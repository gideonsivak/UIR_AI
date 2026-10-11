
"""Tests for GIDEON PLANT smart diagnostic interviews."""

import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from itsdangerous import SignatureExpired

from app.main import app


TEST_SIGNING_KEY = "test-only-diagnosis-signing-key-1234567890"


def valid_form():
    """Valid multipart plant information."""
    return {
        "plant_name": "Tomato",
        "plant_type": "vegetable",
        "location": "Home garden",
        "symptoms": "Yellow leaves and slow growth",
    }


def valid_questions():
    """Three sample AI-generated interview questions."""
    return [
        {
            "id": "q1",
            "question": "How often do you water the plant?",
            "explanation": "Watering affects root health.",
        },
        {
            "id": "q2",
            "question": "How much sunlight does it receive?",
            "explanation": "Sunlight affects plant growth.",
        },
        {
            "id": "q3",
            "question": "Have you noticed any insects?",
            "explanation": "Insects may indicate pests.",
        },
    ]


def valid_validation(
    plant_match="NOT_CHECKED",
    category_match="YES",
    can_continue=True,
):
    """Structured validation result from the mocked AI."""
    return {
        "plant_match": {
            "status": plant_match,
            "reason": (
                "No image was uploaded."
                if plant_match == "NOT_CHECKED"
                else "Plant identity was checked."
            ),
            "correction_instruction": (
                "Upload an image matching the plant name."
                if plant_match == "NO"
                else None
            ),
        },
        "category_match": {
            "status": category_match,
            "reason": (
                "The selected category was checked."
            ),
            "suggested_categories": (
                ["fruit", "tree"]
                if category_match == "NO"
                else []
            ),
        },
        "image_is_plant": None,
        "image_is_clear_enough": None,
        "can_continue": can_continue,
    }


def valid_start_result():
    """Successful first phase of diagnosis."""
    return {
        "validation": valid_validation(),
        "questions": valid_questions(),
    }


def rejected_start_result(
    plant_match="NOT_CHECKED",
    category_match="NO",
):
    """Rejected diagnosis must not contain questions."""
    return {
        "validation": valid_validation(
            plant_match=plant_match,
            category_match=category_match,
            can_continue=False,
        ),
        "questions": [],
    }


def valid_answers():
    """Answers matching all three signed questions."""
    return [
        {
            "question_id": "q1",
            "question": "How often do you water the plant?",
            "answer": "Every day",
        },
        {
            "question_id": "q2",
            "question": "How much sunlight does it receive?",
            "answer": "About four hours",
        },
        {
            "question_id": "q3",
            "question": "Have you noticed any insects?",
            "answer": "Not sure",
        },
    ]


def valid_final_result():
    """Structured final diagnosis returned by mocked Gemini."""
    return {
        "possible_issue": "Possible overwatering",
        "explanation": (
            "Frequent watering may reduce oxygen "
            "availability around the roots."
        ),
        "care_suggestions": [
            "Check the soil moisture.",
            "Improve soil drainage.",
            "Monitor the plant for several days.",
        ],
        "expert_advice": (
            "Consult a plant specialist if symptoms worsen."
        ),
        "expert_advice_needed": False,
        "ai_confidence": 82,
        "plant_match": "NOT_CHECKED",
        "category_match": "YES",
        "interview_answers": valid_answers(),
        "validation": valid_validation(),
        "demo": False,
    }


