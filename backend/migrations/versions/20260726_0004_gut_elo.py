"""Create the Phase 2B Gut ELO tables.

Revision ID: 20260726_0004
Revises: 20260726_0003
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0004"
down_revision: str | None = "20260726_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gut_elo_session",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("board_id", sa.String(length=36), nullable=False),
        sa.Column("queue_mode", sa.String(length=16), nullable=False),
        sa.Column("position", sa.String(length=16), nullable=True),
        sa.Column("tier_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.Column("completed_at", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(
            ["board_id"],
            ["personal_board.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_gut_elo_session_board_updated",
        "gut_elo_session",
        ["board_id", "updated_at"],
    )

    op.create_table(
        "gut_elo_participant",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("player_id", sa.String(length=36), nullable=False),
        sa.Column("starting_manual_rank", sa.Integer(), nullable=False),
        sa.Column("starting_tier_name", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["gut_elo_session.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["player_id"], ["player.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "player_id",
            name="uq_gut_elo_participant_player",
        ),
    )
    op.create_index(
        "ix_gut_elo_participant_session_rank",
        "gut_elo_participant",
        ["session_id", "starting_manual_rank"],
    )
    op.create_index(
        "ix_gut_elo_participant_player",
        "gut_elo_participant",
        ["player_id"],
    )

    op.create_table(
        "gut_elo_action",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("player_a_id", sa.String(length=36), nullable=False),
        sa.Column("player_b_id", sa.String(length=36), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("undone_at", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["gut_elo_session.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["player_a_id"], ["player.id"]),
        sa.ForeignKeyConstraint(["player_b_id"], ["player.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "sequence_number",
            name="uq_gut_elo_action_sequence",
        ),
    )
    op.create_index(
        "ix_gut_elo_action_session_sequence",
        "gut_elo_action",
        ["session_id", "sequence_number"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_gut_elo_action_session_sequence",
        table_name="gut_elo_action",
    )
    op.drop_table("gut_elo_action")
    op.drop_index(
        "ix_gut_elo_participant_player",
        table_name="gut_elo_participant",
    )
    op.drop_index(
        "ix_gut_elo_participant_session_rank",
        table_name="gut_elo_participant",
    )
    op.drop_table("gut_elo_participant")
    op.drop_index(
        "ix_gut_elo_session_board_updated",
        table_name="gut_elo_session",
    )
    op.drop_table("gut_elo_session")
