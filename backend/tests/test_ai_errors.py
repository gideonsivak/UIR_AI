
"""Tests for Gemini AI errors and structured JSON responses."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient

from app.ai_errors import (
    AIAuthenticationError,
    AIConfigurationError,
    AINetworkError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
    InvalidAIResponseError,
    classify_provider_error,
    safe_error_message,
)
from app.ai_service import (
    InvalidPlantInputError,
    analyze_plant,
)
from app.main import app


class ProviderFailure(Exception):
    """Simulate a Gemini provider exception."""

    def __init__(self, code, message="provider failure"):
        self.code = code
        super().__init__(message)


def valid_ai_response(expert_advice_needed=False):
    """Return a valid structured Gemini response."""

    return {
        "possible_issue": "Overwatering stress",
        "explanation": (
            "Persistently wet soil can limit root oxygen."
        ),
        "care_suggestions": [
            "Let the top soil dry slightly.",
            "Use drainage holes.",
            "Reduce watering frequency.",
        ],
        "expert_advice": (
            "Consult a local expert if symptoms worsen."
        ),
        "expert_advice_needed": expert_advice_needed,
    }


def valid_input_response():
    """Return a valid Gemini input relevance response."""

    return {
        "is_valid": True,
        "reason": "Meaningful plant information provided.",
    }


def invalid_input_response():
    """Return an invalid Gemini input relevance response."""

    return {
        "is_valid": False,
        "reason": "The submitted values are random text.",
    }


def mock_json_response(data):
    """Wrap a dictionary as a mocked Gemini response."""

    return SimpleNamespace(text=json.dumps(data))


class AIErrorTests(unittest.TestCase):

    # --------------------------------------------------
    # PROVIDER ERROR CLASSIFICATION
    # --------------------------------------------------

    def test_error_classification(self):
        cases = [
            (ProviderFailure(401), AIAuthenticationError),
            (
                ProviderFailure(400, "API key not valid"),
                AIAuthenticationError,
            ),
            (ProviderFailure(429), AIRateLimitError),
            (ProviderFailure("429"), AIRateLimitError),
            (ProviderFailure(408), AITimeoutError),
            (ProviderFailure(504), AITimeoutError),
            (
                httpx.TimeoutException("timed out"),
                AITimeoutError,
            ),
            (
                httpx.ConnectError("offline"),
                AINetworkError,
            ),
            (ProviderFailure(500), AIProviderError),
        ]

        for error, expected_class in cases:
            with self.subTest(error=str(error)):
                classified = classify_provider_error(error)

                self.assertIsInstance(
                    classified,
                    expected_class,
                )

    # --------------------------------------------------
    # SAFE ERROR LOGGING
    # --------------------------------------------------

    def test_safe_error_message_redacts_keys(self):
        key = "AIza" + "x" * 35

        message = safe_error_message(
            RuntimeError(f"api_key={key}"),
            key,
        )

        self.assertNotIn(key, message)
        self.assertIn("[REDACTED]", message)

    def test_safe_error_message_redacts_bearer_token(self):
        secret = "example.secret.token"

        message = safe_error_message(
            RuntimeError(f"Bearer {secret}")
        )

        self.assertNotIn(secret, message)
        self.assertIn("[REDACTED]", message)

    # --------------------------------------------------
    # SUCCESSFUL STRUCTURED JSON
    # --------------------------------------------------

    @patch("app.ai_service.genai.Client")
    @patch.dict(
        "app.ai_service.os.environ",
        {"GEMINI_API_KEY": "test-key"},
        clear=False,
    )
    def test_successful_analysis_is_not_demo(
        self,
        client_factory,
    ):
        client = Mock()

        client.models.generate_content.side_effect = [
            mock_json_response(valid_input_response()),
            mock_json_response(valid_ai_response()),
        ]

        client_factory.return_value = client

        result = analyze_plant(
            "Basil",
            "Herb",
            "Indoors",
            "Yellow leaves",
        )

        self.assertFalse(result["demo"])
        self.assertEqual(
            len(result["care_suggestions"]),
            3,
        )
        self.assertIs(
            result["expert_advice_needed"],
            False,
        )

        self.assertEqual(
            client.models.generate_content.call_count,
            2,
        )

    # --------------------------------------------------
    # EXPERT ADVICE FLAG
    # --------------------------------------------------

    @patch("app.ai_service.genai.Client")
    @patch.dict(
        "app.ai_service.os.environ",
        {"GEMINI_API_KEY": "test-key"},
        clear=False,
    )
    def test_expert_advice_needed_true(
        self,
        client_factory,
    ):
        client = Mock()

        client.models.generate_content.side_effect = [
            mock_json_response(valid_input_response()),
            mock_json_response(
                valid_ai_response(
                    expert_advice_needed=True
                )
            ),
        ]

        client_factory.return_value = client

        result = analyze_plant(
            "Tomato",
            "Vegetable",
            "Jaffna",
            "Rapidly spreading brown spots",
        )

        self.assertIs(
            result["expert_advice_needed"],
            True,
        )

        self.assertEqual(
            client.models.generate_content.call_count,
            2,
        )

    # --------------------------------------------------
    # INVALID INPUT RELEVANCE
    # --------------------------------------------------

    @patch("app.ai_service.genai.Client")
    @patch.dict(
        "app.ai_service.os.environ",
        {"GEMINI_API_KEY": "test-key"},
        clear=False,
    )
    def test_random_input_is_rejected(
        self,
        client_factory,
    ):
        client = Mock()

        client.models.generate_content.return_value = (
            mock_json_response(invalid_input_response())
        )

        client_factory.return_value = client

        with self.assertRaises(InvalidPlantInputError):
            analyze_plant(
                "dcsdcsdc",
                "sdcsdcsdcs",
                "Jaffna",
                "dcsdcsdc",
            )

        # The analysis request must never be made.
        self.assertEqual(
            client.models.generate_content.call_count,
            1,
        )

    # --------------------------------------------------
    # MISSING API KEY
    # --------------------------------------------------

    @patch.dict(
        "app.ai_service.os.environ",
        {},
        clear=True,
    )
    def test_missing_key_is_configuration_error(self):
        with self.assertRaises(AIConfigurationError):
            analyze_plant(
                "Basil",
                "Herb",
                None,
                "Yellow leaves",
            )

    # --------------------------------------------------
    # INVALID JSON
    # --------------------------------------------------

    @patch("app.ai_service.genai.Client")
    @patch.dict(
        "app.ai_service.os.environ",
        {"GEMINI_API_KEY": "test-key"},
        clear=False,
    )
    def test_invalid_json_is_rejected(
        self,
        client_factory,
    ):
        client = Mock()

        client.models.generate_content.return_value = (
            SimpleNamespace(text="not json")
        )

        client_factory.return_value = client

        with self.assertRaises(InvalidAIResponseError):
            analyze_plant(
                "Basil",
                "Herb",
                None,
                "Yellow leaves",
            )

    # --------------------------------------------------
    # MISSING REQUIRED JSON FIELD
    # --------------------------------------------------

    @patch("app.ai_service.genai.Client")
    @patch.dict(
        "app.ai_service.os.environ",
        {"GEMINI_API_KEY": "test-key"},
        clear=False,
    )
    def test_missing_expert_flag_is_rejected(
        self,
        client_factory,
    ):
        response_data = valid_ai_response()
        del response_data["expert_advice_needed"]

        client = Mock()

        client.models.generate_content.side_effect = [
            mock_json_response(valid_input_response()),
            mock_json_response(response_data),
        ]

        client_factory.return_value = client

        with self.assertRaises(InvalidAIResponseError):
            analyze_plant(
                "Basil",
                "Herb",
                None,
                "Yellow leaves",
            )

    # --------------------------------------------------
    # INVALID CARE SUGGESTIONS
    # --------------------------------------------------

    @patch("app.ai_service.genai.Client")
    @patch.dict(
        "app.ai_service.os.environ",
        {"GEMINI_API_KEY": "test-key"},
        clear=False,
    )
    def test_invalid_suggestions_are_rejected(
        self,
        client_factory,
    ):
        response_data = valid_ai_response()

        response_data["care_suggestions"] = [
            "Water carefully."
        ]

        client = Mock()

        client.models.generate_content.side_effect = [
            mock_json_response(valid_input_response()),
            mock_json_response(response_data),
        ]

        client_factory.return_value = client

        with self.assertRaises(InvalidAIResponseError):
            analyze_plant(
                "Basil",
                "Herb",
                None,
                "Yellow leaves",
            )

    # --------------------------------------------------
    # EMPTY GEMINI RESPONSE
    # --------------------------------------------------

    @patch("app.ai_service.genai.Client")
    @patch.dict(
        "app.ai_service.os.environ",
        {"GEMINI_API_KEY": "test-key"},
        clear=False,
    )
    def test_empty_response_is_rejected(
        self,
        client_factory,
    ):
        client = Mock()

        client.models.generate_content.return_value = (
            SimpleNamespace(text="")
        )

        client_factory.return_value = client

        with self.assertRaises(InvalidAIResponseError):
            analyze_plant(
                "Basil",
                "Herb",
                None,
                "Yellow leaves",
            )

    # --------------------------------------------------
    # API ENDPOINT ERROR HANDLING
    # --------------------------------------------------

    def test_endpoint_maps_safe_errors(self):
        client = TestClient(app)

        payload = {
            "plant_name": "Basil",
            "plant_type": "Herb",
            "symptoms": "Yellow leaves",
        }

        cases = [
            (AIRateLimitError(), 429),
            (AITimeoutError(), 504),
            (AINetworkError(), 503),
            (InvalidAIResponseError(), 502),
            (AIAuthenticationError(), 503),
            (AIConfigurationError(), 503),
            (InvalidPlantInputError(), 422),
        ]

        for error, status_code in cases:
            with self.subTest(
                error=type(error).__name__
            ):
                with patch(
                    "app.main.analyze_plant",
                    side_effect=error,
                ):
                    response = client.post(
                        "/api/analyze",
                        json=payload,
                    )

                    self.assertEqual(
                        response.status_code,
                        status_code,
                    )

                    self.assertEqual(
                        response.json()["detail"],
                        error.public_message,
                    )

    # --------------------------------------------------
    # SUCCESSFUL API RESPONSE STRUCTURE
    # --------------------------------------------------

    def test_endpoint_returns_structured_json(self):
        client = TestClient(app)

        response_data = {
            **valid_ai_response(
                expert_advice_needed=True
            ),
            "demo": False,
        }

        with patch(
            "app.main.analyze_plant",
            return_value=response_data,
        ):
            response = client.post(
                "/api/analyze",
                json={
                    "plant_name": "Tomato",
                    "plant_type": "Vegetable",
                    "location": "Jaffna",
                    "symptoms": "Brown spots on leaves",
                },
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        body = response.json()

        self.assertEqual(
            body["possible_issue"],
            "Overwatering stress",
        )

        self.assertEqual(
            len(body["care_suggestions"]),
            3,
        )

        self.assertIs(
            body["expert_advice_needed"],
            True,
        )

        self.assertIs(
            body["demo"],
            False,
        )


if __name__ == "__main__":
    unittest.main()
