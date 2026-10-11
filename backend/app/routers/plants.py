
"""Plant CRUD API with structured AI analysis and safe JSON storage."""

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Plant, PlantAnalysis, User
from ..schemas import PlantCreate, PlantResponse, PlantUpdate


router = APIRouter(prefix="/api/plants", tags=["Plants"])
logger = logging.getLogger(__name__)


def now() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def storage_failure(db: Session, error: SQLAlchemyError) -> None:
    """Rollback failed database operations."""
    db.rollback()
    logger.exception("Plant database operation failed", exc_info=error)
    raise HTTPException(
        status_code=500,
        detail="Plant storage is unavailable. Please try again later.",
    ) from error


def get_plant_or_404(db: Session, plant_id: str) -> Plant:
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


def ensure_user(db: Session, user_id: str) -> None:
    """Ensure the supplied user exists."""
    if db.get(User, user_id) is None:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )


def parse_care_suggestions(value: str | None) -> list[str] | None:
    """Safely decode a stored JSON array of care suggestions.

    Invalid legacy values return None instead of crashing the API.
    """

    if not value:
        return None

    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Invalid legacy care suggestions JSON found")
        return None

    if not isinstance(parsed, list):
        logger.warning("Stored care suggestions are not a JSON array")
        return None

    if len(parsed) != 3:
        logger.warning("Stored care suggestions have an invalid length")
        return None

    if not all(
        isinstance(item, str) and item.strip()
        for item in parsed
    ):
        logger.warning("Stored care suggestions contain invalid values")
        return None

    return [item.strip() for item in parsed]


def as_response(plant: Plant) -> dict:
    """Convert a SQLAlchemy Plant into the existing API response format."""

    analysis = None

    if plant.analysis is not None:
        suggestions = parse_care_suggestions(
            plant.analysis.care_suggestions
        )

        # A corrupted legacy analysis must not crash the entire
        # plant listing or prevent the plant from being displayed.
        if suggestions is not None:
            analysis = {
                "possible_issue": plant.analysis.possible_issue,
                "explanation": plant.analysis.explanation,
                "care_suggestions": suggestions,
                "expert_advice": plant.analysis.expert_advice,
                "expert_advice_needed": bool(
                    plant.analysis.expert_advice_needed
                ),
            }

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


def set_analysis(plant: Plant, analysis) -> None:
    """Create, replace, update, or clear a plant's structured analysis."""

    if analysis is None:
        plant.analysis = None
        return

    values = analysis.model_dump()

    suggestions_json = json.dumps(
        values["care_suggestions"],
        ensure_ascii=False,
    )

    if plant.analysis is None:
        plant.analysis = PlantAnalysis(
            plant_id=plant.id,
            possible_issue=values["possible_issue"],
            explanation=values["explanation"],
            care_suggestions=suggestions_json,
            expert_advice=values["expert_advice"],
            expert_advice_needed=values["expert_advice_needed"],
        )
        return

    plant.analysis.possible_issue = values["possible_issue"]
    plant.analysis.explanation = values["explanation"]
    plant.analysis.care_suggestions = suggestions_json
    plant.analysis.expert_advice = values["expert_advice"]
    plant.analysis.expert_advice_needed = values["expert_advice_needed"]


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

        values = payload.model_dump(exclude={"analysis"})

        plant = Plant(
            id=str(uuid4()),
            **values,
            created_at=timestamp,
            updated_at=timestamp,
        )

        set_analysis(plant, payload.analysis)

        db.add(plant)
        db.commit()

        db.refresh(plant)

        return as_response(plant)

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
            query = query.where(Plant.user_id == user_id)

        plants = db.scalars(query).all()

        return [as_response(plant) for plant in plants]

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
        plant = get_plant_or_404(db, plant_id)
        return as_response(plant)

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
        ensure_user(db, payload.user_id)

        plant = get_plant_or_404(db, plant_id)

        values = payload.model_dump(exclude={"analysis"})

        for key, value in values.items():
            setattr(plant, key, value)

        set_analysis(plant, payload.analysis)

        plant.updated_at = now()

        db.commit()
        db.refresh(plant)

        return as_response(plant)

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
        plant = get_plant_or_404(db, plant_id)

        db.delete(plant)
        db.commit()

    except HTTPException:
        raise
    except SQLAlchemyError as error:
        storage_failure(db, error)
