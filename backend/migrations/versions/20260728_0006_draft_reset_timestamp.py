"""Add the draft reset audit timestamp.

Revision ID: 20260728_0006
Revises: 20260726_0005
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0006"
down_revision: str | None = "20260726_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("draft_session", sa.Column("reset_at", sa.String(32)))


def downgrade() -> None:
    op.drop_column("draft_session", "reset_at")
