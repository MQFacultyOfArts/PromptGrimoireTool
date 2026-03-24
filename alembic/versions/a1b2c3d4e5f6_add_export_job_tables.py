"""add export job tables

Revision ID: a1b2c3d4e5f6
Revises: 7abc07630af3
Create Date: 2026-03-22 09:10:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "7abc07630af3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create export_job_status and export_job tables."""
    # Reference table
    op.create_table(
        "export_job_status",
        sa.Column("name", sa.String(20), primary_key=True, nullable=False),
        sa.Column("description", sa.String(100), nullable=False, server_default=""),
    )

    # Seed status values
    op.execute(
        sa.text(
            "INSERT INTO export_job_status (name, description) VALUES "
            "('queued', 'Job waiting to be picked up by worker'), "
            "('running', 'Job currently being processed'), "
            "('completed', 'Job finished successfully'), "
            "('failed', 'Job encountered an error')"
        )
    )

    # Main table
    op.create_table(
        "export_job",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(20),
            sa.ForeignKey("export_job_status.name", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("download_token", sa.String(64), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pdf_path", sa.String(500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes
    op.create_index("ix_export_job_user_id", "export_job", ["user_id"])
    op.create_index("ix_export_job_workspace_id", "export_job", ["workspace_id"])
    op.create_index("ix_export_job_status", "export_job", ["status"])
    op.create_index("ix_export_job_created_at", "export_job", ["created_at"])
    op.create_index(
        "ix_export_job_token_expires_at", "export_job", ["token_expires_at"]
    )

    # Unique index on download_token (partial: only non-NULL rows).
    # Required so get_job_by_token() never returns an ambiguous result on collision.
    op.create_index(
        "ix_export_job_download_token",
        "export_job",
        ["download_token"],
        unique=True,
        postgresql_where=sa.text("download_token IS NOT NULL"),
    )

    # Per-user concurrency enforcement: at most one queued/running job per user
    op.create_index(
        "ix_export_job_one_active_per_user",
        "export_job",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    """Drop export_job and export_job_status tables."""
    op.drop_index("ix_export_job_one_active_per_user", table_name="export_job")
    op.drop_index("ix_export_job_download_token", table_name="export_job")
    op.drop_index("ix_export_job_token_expires_at", table_name="export_job")
    op.drop_index("ix_export_job_created_at", table_name="export_job")
    op.drop_index("ix_export_job_status", table_name="export_job")
    op.drop_index("ix_export_job_workspace_id", table_name="export_job")
    op.drop_index("ix_export_job_user_id", table_name="export_job")
    op.drop_table("export_job")
    op.drop_table("export_job_status")
