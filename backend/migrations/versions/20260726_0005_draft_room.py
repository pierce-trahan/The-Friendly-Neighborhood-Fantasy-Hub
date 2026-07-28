"""Create the Phase 3 draft room tables.

Revision ID: 20260726_0005
Revises: 20260726_0004
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0005"
down_revision: str | None = "20260726_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "draft_session",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("board_id", sa.String(36), nullable=False),
        sa.Column("league_profile_id", sa.String(36)),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("draft_format", sa.String(16), nullable=False),
        sa.Column("third_round_reversal", sa.Boolean(), nullable=False),
        sa.Column("team_count", sa.Integer(), nullable=False),
        sa.Column("round_count", sa.Integer(), nullable=False),
        sa.Column("user_slot", sa.Integer(), nullable=False),
        sa.Column("pick_timer_seconds", sa.Integer()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("reset_from_session_id", sa.String(36)),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("completed_at", sa.String(32)),
        sa.ForeignKeyConstraint(["board_id"], ["personal_board.id"]),
        sa.ForeignKeyConstraint(
            ["league_profile_id"], ["league_profile.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reset_from_session_id"], ["draft_session.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_draft_session_board_updated",
        "draft_session",
        ["board_id", "updated_at"],
    )

    op.create_table(
        "draft_team",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("draft_slot", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("is_user", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["draft_session.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("session_id", "draft_slot", name="uq_draft_team_slot"),
    )
    op.create_index("ix_draft_team_session", "draft_team", ["session_id"])

    op.create_table(
        "draft_candidate",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("player_id", sa.String(36), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("search_name", sa.String(200), nullable=False),
        sa.Column("primary_position", sa.String(16), nullable=False),
        sa.Column("fantasy_positions_json", sa.Text(), nullable=False),
        sa.Column("team", sa.String(8)),
        sa.Column("player_status", sa.String(16), nullable=False),
        sa.Column("is_rookie", sa.Boolean(), nullable=False),
        sa.Column("rookie_class", sa.Integer()),
        sa.Column("snapshot_source", sa.String(24), nullable=False),
        sa.Column("manual_rank", sa.Integer()),
        sa.Column("tier_name", sa.String(80)),
        sa.Column("tier_color", sa.String(32)),
        sa.Column("tier_order", sa.Integer()),
        sa.Column("favorite", sa.Boolean(), nullable=False),
        sa.Column("board_note", sa.Text()),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["draft_session.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["player_id"], ["player.id"]),
        sa.UniqueConstraint(
            "session_id", "player_id", name="uq_draft_candidate_player"
        ),
    )
    op.create_index(
        "ix_draft_candidate_session_available",
        "draft_candidate",
        ["session_id", "search_name", "primary_position"],
    )
    op.create_index("ix_draft_candidate_player", "draft_candidate", ["player_id"])

    op.create_table(
        "draft_pick",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("overall_pick", sa.Integer(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("pick_in_round", sa.Integer(), nullable=False),
        sa.Column("selecting_slot", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.String(36)),
        sa.Column("recorded_at", sa.String(32)),
        sa.Column("client_entered_at", sa.String(64)),
        sa.Column("correction_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["draft_session.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["player_id"], ["player.id"]),
        sa.UniqueConstraint(
            "session_id", "overall_pick", name="uq_draft_pick_overall"
        ),
        sa.UniqueConstraint("session_id", "player_id", name="uq_draft_pick_player"),
    )
    op.create_index(
        "ix_draft_pick_session_overall",
        "draft_pick",
        ["session_id", "overall_pick"],
    )

    op.create_table(
        "draft_pick_revision",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("pick_id", sa.String(36), nullable=False),
        sa.Column("session_revision", sa.Integer(), nullable=False),
        sa.Column("action_kind", sa.String(16), nullable=False),
        sa.Column("previous_player_id", sa.String(36)),
        sa.Column("next_player_id", sa.String(36)),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["draft_session.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["pick_id"], ["draft_pick.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["previous_player_id"], ["player.id"]),
        sa.ForeignKeyConstraint(["next_player_id"], ["player.id"]),
        sa.UniqueConstraint(
            "session_id",
            "session_revision",
            name="uq_draft_pick_revision",
        ),
    )
    op.create_index(
        "ix_draft_pick_revision_session",
        "draft_pick_revision",
        ["session_id", "session_revision"],
    )


def downgrade() -> None:
    op.drop_table("draft_pick_revision")
    op.drop_table("draft_pick")
    op.drop_table("draft_candidate")
    op.drop_table("draft_team")
    op.drop_table("draft_session")
