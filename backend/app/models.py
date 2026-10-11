
"""SQLAlchemy models preserving the API's existing string-ID data shape."""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
        ForeignKey("users.id", ondelete="CASCADE"),
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

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    plant_id: Mapped[str] = mapped_column(
        ForeignKey("plants.id", ondelete="CASCADE"),
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

    # NEW: Teacher's required Boolean field.
    # Existing records receive False during migration.
    expert_advice_needed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )

    plant: Mapped[Plant] = relationship(
        back_populates="analysis",
    )
