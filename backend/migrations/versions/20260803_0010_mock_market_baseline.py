"""Freeze market baseline evidence on new mock sessions.

Revision ID: 20260803_0010
Revises: 20260729_0009
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0010"
down_revision: str | None = "20260729_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("draft_candidate") as batch_op:
        batch_op.add_column(sa.Column("market_rank", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "ck_draft_candidate_market_rank",
            "market_rank IS NULL OR market_rank >= 1",
        )
    with op.batch_alter_table("mock_configuration") as batch_op:
        batch_op.add_column(sa.Column("market_baseline_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("mock_configuration") as batch_op:
        batch_op.drop_column("market_baseline_json")
    with op.batch_alter_table("draft_candidate") as batch_op:
        batch_op.drop_constraint("ck_draft_candidate_market_rank", type_="check")
        batch_op.drop_column("market_rank")

