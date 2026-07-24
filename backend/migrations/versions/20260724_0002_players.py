"""Create the Phase 1 canonical player and import-review tables.

Revision ID: 20260724_0002
Revises: 20260724_0001
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0002"
down_revision: str | None = "20260724_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "player",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("suffix", sa.String(length=16), nullable=True),
        sa.Column("search_name", sa.String(length=200), nullable=False),
        sa.Column("team", sa.String(length=8), nullable=True),
        sa.Column("primary_position", sa.String(length=16), nullable=False),
        sa.Column("fantasy_positions_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rookie_class", sa.Integer(), nullable=True),
        sa.Column("is_rookie", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_player_search_name", "player", ["search_name"])
    op.create_index(
        "ix_player_filters",
        "player",
        ["primary_position", "status", "rookie_class"],
    )

    op.create_table(
        "player_external_id",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("player_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("is_manual_override", sa.Boolean(), nullable=False),
        sa.Column("first_seen_at", sa.String(length=32), nullable=False),
        sa.Column("last_seen_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["player.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_id", name="uq_player_external_id"),
    )
    op.create_index("ix_player_external_player", "player_external_id", ["player_id"])

    op.create_table(
        "player_relevance",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("player_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("reference_id", sa.String(length=36), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["player.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "player_id",
            "reason",
            "reference_id",
            name="uq_player_relevance_reason",
        ),
    )
    op.create_index("ix_player_relevance_active", "player_relevance", ["active", "reason"])

    op.create_table(
        "player_import_session",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("filename", sa.String(length=200), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("new_count", sa.Integer(), nullable=False),
        sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("changed_count", sa.Integer(), nullable=False),
        sa.Column("ambiguous_count", sa.Integer(), nullable=False),
        sa.Column("invalid_count", sa.Integer(), nullable=False),
        sa.Column("ignored_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("committed_at", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_player_import_session_created",
        "player_import_session",
        ["created_at"],
    )

    op.create_table(
        "player_import_row",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_payload_json", sa.Text(), nullable=False),
        sa.Column("normalized_candidate_json", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("proposed_player_id", sa.String(length=36), nullable=True),
        sa.Column("resolved_player_id", sa.String(length=36), nullable=True),
        sa.Column("candidate_player_ids_json", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("explanation", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["player_import_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposed_player_id"], ["player.id"]),
        sa.ForeignKeyConstraint(["resolved_player_id"], ["player.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "row_number", name="uq_player_import_row_number"),
    )
    op.create_index("ix_player_import_row_session", "player_import_row", ["session_id"])

    op.create_table(
        "player_mapping_decision",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("import_row_id", sa.String(length=36), nullable=False),
        sa.Column("player_id", sa.String(length=36), nullable=True),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["import_row_id"], ["player_import_row.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_id"], ["player.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("import_row_id"),
    )


def downgrade() -> None:
    op.drop_table("player_mapping_decision")
    op.drop_index("ix_player_import_row_session", table_name="player_import_row")
    op.drop_table("player_import_row")
    op.drop_index("ix_player_import_session_created", table_name="player_import_session")
    op.drop_table("player_import_session")
    op.drop_index("ix_player_relevance_active", table_name="player_relevance")
    op.drop_table("player_relevance")
    op.drop_index("ix_player_external_player", table_name="player_external_id")
    op.drop_table("player_external_id")
    op.drop_index("ix_player_filters", table_name="player")
    op.drop_index("ix_player_search_name", table_name="player")
    op.drop_table("player")
