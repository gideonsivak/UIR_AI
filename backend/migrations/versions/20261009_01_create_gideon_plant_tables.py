"""create Gideon Plant MySQL tables

Revision ID: 20261009_01
Revises:
Create Date: 2026-10-09
"""

from alembic import op
import sqlalchemy as sa


revision = "20261009_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_table(
        "plants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("plant_name", sa.String(length=120), nullable=False),
        sa.Column("plant_type", sa.String(length=120), nullable=False),
        sa.Column("location", sa.String(length=160), nullable=True),
        sa.Column("symptom", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plants_user_id", "plants", ["user_id"], unique=False)
    op.create_table(
        "plant_analyses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plant_id", sa.String(length=36), nullable=False),
        sa.Column("possible_issue", sa.String(length=500), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("care_suggestions", sa.Text(), nullable=False),
        sa.Column("expert_advice", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plant_id"),
    )
    op.create_index("ix_plant_analyses_plant_id", "plant_analyses", ["plant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_plant_analyses_plant_id", table_name="plant_analyses")
    op.drop_table("plant_analyses")
    op.drop_index("ix_plants_user_id", table_name="plants")
    op.drop_table("plants")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
