
"""SQLAlchemy models preserving the API's existing string-ID data shape."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from .database import Base


# --------------------------------------------------
# USER MODEL
# --------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        unique=True,
        index=True,
    )

    created_at: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    updated_at: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    plants: Mapped[list["Plant"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


# --------------------------------------------------
# PLANT MODEL
# --------------------------------------------------

class Plant(Base):
    __tablename__ = "plants"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    plant_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    plant_type: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    location: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
    )

    symptom: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    updated_at: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    user: Mapped[User] = relationship(
        back_populates="plants",
    )

    analysis: Mapped["PlantAnalysis | None"] = relationship(
        back_populates="plant",
        cascade="all, delete-orphan",
        uselist=False,
    )


# --------------------------------------------------
# STRUCTURED PLANT AI ANALYSIS MODEL
# --------------------------------------------------

class PlantAnalysis(Base):
    __tablename__ = "plant_analyses"

    __table_args__ = (
        CheckConstraint(
            "ai_confidence IS NULL OR "
            "(ai_confidence >= 0 AND ai_confidence <= 100)",
            name="ck_plant_analyses_ai_confidence_range",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    plant_id: Mapped[str] = mapped_column(
        ForeignKey(
            "plants.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    possible_issue: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # JSON array stored as text.
    # Example: ["Check soil", "Improve drainage", "Monitor leaves"]
    care_suggestions: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    expert_advice: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Existing field — preserve old records and behavior.
    expert_advice_needed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )

    # --------------------------------------------------
    # NEW: AI SELF-ESTIMATED CONFIDENCE
    # --------------------------------------------------

    # NULL for legacy records without confidence.
    # Valid values: 0 through 100.
    ai_confidence: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # --------------------------------------------------
    # NEW: PLANT IMAGE MATCH STATUS
    # --------------------------------------------------

    # YES / NO / UNCERTAIN / NOT_CHECKED
    # Only completed, accepted diagnoses are saved.
    plant_match: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    # --------------------------------------------------
    # NEW: CATEGORY MATCH STATUS
    # --------------------------------------------------

    # YES / NO / UNCERTAIN
    category_match: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    # --------------------------------------------------
    # NEW: SMART INTERVIEW ANSWERS
    # --------------------------------------------------

    # JSON text example:
    # [
    #   {
    #     "question_id": "q1",
    #     "question": "How often do you water the plant?",
    #     "answer": "Every morning"
    #   }
    # ]
    #
    # NULL for analyses created without an interview.
    interview_answers: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    plant: Mapped[Plant] = relationship(
        back_populates="analysis",
    )
