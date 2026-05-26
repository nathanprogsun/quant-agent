"""Create threads and runs table

Revision ID: 5ed61ff7bdb1
Revises: a0f9617d90dd
Create Date: 2026-05-26 14:51:52.175959

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "5ed61ff7bdb1"
down_revision = "a0f9617d90dd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create threads table
    op.create_table(
        "threads",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("model_name", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    # Create runs table
    op.create_table(
        "runs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=True),
        sa.Column("assistant_id", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("token_usage", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    # Indexes for threads
    op.create_index("ix_threads_user_id", "threads", ["user_id"])
    # Indexes for runs
    op.create_index("ix_runs_thread_id", "runs", ["thread_id"])
    op.create_index("ix_runs_user_id", "runs", ["user_id"])
    op.create_index("ix_runs_status", "runs", ["status"])


def downgrade() -> None:
    # Drop runs indexes
    op.drop_index("ix_runs_status", "runs")
    op.drop_index("ix_runs_user_id", "runs")
    op.drop_index("ix_runs_thread_id", "runs")
    # Drop threads indexes
    op.drop_index("ix_threads_user_id", "threads")
    # Drop tables
    op.drop_table("runs")
    op.drop_table("threads")
