"""add wargame schema

Revision ID: 1b59ab790954
Revises: c08959d80031
Create Date: 2026-03-07 08:53:33.788510

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1b59ab790954"
down_revision: str | Sequence[str] | None = "c08959d80031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add wargame tables and extend activity/ACL polymorphism."""
    # Keep the server default in place so legacy rows upgrade to annotation
    # without a separate backfill, and schema-only annotation creation remains valid.
    op.add_column(
        "activity",
        sa.Column(
            "type",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'annotation'"),
        ),
    )
    op.alter_column(
        "activity", "template_workspace_id", existing_type=sa.Uuid(), nullable=True
    )
    op.create_check_constraint(
        "ck_activity_type_known",
        "activity",
        "type IN ('annotation', 'wargame')",
    )
    op.create_check_constraint(
        "ck_activity_annotation_requires_template",
        "activity",
        "type != 'annotation' OR template_workspace_id IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_activity_wargame_no_template",
        "activity",
        "type != 'wargame' OR template_workspace_id IS NULL",
    )
    op.create_unique_constraint(
        "uq_activity_id_type",
        "activity",
        ["id", "type"],
    )

    op.create_table(
        "wargame_config",
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "activity_type",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'wargame'"),
        ),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("scenario_bootstrap", sa.Text(), nullable=False),
        sa.Column("timer_delta", sa.Interval(), nullable=True),
        sa.Column("timer_wall_clock", sa.Time(), nullable=True),
        sa.ForeignKeyConstraint(
            ["activity_id", "activity_type"],
            ["activity.id", "activity.type"],
            name="fk_wargame_config_activity_wargame",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("activity_id"),
        sa.CheckConstraint(
            "activity_type = 'wargame'",
            name="ck_wargame_config_activity_type",
        ),
        sa.CheckConstraint(
            "num_nonnulls(timer_delta, timer_wall_clock) = 1",
            name="ck_wargame_config_timer_exactly_one",
        ),
    )

    op.create_table(
        "wargame_team",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "activity_type",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'wargame'"),
        ),
        sa.Column("codename", sa.String(length=100), nullable=False),
        sa.Column(
            "current_round",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "round_state",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'drafting'"),
        ),
        sa.Column("current_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("game_state_text", sa.Text(), nullable=True),
        sa.Column("student_summary_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_id", "activity_type"],
            ["activity.id", "activity.type"],
            name="fk_wargame_team_activity_wargame",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "activity_type = 'wargame'",
            name="ck_wargame_team_activity_type",
        ),
        sa.UniqueConstraint(
            "activity_id",
            "codename",
            name="uq_wargame_team_activity_codename",
        ),
    )
    op.create_index("ix_wargame_team_activity_id", "wargame_team", ["activity_id"])

    op.create_table(
        "wargame_message",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("thinking", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["wargame_team.id"],
            name="fk_wargame_message_team_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "team_id",
            "sequence_no",
            name="uq_wargame_message_team_sequence",
        ),
    )
    op.create_index("ix_wargame_message_team_id", "wargame_message", ["team_id"])

    op.add_column("acl_entry", sa.Column("team_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_acl_entry_team_id",
        "acl_entry",
        "wargame_team",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("acl_entry", "workspace_id", existing_type=sa.Uuid(), nullable=True)
    op.create_check_constraint(
        "ck_acl_entry_exactly_one_target",
        "acl_entry",
        "num_nonnulls(workspace_id, team_id) = 1",
    )
    # Team-target ACL rows satisfy num_nonnulls(workspace_id, team_id) = 1
    # with workspace_id NULL, so workspace and team uniqueness need separate
    # partial indexes instead of one nullable composite UNIQUE constraint.
    op.drop_constraint("uq_acl_entry_workspace_user", "acl_entry", type_="unique")
    op.create_index(
        "uq_acl_entry_workspace_user",
        "acl_entry",
        ["workspace_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("workspace_id IS NOT NULL"),
    )
    op.create_index(
        "uq_acl_entry_team_user",
        "acl_entry",
        ["team_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("team_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove wargame tables and ACL/activity polymorphism changes."""
    # Reverse later-phase objects before restoring the legacy activity shape.
    op.drop_index("uq_acl_entry_team_user", table_name="acl_entry")
    op.drop_index("uq_acl_entry_workspace_user", table_name="acl_entry")
    op.drop_constraint("ck_acl_entry_exactly_one_target", "acl_entry", type_="check")

    # Team-target ACL rows satisfy num_nonnulls(workspace_id, team_id) = 1
    # with workspace_id NULL, so downgrade must delete them before restoring
    # the legacy workspace_id NOT NULL shape.
    op.execute("DELETE FROM acl_entry WHERE workspace_id IS NULL")

    op.drop_constraint("fk_acl_entry_team_id", "acl_entry", type_="foreignkey")
    op.drop_column("acl_entry", "team_id")
    op.alter_column(
        "acl_entry", "workspace_id", existing_type=sa.Uuid(), nullable=False
    )
    op.create_unique_constraint(
        "uq_acl_entry_workspace_user",
        "acl_entry",
        ["workspace_id", "user_id"],
    )

    op.drop_index("ix_wargame_message_team_id", table_name="wargame_message")
    op.drop_table("wargame_message")
    op.drop_index("ix_wargame_team_activity_id", table_name="wargame_team")
    op.drop_table("wargame_team")
    op.drop_table("wargame_config")

    # Destructive downgrade: wargame activities cannot satisfy the legacy
    # NOT NULL template constraint, so they must be removed before rollback.
    op.execute("DELETE FROM activity WHERE type = 'wargame'")

    op.drop_constraint(
        "ck_activity_type_known",
        "activity",
        type_="check",
    )
    op.drop_constraint(
        "ck_activity_wargame_no_template",
        "activity",
        type_="check",
    )
    op.drop_constraint(
        "ck_activity_annotation_requires_template",
        "activity",
        type_="check",
    )
    op.drop_constraint(
        "uq_activity_id_type",
        "activity",
        type_="unique",
    )
    op.alter_column(
        "activity", "template_workspace_id", existing_type=sa.Uuid(), nullable=False
    )
    op.drop_column("activity", "type")
