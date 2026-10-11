
"""Add smart diagnosis fields to plant analyses.

Revision ID: 20261011_03
Revises: 20261009_02
"""

from alembic import op
import sqlalchemy as sa


# Alembic revision identifiers
revision = "20261011_03"
down_revision = "20261009_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable fields without deleting existing data."""

    op.add_column(
        "plant_analyses",
        sa.Column(
            "ai_confidence",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "plant_analyses",
        sa.Column(
            "plant_match",
            sa.String(length=20),
            nullable=True,
        ),
    )

    op.add_column(
        "plant_analyses",
        sa.Column(
            "category_match",
            sa.String(length=20),
            nullable=True,
        ),
    )

    op.add_column(
        "plant_analyses",
        sa.Column(
            "interview_answers",
            sa.Text(),
            nullable=True,
        ),
    )

    op.create_check_constraint(
        "ck_plant_analyses_ai_confidence_range",
        "plant_analyses",
        (
            "ai_confidence IS NULL OR "
            "(ai_confidence >= 0 AND ai_confidence <= 100)"
        ),
    )


def downgrade() -> None:
    """Remove the new fields if this migration is reversed."""

    op.drop_constraint(
        "ck_plant_analyses_ai_confidence_range",
        "plant_analyses",
        type_="check",
    )

    op.drop_column("plant_analyses", "interview_answers")
    op.drop_column("plant_analyses", "category_match")
    op.drop_column("plant_analyses", "plant_match")
    op.drop_column("plant_analyses", "ai_confidence")
