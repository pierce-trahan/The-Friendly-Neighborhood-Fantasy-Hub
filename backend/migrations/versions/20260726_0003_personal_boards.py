"""Create the Phase 2A personal board tables.

Revision ID: 20260726_0003
Revises: 20260724_0002
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0003"
down_revision: str | None = "20260724_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "personal_board",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("league_profile_id", sa.String(length=36), nullable=True),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["league_profile_id"],
            ["league_profile.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_personal_board_archived_updated",
        "personal_board",
        ["archived", "updated_at"],
    )

    op.create_table(
        "board_tier",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("board_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("tier_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["board_id"],
            ["personal_board.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("board_id", "name", name="uq_board_tier_name"),
    )
    op.create_index(
        "ix_board_tier_order",
        "board_tier",
        ["board_id", "tier_order"],
    )

    op.create_table(
        "board_entry",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("board_id", sa.String(length=36), nullable=False),
        sa.Column("player_id", sa.String(length=36), nullable=False),
        sa.Column("tier_id", sa.String(length=36), nullable=True),
        sa.Column("manual_order", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("favorite", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["board_id"],
            ["personal_board.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["player.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tier_id"],
            ["board_tier.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("board_id", "player_id", name="uq_board_entry_player"),
    )
    op.create_index(
        "ix_board_entry_active_order",
        "board_entry",
        ["board_id", "active", "manual_order"],
    )
    op.create_index("ix_board_entry_player", "board_entry", ["player_id"])


def downgrade() -> None:
    op.drop_index("ix_board_entry_player", table_name="board_entry")
    op.drop_index("ix_board_entry_active_order", table_name="board_entry")
    op.drop_table("board_entry")
    op.drop_index("ix_board_tier_order", table_name="board_tier")
    op.drop_table("board_tier")
    op.drop_index("ix_personal_board_archived_updated", table_name="personal_board")
    op.drop_table("personal_board")
