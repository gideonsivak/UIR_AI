
"""Tests for plant analysis input and structured response validation."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    PlantAnalysis,
)


def valid_analysis():
    """A valid structured plant analysis for testing."""
    return {
        "possible_issue": "Possible overwatering",
        "explanation": (
            "Excess soil moisture may reduce oxygen "
            "availability around plant roots."
        ),
        "care_suggestions": [
            "Check soil moisture before watering.",
            "Ensure the plant pot has drainage holes.",
            "Improve airflow around the plant.",
        ],
        "expert_advice": (
            "Consult a local agricultural expert "
            "if symptoms continue or spread."
        ),
        "expert_advice_needed": False,
    }


class AnalyzeRequestValidationTests(unittest.TestCase):

    def test_valid_input_is_trimmed_and_accepted(self):
        request = AnalyzeRequest(
            plant_name="  Basil  ",
            plant_type=" Herb ",
            location="Kitchen",
            symptoms="  Yellow leaves and damp soil.  ",
        )

        self.assertEqual(request.plant_name, "Basil")
        self.assertEqual(request.plant_type, "Herb")
        self.assertEqual(
            request.symptoms,
            "Yellow leaves and damp soil.",
        )

    def test_blank_required_fields_are_rejected(self):
        for field in (
            "plant_name",
            "plant_type",
            "symptoms",
        ):
            payload = {
                "plant_name": "Basil",
                "plant_type": "Herb",
                "symptoms": "Yellow leaves",
            }

            payload[field] = "   \t "

            with self.subTest(field=field):
                with self.assertRaises(ValidationError) as context:
                    AnalyzeRequest(**payload)

                self.assertIn(
                    "Please provide",
                    str(context.exception),
                )

    def test_contradictory_absolute_soil_symptoms_are_rejected(self):
        with self.assertRaises(ValidationError) as context:
            AnalyzeRequest(
                plant_name="Basil",
                plant_type="Herb",
                symptoms=(
                    "The soil is completely dry and waterlogged."
                ),
            )

        self.assertIn(
            "Please clarify its current condition",
            str(context.exception),
        )

    def test_ambiguous_plant_classification_is_allowed(self):
        request = AnalyzeRequest(
            plant_name="Potato",
            plant_type="Flower",
            symptoms="Leaves have brown spots.",
        )

        self.assertEqual(request.plant_name, "Potato")
        self.assertEqual(request.plant_type, "Flower")

    def test_invalid_request_does_not_call_analysis_service(self):
        client = TestClient(app)

        payload = {
            "plant_name": "   ",
            "plant_type": "Herb",
            "symptoms": "Yellow leaves",
        }

        with patch("app.main.analyze_plant") as analyze_plant:
            response = client.post(
                "/api/analyze",
                json=payload,
            )

        self.assertEqual(response.status_code, 422)
        analyze_plant.assert_not_called()

    def test_placeholder_values_are_rejected(self):
        for value in ("unknown", "n/a", "?"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    AnalyzeRequest(
                        plant_name=value,
                        plant_type="Herb",
                        symptoms="Yellow leaves",
                    )

    def test_whitespace_only_symptoms_are_rejected(self):
        with self.assertRaises(ValidationError):
            AnalyzeRequest(
                plant_name="Basil",
                plant_type="Herb",
                symptoms="   ",
            )

    def test_missing_required_field_returns_422(self):
        client = TestClient(app)

        with patch("app.main.analyze_plant") as ai_mock:
            response = client.post(
                "/api/analyze",
                json={
                    "plant_name": "Basil",
                    "plant_type": "Herb",
                },
            )

        self.assertEqual(response.status_code, 422)
        ai_mock.assert_not_called()


class StructuredResponseValidationTests(unittest.TestCase):

    def test_valid_structured_response(self):
        response = AnalyzeResponse(
            **valid_analysis(),
            demo=False,
        )

        self.assertEqual(
            response.possible_issue,
            "Possible overwatering",
        )
        self.assertEqual(
            len(response.care_suggestions),
            3,
        )
        self.assertIs(
            response.expert_advice_needed,
            False,
        )
        self.assertIs(response.demo, False)

    def test_expert_advice_needed_true(self):
        data = valid_analysis()
        data["expert_advice_needed"] = True

        response = AnalyzeResponse(
            **data,
            demo=False,
        )

        self.assertIs(
            response.expert_advice_needed,
            True,
        )

    def test_missing_expert_flag_uses_legacy_default(self):
        data = valid_analysis()
        del data["expert_advice_needed"]

        analysis = PlantAnalysis(**data)

        self.assertIs(
            analysis.expert_advice_needed,
            False,
        )

    def test_invalid_suggestions_count_is_rejected(self):
        data = valid_analysis()
        data["care_suggestions"] = [
            "Water carefully."
        ]

        with self.assertRaises(ValidationError):
            AnalyzeResponse(**data)

    def test_blank_suggestions_are_rejected(self):
        data = valid_analysis()
        data["care_suggestions"] = [
            "Check the soil.",
            "   ",
            "Improve drainage.",
        ]

        with self.assertRaises(ValidationError):
            AnalyzeResponse(**data)

    def test_blank_possible_issue_is_rejected(self):
        data = valid_analysis()
        data["possible_issue"] = "   "

        with self.assertRaises(ValidationError):
            AnalyzeResponse(**data)

    def test_invalid_boolean_is_rejected(self):
        data = valid_analysis()
        data["expert_advice_needed"] = "not sure"

        with self.assertRaises(ValidationError):
            AnalyzeResponse(**data)

    def test_endpoint_returns_structured_response(self):
        client = TestClient(app)

        ai_result = {
            **valid_analysis(),
            "demo": False,
        }

        with patch(
            "app.main.analyze_plant",
            return_value=ai_result,
        ):
            response = client.post(
                "/api/analyze",
                json={
                    "plant_name": "Tomato",
                    "plant_type": "Vegetable",
                    "symptoms": "Yellow leaves",
                },
            )

        self.assertEqual(response.status_code, 200)

        body = response.json()

        self.assertIn("possible_issue", body)
        self.assertIn("explanation", body)
        self.assertIn("care_suggestions", body)
        self.assertIn("expert_advice", body)
        self.assertIn("expert_advice_needed", body)

        self.assertIsInstance(
            body["care_suggestions"],
            list,
        )

        self.assertIsInstance(
            body["expert_advice_needed"],
            bool,
        )


if __name__ == "__main__":
    unittest.main()
