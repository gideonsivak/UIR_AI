
"""Pydantic request and response schemas for GIDEON PLANT."""

import re

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


# --------------------------------------------------
# VALIDATION CONSTANTS
# --------------------------------------------------

_PLACEHOLDER_VALUES = {
    "-",
    "?",
    "n/a",
    "na",
    "none",
    "unknown",
    "not sure",
    "test",
    "testing",
    "asdf",
    "asdasd",
    "sdfsdfs",
    "qwerty",
    "abc",
    "abcd",
    "xxx",
}

_ABSOLUTELY_DRY_SOIL = re.compile(
    r"\b(?:bone[- ]dry|completely dry|totally dry)\b",
    re.IGNORECASE,
)

_ABSOLUTELY_WET_SOIL = re.compile(
    r"\b(?:waterlogged|soaking wet|sopping wet|completely saturated)\b",
    re.IGNORECASE,
)

_KEYBOARD_MASH = re.compile(
    r"(?:asdf|qwer|zxcv|hjkl|sdfg|dfgh|fghj)",
    re.IGNORECASE,
)

_REPEATED_CHARACTER = re.compile(
    r"(.)\1{4,}",
    re.IGNORECASE,
)


def validate_meaningful_text(
    value: str,
    label: str,
) -> str:
    """Reject obvious placeholder and keyboard-mash input."""

    cleaned = " ".join(value.split())

    if not cleaned:
        raise ValueError(
            f"Please provide a {label}."
        )

    if cleaned.casefold() in _PLACEHOLDER_VALUES:
        raise ValueError(
            f"Please provide a specific {label} "
            "instead of a placeholder."
        )

    if not any(char.isalpha() for char in cleaned):
        raise ValueError(
            f"Please provide a descriptive {label} "
            "using letters."
        )

    if _KEYBOARD_MASH.search(cleaned):
        raise ValueError(
            f"The {label} appears to contain random text. "
            "Please enter meaningful plant information."
        )

    if _REPEATED_CHARACTER.search(cleaned):
        raise ValueError(
            f"The {label} appears to contain repeated characters. "
            "Please enter meaningful plant information."
        )

    return cleaned


# --------------------------------------------------
# 1. PLANT ANALYSIS REQUEST
# --------------------------------------------------

class AnalyzeRequest(BaseModel):
    plant_name: str = Field(min_length=1, max_length=120)
    plant_type: str = Field(min_length=1, max_length=120)
    location: str | None = Field(
        default=None,
        max_length=160,
    )
    symptoms: str = Field(min_length=1, max_length=2000)

    @field_validator(
        "plant_name",
        "plant_type",
        "symptoms",
    )
    @classmethod
    def required_analysis_text(
        cls,
        value: str,
        info,
    ) -> str:
        labels = {
            "plant_name": "plant name",
            "plant_type": "plant type",
            "symptoms": "reported symptoms",
        }

        return validate_meaningful_text(
            value,
            labels[info.field_name],
        )

    @field_validator("location")
    @classmethod
    def clean_analysis_location(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return " ".join(value.split()) or None

    @model_validator(mode="after")
    def symptoms_must_not_conflict(self):
        if (
            _ABSOLUTELY_DRY_SOIL.search(self.symptoms)
            and _ABSOLUTELY_WET_SOIL.search(self.symptoms)
        ):
            raise ValueError(
                "Your symptoms describe soil as both completely dry "
                "and waterlogged. Please clarify its current condition."
            )

        return self


# --------------------------------------------------
# 2. STRUCTURED AI RESULT
# --------------------------------------------------

class PlantAIResult(BaseModel):
    """Structured AI result required by the teacher's lesson."""

    possible_issue: str = Field(
        min_length=1,
        max_length=500,
    )

    explanation: str = Field(
        min_length=1,
        max_length=3000,
    )

    care_suggestions: list[str] = Field(
        min_length=3,
        max_length=3,
    )

    # Existing field: preserve API compatibility.
    expert_advice: str = Field(
        min_length=1,
        max_length=1500,
    )

    # Default False supports older saved analyses.
    expert_advice_needed: bool = False

    @field_validator(
        "possible_issue",
        "explanation",
        "expert_advice",
    )
    @classmethod
    def analysis_text_not_blank(
        cls,
        value: str,
    ) -> str:
        cleaned = value.strip()

        if not cleaned:
            raise ValueError(
                "Analysis text cannot be blank"
            )

        return cleaned

    @field_validator("care_suggestions")
    @classmethod
    def validate_care_suggestions(
        cls,
        values: list[str],
    ) -> list[str]:
        cleaned = [
            item.strip()
            for item in values
        ]

        if any(not item for item in cleaned):
            raise ValueError(
                "Care suggestions cannot contain blank items"
            )

        return cleaned


# --------------------------------------------------
# 3. AI ANALYSIS RESPONSE
# --------------------------------------------------

class AnalyzeResponse(PlantAIResult):
    """Response for POST /api/analyze."""

    demo: bool = True


# --------------------------------------------------
# 4. PEOPLE / USER SCHEMAS
# --------------------------------------------------

class UserCreate(BaseModel):
    name: str = Field(max_length=120)
    email: EmailStr

    @field_validator("name")
    @classmethod
    def name_not_blank(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError(
                "Name cannot be empty"
            )

        return value.strip()


class UserUpdate(UserCreate):
    pass


class UserResponse(UserCreate):
    id: str
    created_at: str
    updated_at: str


# --------------------------------------------------
# 5. SAVED PLANT ANALYSIS
# --------------------------------------------------

class PlantAnalysis(PlantAIResult):
    """Structured analysis stored with a saved plant."""

    pass


# --------------------------------------------------
# 6. PLANT SCHEMAS
# --------------------------------------------------

class PlantBase(BaseModel):
    user_id: str = Field(min_length=1)

    plant_name: str = Field(max_length=120)
    plant_type: str = Field(max_length=120)

    location: str | None = Field(
        default=None,
        max_length=160,
    )

    symptom: str = Field(max_length=2000)

    analysis: PlantAnalysis | None = None

    @field_validator(
        "plant_name",
        "plant_type",
        "symptom",
    )
    @classmethod
    def required_text_not_blank(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError(
                "This field cannot be empty"
            )

        return value.strip()

    @field_validator("location")
    @classmethod
    def clean_location(
        cls,
        value: str | None,
    ) -> str | None:
        return value.strip() or None if value else None


class PlantCreate(PlantBase):
    pass


class PlantUpdate(PlantBase):
    pass


class PlantResponse(PlantBase):
    id: str
    created_at: str
    updated_at: str
