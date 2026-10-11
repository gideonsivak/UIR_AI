
"""Safe, reusable error handling for Gemini AI provider calls."""

import logging
import re

import httpx


# --------------------------------------------------
# BASE AI ERROR
# --------------------------------------------------

class AIServiceError(Exception):
    """Base exception for AI service failures."""

    status_code = 503
    public_message = (
        "Plant analysis is temporarily unavailable. "
        "Please try again later."
    )
    log_level = logging.ERROR


# --------------------------------------------------
# API KEY / CONFIGURATION ERRORS
# --------------------------------------------------

class AIConfigurationError(AIServiceError):
    """Raised when Gemini API configuration is missing."""

    status_code = 503
    public_message = (
        "AI analysis is not configured. "
        "Please contact the application administrator."
    )


class AIAuthenticationError(AIServiceError):
    """Raised when Gemini rejects the API credentials."""

    status_code = 503
    public_message = (
        "AI analysis is temporarily unavailable. "
        "Please try again later."
    )


# --------------------------------------------------
# RATE LIMIT / QUOTA ERROR
# --------------------------------------------------

class AIRateLimitError(AIServiceError):
    """Raised when Gemini rate limits or quota limits are reached."""

    status_code = 429
    public_message = (
        "AI analysis is busy. "
        "Please wait a moment and try again."
    )
    log_level = logging.WARNING


# --------------------------------------------------
# TIMEOUT ERROR
# --------------------------------------------------

class AITimeoutError(AIServiceError):
    """Raised when the Gemini request takes too long."""

    status_code = 504
    public_message = (
        "AI analysis took too long. "
        "Please try again."
    )
    log_level = logging.WARNING


# --------------------------------------------------
# NETWORK ERROR
# --------------------------------------------------

class AINetworkError(AIServiceError):
    """Raised when a network or HTTP transport error occurs."""

    status_code = 503
    public_message = (
        "AI analysis is temporarily unavailable. "
        "Please try again later."
    )
    log_level = logging.WARNING


# --------------------------------------------------
# INVALID AI RESPONSE ERROR
# --------------------------------------------------

class InvalidAIResponseError(AIServiceError):
    """Raised when Gemini returns invalid JSON or invalid fields."""

    status_code = 502
    public_message = (
        "AI analysis returned an invalid response. "
        "Please try again."
    )


# --------------------------------------------------
# GENERAL PROVIDER ERROR
# --------------------------------------------------

class AIProviderError(AIServiceError):
    """Raised for other unexpected Gemini provider failures."""

    status_code = 502
    public_message = (
        "AI analysis is temporarily unavailable. "
        "Please try again later."
    )


# --------------------------------------------------
# SAFE ERROR MESSAGE
# --------------------------------------------------

def safe_error_message(
    exc: Exception,
    api_key: str | None = None,
) -> str:
    """Remove sensitive credentials from error diagnostics."""

    message = str(exc)

    # Redact the currently configured API key.
    if api_key:
        message = message.replace(api_key, "[REDACTED]")

    # Redact Google-style API keys.
    message = re.sub(
        r"AIza[\w-]{20,}",
        "[REDACTED]",
        message,
    )

    # Redact API keys appearing as key=value or key: value.
    message = re.sub(
        r"(?i)(api[_-]?key\s*[=:]\s*)\S+",
        r"\1[REDACTED]",
        message,
    )

    # Redact authorization bearer tokens.
    message = re.sub(
        r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+",
        r"\1[REDACTED]",
        message,
    )

    # Keep logs short.
    return message[:500]


# --------------------------------------------------
# CLASSIFY GEMINI / HTTP ERRORS
# --------------------------------------------------

def classify_provider_error(exc: Exception) -> AIServiceError:
    """Convert provider failures into safe application exceptions."""

    # Preserve known application errors.
    if isinstance(exc, AIServiceError):
        return exc

    # Timeout errors.
    if isinstance(exc, httpx.TimeoutException):
        return AITimeoutError(
            "Gemini request timed out"
        )

    # Network and other transport errors.
    if isinstance(exc, httpx.TransportError):
        return AINetworkError(
            "Gemini network request failed"
        )

    # Google SDK errors may expose code or status_code.
    provider_status = getattr(exc, "code", None)

    if provider_status is None:
        provider_status = getattr(exc, "status_code", None)

    try:
        provider_status = int(provider_status)
    except (TypeError, ValueError):
        provider_status = None

    provider_detail = str(exc).lower()

    # Detect invalid API key messages.
    invalid_key_message = (
        "api key" in provider_detail
        and any(
            marker in provider_detail
            for marker in (
                "invalid",
                "not valid",
                "authentication",
                "expired",
            )
        )
    )

    # Authentication / permission errors.
    if provider_status in {401, 403} or invalid_key_message:
        return AIAuthenticationError(
            "Gemini authentication failed"
        )

    # Rate limit or quota exceeded.
    if provider_status == 429:
        return AIRateLimitError(
            "Gemini quota or rate limit reached"
        )

    # Provider timeout.
    if provider_status in {408, 504}:
        return AITimeoutError(
            "Gemini provider request timed out"
        )

    # General provider error.
    return AIProviderError(
        "Gemini provider request failed"
    )


# --------------------------------------------------
# SAFE ERROR LOGGING
# --------------------------------------------------

def log_ai_error(
    logger: logging.Logger,
    error: AIServiceError,
    cause: Exception | None,
    api_key: str | None,
) -> None:
    """Log redacted diagnostics without exposing secrets to API clients."""

    detail = safe_error_message(
        cause if cause is not None else error,
        api_key,
    )

    logger.log(
        error.log_level,
        "AI analysis failed (%s): %s",
        type(error).__name__,
        detail,
    )
