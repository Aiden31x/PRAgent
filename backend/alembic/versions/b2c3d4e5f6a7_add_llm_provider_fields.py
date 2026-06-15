"""add llm provider fields to users and reviews

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-07 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users: store preferred LLM provider and model
    op.add_column(
        "users",
        sa.Column(
            "preferred_llm_provider",
            sa.String(length=50),
            nullable=False,
            server_default="gemini",
        ),
    )
    op.add_column(
        "users",
        sa.Column("preferred_llm_model", sa.String(length=100), nullable=True),
    )

    # Reviews: audit trail of which provider/model produced this review
    op.add_column(
        "reviews",
        sa.Column(
            "llm_provider",
            sa.String(length=50),
            nullable=False,
            server_default="gemini",
        ),
    )
    op.add_column(
        "reviews",
        sa.Column(
            "llm_model",
            sa.String(length=100),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("reviews", "llm_model")
    op.drop_column("reviews", "llm_provider")
    op.drop_column("users", "preferred_llm_model")
    op.drop_column("users", "preferred_llm_provider")
