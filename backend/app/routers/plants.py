
"""Plant CRUD API with structured AI analysis and safe JSON storage."""

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Plant, PlantAnalysis, User
from ..schemas import (
    InterviewAnswer,
    PlantCreate,
    PlantResponse,
    PlantUpdate,
)


router = APIRouter(
    prefix="/api/plants",
    tags=["Plants"],
)

logger = logging.getLogger(__name__)


# --------------------------------------------------
# SHARED HELPERS
# --------------------------------------------------

def now() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def storage_failure(
    db: Session,
    error: SQLAlchemyError,
) -> None:
    """Rollback failed database operations."""

    db.rollback()

    logger.exception(
        "Plant database operation failed",
        exc_info=error,
    )

    raise HTTPException(
        status_code=500,
        detail=(
            "Plant storage is unavailable. "
            "Please try again later."
        ),
    ) from error


def get_plant_or_404(
    db: Session,
    plant_id: str,
) -> Plant:
    """Find a plant and load its saved analysis."""

    plant = db.scalar(
        select(Plant)
        .options(selectinload(Plant.analysis))
        .where(Plant.id == plant_id)
    )

    if plant is None:
        raise HTTPException(
            status_code=404,
            detail="Plant not found.",
        )

    return plant


def ensure_user(
    db: Session,
    user_id: str,
) -> None:
    """Ensure the supplied user exists."""

    if db.get(User, user_id) is None:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )


# --------------------------------------------------
# SAFE JSON PARSING
# --------------------------------------------------

def parse_care_suggestions(
    value: str | None,
) -> list[str] | None:
    """Safely decode stored care suggestions."""

    if not value:
        return None

    try:
        parsed = json.loads(value)

    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "Invalid legacy care suggestions JSON found"
        )
        return None

    if not isinstance(parsed, list):
        logger.warning(
            "Stored care suggestions are not a JSON array"
        )
        return None

    if len(parsed) != 3:
        logger.warning(
            "Stored care suggestions have an invalid length"
        )
        return None

    if not all(
        isinstance(item, str) and item.strip()
        for item in parsed
    ):
        logger.warning(
            "Stored care suggestions contain invalid values"
        )
        return None

    return [
        item.strip()
        for item in parsed
    ]


def parse_interview_answers(
    value: str | None,
) -> list[dict] | None:
    """Safely decode and validate saved interview answers."""

    if not value:
        return None

    try:
        parsed = json.loads(value)

        if not isinstance(parsed, list):
            raise ValueError(
                "Interview answers must be a list"
            )

        if not 3 <= len(parsed) <= 5:
            raise ValueError(
                "Interview must contain 3–5 answers"
            )

        answers = [
            InterviewAnswer.model_validate(item)
            for item in parsed
        ]

        question_ids = [
            answer.question_id
            for answer in answers
        ]

        if len(set(question_ids)) != len(question_ids):
            raise ValueError(
                "Duplicate interview question IDs"
            )

        return [
            answer.model_dump(mode="json")
            for answer in answers
        ]

    except (ValueError, TypeError, ValidationError):
        logger.warning(
            "Invalid saved interview answers JSON found"
        )
        return None


# --------------------------------------------------
# DATABASE MODEL -> API RESPONSE
# --------------------------------------------------

def as_response(plant: Plant) -> dict:
    """Convert SQLAlchemy Plant to API response data."""

    analysis = None

    if plant.analysis is not None:
        suggestions = parse_care_suggestions(
            plant.analysis.care_suggestions
        )

        # Corrupted legacy analysis must not crash the API.
        if suggestions is not None:
            saved = plant.analysis

            analysis = {
                "possible_issue": saved.possible_issue,
                "explanation": saved.explanation,
                "care_suggestions": suggestions,
                "expert_advice": saved.expert_advice,
                "expert_advice_needed": bool(
                    saved.expert_advice_needed
                ),
            }

            # Include new fields only when values exist.
            if saved.ai_confidence is not None:
                analysis["ai_confidence"] = (
                    saved.ai_confidence
                )

            if saved.plant_match is not None:
                analysis["plant_match"] = (
                    saved.plant_match
                )

            if saved.category_match is not None:
                analysis["category_match"] = (
                    saved.category_match
                )

            if saved.interview_answers is not None:
                answers = parse_interview_answers(
                    saved.interview_answers
                )

                if answers is not None:
                    analysis["interview_answers"] = answers

    return {
        "id": plant.id,
        "user_id": plant.user_id,
        "plant_name": plant.plant_name,
        "plant_type": plant.plant_type,
        "location": plant.location,
        "symptom": plant.symptom,
        "analysis": analysis,
        "created_at": plant.created_at,
        "updated_at": plant.updated_at,
    }


# --------------------------------------------------
# RESPONSE SERIALIZATION
# --------------------------------------------------

def plant_json_response(
    data: dict | list,
    status_code: int = 200,
) -> JSONResponse:
    """
    Preserve analysis=null when no analysis exists.

    Omit unused optional fields inside an analysis.
    Validate the response structure before sending it.
    """

    if isinstance(data, list):
        validated = [
            PlantResponse.model_validate(item).model_dump(
                mode="json",
                exclude={
                    "analysis": {
                        "ai_confidence",
                        "plant_match",
                        "category_match",
                        "interview_answers",
                    }
                } if item.get("analysis") is None else None,
            )
            for item in data
        ]

    else:
        validated = PlantResponse.model_validate(
            data
        ).model_dump(mode="json")

        # Remove only absent optional analysis fields.
        if isinstance(data.get("analysis"), dict):
            for field in (
                "ai_confidence",
                "plant_match",
                "category_match",
                "interview_answers",
            ):
                if field not in data["analysis"]:
                    validated["analysis"].pop(field, None)

    # Apply the same cleanup to list responses.
    if isinstance(data, list):
        for original, item in zip(data, validated):
            if not isinstance(original.get("analysis"), dict):
                continue

            for field in (
                "ai_confidence",
                "plant_match",
                "category_match",
                "interview_answers",
            ):
                if field not in original["analysis"]:
                    item["analysis"].pop(field, None)

    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(validated),
    )


