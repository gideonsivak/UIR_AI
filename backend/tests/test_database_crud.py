
"""Database CRUD and structured AI analysis tests.

All tests use an isolated in-memory SQLite database.
The real MySQL database is not modified.
"""

import json
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import selectinload, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Plant, PlantAnalysis, User


def make_analysis(expert_advice_needed=False):
    """Return a valid structured plant analysis."""
    return {
        "possible_issue": "Overwatering stress",
        "explanation": "Wet soil can reduce root oxygen.",
        "care_suggestions": [
            "Check soil moisture.",
            "Use drainage holes.",
            "Reduce watering frequency.",
        ],
        "expert_advice": "Consult an expert if symptoms worsen.",
        "expert_advice_needed": expert_advice_needed,
    }


class DatabaseCrudTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Create a separate SQLite database for testing."""

        cls.engine = create_engine(
            "sqlite://",
            connect_args={
                "check_same_thread": False,
            },
            poolclass=StaticPool,
        )

        cls.Session = sessionmaker(
            bind=cls.engine,
            autoflush=False,
            autocommit=False,
        )

        Base.metadata.create_all(cls.engine)

        def override_get_db():
            session = cls.Session()

            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db

        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        """Remove only the temporary SQLite test database."""

        app.dependency_overrides.pop(get_db, None)

        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def tearDown(self):
        """Clear test records between tests."""

        with self.Session.begin() as session:
            session.query(PlantAnalysis).delete()
            session.query(Plant).delete()
            session.query(User).delete()

    def create_test_user(self):
        """Create a user through the real FastAPI endpoint."""

        response = self.client.post(
            "/api/users",
            json={
                "name": "Test Gardener",
                "email": f"test-{uuid4().hex}@example.com",
            },
        )

        self.assertEqual(
            response.status_code,
            201,
            response.text,
        )

        return response.json()

    def plant_payload(self, user_id, analysis=None):
        """Build a valid plant request."""

        return {
            "user_id": user_id,
            "plant_name": "Basil",
            "plant_type": "Herb",
            "location": "Kitchen",
            "symptom": "Yellow leaves",
            "analysis": analysis,
        }

    # ----------------------------------------------
    # CREATE AND READ PLANT ANALYSIS
    # ----------------------------------------------

    def test_create_and_read_structured_analysis(self):
        user = self.create_test_user()

        analysis = make_analysis(
            expert_advice_needed=True
        )

        payload = self.plant_payload(
            user["id"],
            analysis,
        )

        response = self.client.post(
            "/api/plants",
            json=payload,
        )

        self.assertEqual(
            response.status_code,
            201,
            response.text,
        )

        plant = response.json()

        self.assertEqual(
            plant["analysis"]["possible_issue"],
            analysis["possible_issue"],
        )

        self.assertEqual(
            plant["analysis"]["care_suggestions"],
            analysis["care_suggestions"],
        )

        self.assertIs(
            plant["analysis"]["expert_advice_needed"],
            True,
        )

        # Verify the stored MySQL-compatible JSON text format.
        with self.Session() as session:
            stored = session.scalar(
                select(PlantAnalysis).where(
                    PlantAnalysis.plant_id == plant["id"]
                )
            )

            self.assertIsNotNone(stored)

            self.assertIs(
                stored.expert_advice_needed,
                True,
            )

            self.assertEqual(
                json.loads(stored.care_suggestions),
                analysis["care_suggestions"],
            )

        # Retrieve the same analysis through the API.
        get_response = self.client.get(
            f"/api/plants/{plant['id']}"
        )

        self.assertEqual(
            get_response.status_code,
            200,
        )

        self.assertEqual(
            get_response.json()["analysis"],
            analysis,
        )

    # ----------------------------------------------
    # LIST PLANTS
    # ----------------------------------------------

    def test_list_plants_returns_structured_analysis(self):
        user = self.create_test_user()

        self.client.post(
            "/api/plants",
            json=self.plant_payload(
                user["id"],
                make_analysis(True),
            ),
        )

        response = self.client.get(
            "/api/plants",
            params={"user_id": user["id"]},
        )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        plants = response.json()

        self.assertEqual(len(plants), 1)

        self.assertIs(
            plants[0]["analysis"]["expert_advice_needed"],
            True,
        )

        self.assertEqual(
            len(plants[0]["analysis"]["care_suggestions"]),
            3,
        )

    # ----------------------------------------------
    # UPDATE PLANT ANALYSIS
    # ----------------------------------------------

    def test_update_analysis_and_boolean_flag(self):
        user = self.create_test_user()

        response = self.client.post(
            "/api/plants",
            json=self.plant_payload(
                user["id"],
                make_analysis(False),
            ),
        )

        self.assertEqual(
            response.status_code,
            201,
            response.text,
        )

        plant_id = response.json()["id"]

        updated_analysis = make_analysis(True)

        updated_analysis["possible_issue"] = (
            "Possible fungal leaf infection"
        )

        update_payload = self.plant_payload(
            user["id"],
            updated_analysis,
        )

        update_payload["plant_name"] = "Sweet Basil"

        update_response = self.client.put(
            f"/api/plants/{plant_id}",
            json=update_payload,
        )

        self.assertEqual(
            update_response.status_code,
            200,
            update_response.text,
        )

        updated_plant = update_response.json()

        self.assertEqual(
            updated_plant["plant_name"],
            "Sweet Basil",
        )

        self.assertIs(
            updated_plant["analysis"]["expert_advice_needed"],
            True,
        )

        self.assertEqual(
            updated_plant["analysis"]["possible_issue"],
            "Possible fungal leaf infection",
        )

    # ----------------------------------------------
    # REMOVE ANALYSIS WITHOUT DELETING PLANT
    # ----------------------------------------------

    def test_remove_analysis_preserves_plant(self):
        user = self.create_test_user()

        response = self.client.post(
            "/api/plants",
            json=self.plant_payload(
                user["id"],
                make_analysis(),
            ),
        )

        self.assertEqual(
            response.status_code,
            201,
            response.text,
        )

        plant_id = response.json()["id"]

        update_payload = self.plant_payload(
            user["id"],
            None,
        )

        update_response = self.client.put(
            f"/api/plants/{plant_id}",
            json=update_payload,
        )

        self.assertEqual(
            update_response.status_code,
            200,
            update_response.text,
        )

        self.assertIsNone(
            update_response.json()["analysis"]
        )

        with self.Session() as session:
            stored_plant = session.scalar(
                select(Plant)
                .options(selectinload(Plant.analysis))
                .where(Plant.id == plant_id)
            )

            self.assertIsNotNone(stored_plant)

            self.assertIsNone(
                stored_plant.analysis
            )

    # ----------------------------------------------
    # LEGACY ANALYSIS WITHOUT BOOLEAN FIELD
    # ----------------------------------------------

    def test_legacy_analysis_defaults_to_false(self):
        user = self.create_test_user()

        legacy_analysis = make_analysis()

        del legacy_analysis["expert_advice_needed"]

        response = self.client.post(
            "/api/plants",
            json=self.plant_payload(
                user["id"],
                legacy_analysis,
            ),
        )

        self.assertEqual(
            response.status_code,
            201,
            response.text,
        )

        self.assertIs(
            response.json()["analysis"]["expert_advice_needed"],
            False,
        )

    # ----------------------------------------------
    # CORRUPTED LEGACY JSON
    # ----------------------------------------------

    def test_invalid_stored_json_does_not_crash_list(self):
        user = self.create_test_user()

        response = self.client.post(
            "/api/plants",
            json=self.plant_payload(
                user["id"],
                make_analysis(),
            ),
        )

        self.assertEqual(
            response.status_code,
            201,
            response.text,
        )

        plant_id = response.json()["id"]

        with self.Session.begin() as session:
            stored_analysis = session.scalar(
                select(PlantAnalysis).where(
                    PlantAnalysis.plant_id == plant_id
                )
            )

            stored_analysis.care_suggestions = (
                "invalid JSON content"
            )

        list_response = self.client.get(
            "/api/plants",
            params={"user_id": user["id"]},
        )

        self.assertEqual(
            list_response.status_code,
            200,
            list_response.text,
        )

        plants = list_response.json()

        self.assertEqual(len(plants), 1)

        self.assertIsNone(
            plants[0]["analysis"]
        )

    # ----------------------------------------------
    # INVALID ANALYSIS INPUT
    # ----------------------------------------------

    def test_invalid_suggestions_are_rejected(self):
        user = self.create_test_user()

        analysis = make_analysis()

        analysis["care_suggestions"] = [
            "Only one suggestion"
        ]

        response = self.client.post(
            "/api/plants",
            json=self.plant_payload(
                user["id"],
                analysis,
            ),
        )

        self.assertEqual(
            response.status_code,
            422,
        )

    # ----------------------------------------------
    # DELETE PLANT
    # ----------------------------------------------

    def test_delete_plant_and_its_analysis(self):
        user = self.create_test_user()

        response = self.client.post(
            "/api/plants",
            json=self.plant_payload(
                user["id"],
                make_analysis(True),
            ),
        )

        self.assertEqual(
            response.status_code,
            201,
            response.text,
        )

        plant_id = response.json()["id"]

        delete_response = self.client.delete(
            f"/api/plants/{plant_id}"
        )

        self.assertEqual(
            delete_response.status_code,
            204,
        )

        with self.Session() as session:
            self.assertIsNone(
                session.get(Plant, plant_id)
            )

            stored_analysis = session.scalar(
                select(PlantAnalysis).where(
                    PlantAnalysis.plant_id == plant_id
                )
            )

            self.assertIsNone(stored_analysis)

    # ----------------------------------------------
    # DELETE USER AND RELATED PLANTS
    # ----------------------------------------------

    def test_delete_user_cascades_to_plants(self):
        user = self.create_test_user()

        response = self.client.post(
            "/api/plants",
            json=self.plant_payload(
                user["id"],
                make_analysis(True),
            ),
        )

        self.assertEqual(
            response.status_code,
            201,
            response.text,
        )

        plant_id = response.json()["id"]

        delete_response = self.client.delete(
            f"/api/users/{user['id']}"
        )

        self.assertEqual(
            delete_response.status_code,
            204,
        )

        with self.Session() as session:
            self.assertIsNone(
                session.get(User, user["id"])
            )

            self.assertIsNone(
                session.get(Plant, plant_id)
            )


if __name__ == "__main__":
    unittest.main()