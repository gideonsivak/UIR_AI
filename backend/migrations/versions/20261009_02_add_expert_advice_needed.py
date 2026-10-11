
"""Add expert_advice_needed to plant analyses.

Revision ID: 20261009_02
Revises: 20261009_01
Create Date: 2026-10-09
"""

from alembic import op
import sqlalchemy as sa


revision = "20261009_02"
down_revision = "20261009_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plant_analyses",
        sa.Column(
            "expert_advice_needed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "plant_analyses",
        "expert_advice_needed",
    )
