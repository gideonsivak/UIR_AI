
"""One-way, idempotent import of existing JSON data into MySQL.

The JSON source files are read only and are never changed or deleted.
Existing MySQL users and plants are not overwritten.
"""

import json
import logging
import sys
from pathlib import Path

from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal
from app.models import Plant, PlantAnalysis, User
from app.schemas import PlantAnalysis as PlantAnalysisSchema


DATA_DIR = BACKEND_DIR / "data"

logger = logging.getLogger(__name__)


def read_records(name: str) -> list[dict]:
    """Read and validate the top-level JSON file structure."""

    path = DATA_DIR / f"{name}.json"

    with path.open(encoding="utf-8") as source:
        records = json.load(source)

    if not isinstance(records, list):
        raise ValueError(
            f"{name}.json must contain a JSON array"
        )

    return records


def parse_legacy_analysis(value):
    """Validate old structured analysis without changing its source data.

    Invalid or plain-text legacy analyses are skipped.
    The corresponding plant can still be imported.
    """

    if value is None or value == "":
        return None

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Skipping a legacy analysis that is not valid JSON"
            )
            return None

    if not isinstance(value, dict):
        logger.warning(
            "Skipping a legacy analysis that is not a JSON object"
        )
        return None

    try:
        return PlantAnalysisSchema.model_validate(value)

    except ValidationError:
        logger.warning(
            "Skipping a legacy analysis with invalid or missing fields"
        )
        return None


def main() -> None:
    """Import JSON users and plants without overwriting existing records."""

    users = read_records("users")
    plants = read_records("plants")

    imported_users = 0
    imported_plants = 0
    skipped_users = 0
    skipped_plants = 0
    imported_analyses = 0
    skipped_analyses = 0

    with SessionLocal.begin() as session:

        # ------------------------------------------
        # IMPORT USERS
        # ------------------------------------------

        for record in users:

            if session.get(User, record["id"]):
                skipped_users += 1
                continue

            email = record["email"].strip().lower()

            if session.query(User.id).filter_by(email=email).first():
                skipped_users += 1
                continue

            user = User(
                id=record["id"],
                name=record["name"],
                email=email,
                created_at=record["created_at"],
                updated_at=record["updated_at"],
            )

            session.add(user)
            imported_users += 1

        session.flush()

        # ------------------------------------------
        # IMPORT PLANTS
        # ------------------------------------------

        for record in plants:

            if session.get(Plant, record["id"]):
                skipped_plants += 1
                continue

            if not session.get(User, record["user_id"]):
                logger.warning(
                    "Skipping plant because its user does not exist"
                )
                skipped_plants += 1
                continue

            plant = Plant(
                id=record["id"],
                user_id=record["user_id"],
                plant_name=record["plant_name"],
                plant_type=record["plant_type"],
                location=record.get("location"),
                symptom=record["symptom"],
                created_at=record["created_at"],
                updated_at=record["updated_at"],
            )

            # --------------------------------------
            # STRUCTURED AI ANALYSIS
            # --------------------------------------

            raw_analysis = record.get("analysis")

            analysis = parse_legacy_analysis(raw_analysis)

            if analysis is not None:

                values = analysis.model_dump()

                plant.analysis = PlantAnalysis(
                    plant_id=plant.id,
                    possible_issue=values["possible_issue"],
                    explanation=values["explanation"],
                    care_suggestions=json.dumps(
                        values["care_suggestions"],
                        ensure_ascii=False,
                    ),
                    expert_advice=values["expert_advice"],
                    expert_advice_needed=values[
                        "expert_advice_needed"
                    ],
                )

                imported_analyses += 1

            elif raw_analysis is not None:
                skipped_analyses += 1

            session.add(plant)
            imported_plants += 1

    print(
        f"Imported users: {imported_users}; "
        f"skipped existing users: {skipped_users}; "
        f"imported plants: {imported_plants}; "
        f"skipped existing plants: {skipped_plants}; "
        f"imported analyses: {imported_analyses}; "
        f"skipped invalid analyses: {skipped_analyses}."
    )


if __name__ == "__main__":
    main()
