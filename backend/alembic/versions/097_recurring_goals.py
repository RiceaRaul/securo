"""goals that repeat every month

A recurring goal is a template ("put the rent aside, 500 EUR, from the
10th") that produces one ordinary goal per period. The instances are rows
in `goals`, so the goals list, the dashboard widget and search keep working
on them unchanged; they only gain a link back to the template and the
period they cover.

  - `recurring_goals`: the template, with `next_period_start` as the
    cursor the hourly job advances.
  - `goals.recurring_goal_id`, `period_start`, `period_end`: set on
    instances only. Unique per (template, period_start), so a period can
    never be generated twice. Deleting a template without its history
    leaves the instances behind as plain goals (SET NULL).

Revision ID: 097
Revises: 096
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "097"
down_revision = "096"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recurring_goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("target_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("start_day", sa.Integer(), nullable=False),
        sa.Column("icon", sa.String(length=50), nullable=True),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_period_start", sa.Date(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("start_day BETWEEN 1 AND 31", name="ck_recurring_goals_start_day"),
    )
    op.create_index("ix_recurring_goals_workspace_id", "recurring_goals", ["workspace_id"])

    op.add_column(
        "goals", sa.Column("recurring_goal_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("goals", sa.Column("period_start", sa.Date(), nullable=True))
    op.add_column("goals", sa.Column("period_end", sa.Date(), nullable=True))
    op.create_foreign_key(
        "goals_recurring_goal_id_fkey",
        "goals",
        "recurring_goals",
        ["recurring_goal_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_goals_recurring_goal_id", "goals", ["recurring_goal_id"])
    op.create_unique_constraint(
        "uq_goals_recurring_period", "goals", ["recurring_goal_id", "period_start"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_goals_recurring_period", "goals", type_="unique")
    op.drop_index("ix_goals_recurring_goal_id", table_name="goals")
    op.drop_constraint("goals_recurring_goal_id_fkey", "goals", type_="foreignkey")
    op.drop_column("goals", "period_end")
    op.drop_column("goals", "period_start")
    op.drop_column("goals", "recurring_goal_id")
    op.drop_index("ix_recurring_goals_workspace_id", table_name="recurring_goals")
    op.drop_table("recurring_goals")
