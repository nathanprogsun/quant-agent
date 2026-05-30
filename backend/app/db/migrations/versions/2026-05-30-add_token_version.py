"""add token_version column

Revision ID: add_token_version
Revises: 5ed61ff7bdb1
Create Date: 2026-05-30

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "add_token_version"
down_revision = "5ed61ff7bdb1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("token_version", sa.Integer(), default=0, nullable=False))


def downgrade() -> None:
    op.drop_column("users", "token_version")