class SmartDiagnosisTests(unittest.TestCase):
    """Test new diagnostic endpoints without calling Gemini."""

    def setUp(self):
        self.env_patcher = patch.dict(
            "os.environ",
            {"DIAGNOSIS_SIGNING_KEY": TEST_SIGNING_KEY},
        )
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)

        self.client = TestClient(app)

    def start_interview(self):
        """Create a real signed token using mocked AI output."""
        with patch(
            "app.main.start_diagnosis",
            return_value=valid_start_result(),
        ) as ai_mock:
            response = self.client.post(
                "/api/diagnosis/start",
                data=valid_form(),
            )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )
        ai_mock.assert_called_once()

        return response.json()

    def complete_interview(
        self,
        token,
        answers=None,
        form=None,
    ):
        """Submit interview answers with the original details."""
        payload = dict(form or valid_form())
        payload["interview_token"] = token
        payload["answers_json"] = json.dumps(
            valid_answers() if answers is None else answers
        )

        return self.client.post(
            "/api/diagnosis/complete",
            data=payload,
        )

    # ----------------------------------------------
    # START ENDPOINT
    # ----------------------------------------------

    def test_start_returns_three_questions_and_token(self):
        result = self.start_interview()

        self.assertTrue(
            result["validation"]["can_continue"]
        )
        self.assertEqual(len(result["questions"]), 3)
        self.assertTrue(result["interview_token"])

    def test_invalid_category_returns_422(self):
        form = valid_form()
        form["plant_type"] = "invalid-category"

        with patch("app.main.start_diagnosis") as ai_mock:
            response = self.client.post(
                "/api/diagnosis/start",
                data=form,
            )

        self.assertEqual(response.status_code, 422)
        ai_mock.assert_not_called()

    def test_blank_plant_name_returns_422(self):
        form = valid_form()
        form["plant_name"] = "   "

        with patch("app.main.start_diagnosis") as ai_mock:
            response = self.client.post(
                "/api/diagnosis/start",
                data=form,
            )

        self.assertEqual(response.status_code, 422)
        ai_mock.assert_not_called()

    def test_wrong_category_blocks_interview(self):
        with patch(
            "app.main.start_diagnosis",
            return_value=rejected_start_result(),
        ):
            response = self.client.post(
                "/api/diagnosis/start",
                data=valid_form(),
            )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        result = response.json()

        self.assertFalse(
            result["validation"]["can_continue"]
        )
        self.assertEqual(
            result["validation"]["category_match"]["status"],
            "NO",
        )
        self.assertEqual(result["questions"], [])
        self.assertIsNone(result["interview_token"])

    def test_plant_mismatch_blocks_interview(self):
        with patch(
            "app.main.start_diagnosis",
            return_value=rejected_start_result(
                plant_match="NO",
                category_match="YES",
            ),
        ):
            response = self.client.post(
                "/api/diagnosis/start",
                data=valid_form(),
            )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        result = response.json()

        self.assertEqual(
            result["validation"]["plant_match"]["status"],
            "NO",
        )
        self.assertFalse(
            result["validation"]["can_continue"]
        )
        self.assertEqual(result["questions"], [])
        self.assertIsNone(result["interview_token"])

    def test_invalid_image_type_rejected_before_ai(self):
        with patch("app.main.start_diagnosis") as ai_mock:
            response = self.client.post(
                "/api/diagnosis/start",
                data=valid_form(),
                files={
                    "image": (
                        "plant.txt",
                        b"This is not an image",
                        "text/plain",
                    )
                },
            )

        self.assertEqual(response.status_code, 400)
        ai_mock.assert_not_called()

    def test_fake_png_rejected_before_ai(self):
        with patch("app.main.start_diagnosis") as ai_mock:
            response = self.client.post(
                "/api/diagnosis/start",
                data=valid_form(),
                files={
                    "image": (
                        "plant.png",
                        b"not a real PNG",
                        "image/png",
                    )
                },
            )

        self.assertEqual(response.status_code, 400)
        ai_mock.assert_not_called()

    def test_missing_signing_key_blocks_token_creation(self):
        with patch.dict(
            "os.environ",
            {"DIAGNOSIS_SIGNING_KEY": ""},
        ):
            with patch(
                "app.main.start_diagnosis",
                return_value=valid_start_result(),
            ):
                response = self.client.post(
                    "/api/diagnosis/start",
                    data=valid_form(),
                )

        self.assertEqual(response.status_code, 503)

    # ----------------------------------------------
    # COMPLETE ENDPOINT
    # ----------------------------------------------

    def test_complete_returns_final_ai_confidence(self):
        started = self.start_interview()

        with patch(
            "app.main.complete_diagnosis",
            return_value=valid_final_result(),
        ) as ai_mock:
            response = self.complete_interview(
                started["interview_token"]
            )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        result = response.json()

        self.assertEqual(result["ai_confidence"], 82)
        self.assertEqual(result["category_match"], "YES")
        self.assertEqual(
            result["plant_match"],
            "NOT_CHECKED",
        )
        self.assertEqual(
            len(result["interview_answers"]),
            3,
        )
        self.assertFalse(result["demo"])
        ai_mock.assert_called_once()

    def test_tampered_token_rejected(self):
        started = self.start_interview()

        token = started["interview_token"]
        tampered_token = token + "tampered"

        with patch("app.main.complete_diagnosis") as ai_mock:
            response = self.complete_interview(
                tampered_token
            )

        self.assertEqual(response.status_code, 422)
        ai_mock.assert_not_called()

    def test_expired_token_rejected(self):
        started = self.start_interview()

        with patch(
            "app.main.get_interview_serializer"
        ) as serializer_mock:
            serializer_mock.return_value.loads.side_effect = (
                SignatureExpired("Token expired")
            )

            with patch(
                "app.main.complete_diagnosis"
            ) as ai_mock:
                response = self.complete_interview(
                    started["interview_token"]
                )

        self.assertEqual(response.status_code, 422)
        ai_mock.assert_not_called()

    def test_changed_plant_name_rejected(self):
        started = self.start_interview()

        changed_form = valid_form()
        changed_form["plant_name"] = "Potato"

        with patch("app.main.complete_diagnosis") as ai_mock:
            response = self.complete_interview(
                started["interview_token"],
                form=changed_form,
            )

        self.assertEqual(response.status_code, 422)
        ai_mock.assert_not_called()

    def test_changed_category_rejected(self):
        started = self.start_interview()

        changed_form = valid_form()
        changed_form["plant_type"] = "fruit"

        with patch("app.main.complete_diagnosis") as ai_mock:
            response = self.complete_interview(
                started["interview_token"],
                form=changed_form,
            )

        self.assertEqual(response.status_code, 422)
        ai_mock.assert_not_called()

    def test_missing_answer_rejected(self):
        started = self.start_interview()

        incomplete_answers = valid_answers()[:2]

        with patch("app.main.complete_diagnosis") as ai_mock:
            response = self.complete_interview(
                started["interview_token"],
                answers=incomplete_answers,
            )

        self.assertEqual(response.status_code, 422)
        ai_mock.assert_not_called()

    def test_duplicate_answer_rejected(self):
        started = self.start_interview()

        duplicate_answers = valid_answers()
        duplicate_answers[2] = duplicate_answers[0].copy()

        with patch("app.main.complete_diagnosis") as ai_mock:
            response = self.complete_interview(
                started["interview_token"],
                answers=duplicate_answers,
            )

        self.assertEqual(response.status_code, 422)
        ai_mock.assert_not_called()

    def test_modified_question_rejected(self):
        started = self.start_interview()

        answers = valid_answers()
        answers[0]["question"] = (
            "A question that was not originally asked"
        )

        with patch("app.main.complete_diagnosis") as ai_mock:
            response = self.complete_interview(
                started["interview_token"],
                answers=answers,
            )

        self.assertEqual(response.status_code, 422)
        ai_mock.assert_not_called()

    def test_not_sure_is_accepted_as_answer(self):
        started = self.start_interview()

        answers = valid_answers()

        self.assertEqual(
            answers[2]["answer"],
            "Not sure",
        )

        with patch(
            "app.main.complete_diagnosis",
            return_value=valid_final_result(),
        ) as ai_mock:
            response = self.complete_interview(
                started["interview_token"],
                answers=answers,
            )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )
        ai_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