# --------------------------------------------------
# API ANALYSIS -> DATABASE MODEL
# --------------------------------------------------

def set_analysis(
    plant: Plant,
    analysis,
) -> None:
    """Create, replace, update, or clear plant analysis."""

    if analysis is None:
        plant.analysis = None
        return

    values = analysis.model_dump(mode="json")

    suggestions_json = json.dumps(
        values["care_suggestions"],
        ensure_ascii=False,
    )

    ai_confidence = values.get("ai_confidence")
    plant_match = values.get("plant_match")
    category_match = values.get("category_match")

    interview_answers = values.get(
        "interview_answers"
    )

    interview_answers_json = (
        json.dumps(
            interview_answers,
            ensure_ascii=False,
        )
        if interview_answers is not None
        else None
    )

    if plant.analysis is None:
        plant.analysis = PlantAnalysis(
            plant_id=plant.id,
            possible_issue=values["possible_issue"],
            explanation=values["explanation"],
            care_suggestions=suggestions_json,
            expert_advice=values["expert_advice"],
            expert_advice_needed=values[
                "expert_advice_needed"
            ],
            ai_confidence=ai_confidence,
            plant_match=plant_match,
            category_match=category_match,
            interview_answers=interview_answers_json,
        )
        return

    # Replace complete existing analysis.
    plant.analysis.possible_issue = values[
        "possible_issue"
    ]

    plant.analysis.explanation = values[
        "explanation"
    ]

    plant.analysis.care_suggestions = suggestions_json

    plant.analysis.expert_advice = values[
        "expert_advice"
    ]

    plant.analysis.expert_advice_needed = values[
        "expert_advice_needed"
    ]

    plant.analysis.ai_confidence = ai_confidence
    plant.analysis.plant_match = plant_match
    plant.analysis.category_match = category_match
    plant.analysis.interview_answers = (
        interview_answers_json
    )


# --------------------------------------------------
# CREATE PLANT
# --------------------------------------------------

@router.post(
    "",
    response_model=PlantResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_plant(
    payload: PlantCreate,
    db: Session = Depends(get_db),
):
    try:
        ensure_user(db, payload.user_id)

        timestamp = now()

        values = payload.model_dump(
            exclude={"analysis"}
        )

        plant = Plant(
            id=str(uuid4()),
            **values,
            created_at=timestamp,
            updated_at=timestamp,
        )

        set_analysis(
            plant,
            payload.analysis,
        )

        db.add(plant)
        db.commit()
        db.refresh(plant)

        return plant_json_response(
            as_response(plant),
            status_code=201,
        )

    except HTTPException:
        raise

    except SQLAlchemyError as error:
        storage_failure(db, error)


# --------------------------------------------------
# LIST PLANTS
# --------------------------------------------------

@router.get(
    "",
    response_model=list[PlantResponse],
)
def list_plants(
    user_id: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        query = (
            select(Plant)
            .options(selectinload(Plant.analysis))
            .order_by(Plant.created_at)
        )

        if user_id:
            query = query.where(
                Plant.user_id == user_id
            )

        plants = db.scalars(query).all()

        return plant_json_response(
            [
                as_response(plant)
                for plant in plants
            ]
        )

    except SQLAlchemyError as error:
        storage_failure(db, error)


# --------------------------------------------------
# GET ONE PLANT
# --------------------------------------------------

@router.get(
    "/{plant_id}",
    response_model=PlantResponse,
)
def get_plant(
    plant_id: str,
    db: Session = Depends(get_db),
):
    try:
        plant = get_plant_or_404(
            db,
            plant_id,
        )

        return plant_json_response(
            as_response(plant)
        )

    except HTTPException:
        raise

    except SQLAlchemyError as error:
        storage_failure(db, error)


# --------------------------------------------------
# UPDATE PLANT
# --------------------------------------------------

@router.put(
    "/{plant_id}",
    response_model=PlantResponse,
)
def update_plant(
    plant_id: str,
    payload: PlantUpdate,
    db: Session = Depends(get_db),
):
    try:
        ensure_user(
            db,
            payload.user_id,
        )

        plant = get_plant_or_404(
            db,
            plant_id,
        )

        values = payload.model_dump(
            exclude={"analysis"}
        )

        for key, value in values.items():
            setattr(
                plant,
                key,
                value,
            )

        set_analysis(
            plant,
            payload.analysis,
        )

        plant.updated_at = now()

        db.commit()
        db.refresh(plant)

        return plant_json_response(
            as_response(plant)
        )

    except HTTPException:
        raise

    except SQLAlchemyError as error:
        storage_failure(db, error)


# --------------------------------------------------
# DELETE PLANT
# --------------------------------------------------

@router.delete(
    "/{plant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_plant(
    plant_id: str,
    db: Session = Depends(get_db),
):
    try:
        plant = get_plant_or_404(
            db,
            plant_id,
        )

        db.delete(plant)
        db.commit()

    except HTTPException:
        raise

    except SQLAlchemyError as error:
        storage_failure(db, error)
