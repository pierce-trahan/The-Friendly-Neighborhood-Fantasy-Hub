"""Create the Phase 6 post-draft report persistence tables.

Revision ID: 20260729_0009
Revises: 20260728_0008
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0009"
down_revision: str | None = "20260728_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "post_draft_report",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("draft_session_id", sa.String(36), nullable=False),
        sa.Column("draft_revision", sa.Integer(), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("league_shape_fingerprint", sa.String(64), nullable=False),
        sa.Column("report_engine_version", sa.String(64), nullable=False),
        sa.Column("report_rules_version", sa.String(64), nullable=False),
        sa.Column("explanation_template_version", sa.String(64), nullable=False),
        sa.Column("draft_mode", sa.String(16), nullable=False),
        sa.Column("generated_at", sa.String(32), nullable=False),
        sa.Column("completed_at", sa.String(32), nullable=False),
        sa.Column("section_summary_json", sa.Text(), nullable=False),
        sa.Column("limitation_codes_json", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "draft_revision >= 0",
            name="ck_post_draft_report_revision",
        ),
        sa.CheckConstraint(
            "length(input_fingerprint) = 64 "
            "AND input_fingerprint NOT GLOB '*[^0-9a-f]*'",
            name="ck_post_draft_report_input_fingerprint",
        ),
        sa.CheckConstraint(
            "length(league_shape_fingerprint) = 64 "
            "AND league_shape_fingerprint NOT GLOB '*[^0-9a-f]*'",
            name="ck_post_draft_report_league_fingerprint",
        ),
        sa.CheckConstraint(
            "length(report_engine_version) BETWEEN 1 AND 64 "
            "AND length(report_rules_version) BETWEEN 1 AND 64 "
            "AND length(explanation_template_version) BETWEEN 1 AND 64",
            name="ck_post_draft_report_versions",
        ),
        sa.CheckConstraint(
            "draft_mode IN ('live', 'mock')",
            name="ck_post_draft_report_mode",
        ),
        sa.CheckConstraint(
            "json_valid(section_summary_json) = 1 "
            "AND json_valid(limitation_codes_json) = 1",
            name="ck_post_draft_report_json",
        ),
        sa.ForeignKeyConstraint(
            ["draft_session_id"],
            ["draft_session.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "draft_session_id",
            "input_fingerprint",
            name="uq_post_draft_report_draft_fingerprint",
        ),
    )
    op.create_index(
        "ix_post_draft_report_draft_completed",
        "post_draft_report",
        ["draft_session_id", "completed_at"],
    )

    op.create_table(
        "post_draft_report_player",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("report_id", sa.String(36), nullable=False),
        sa.Column("player_id", sa.String(36), nullable=False),
        sa.Column("overall_pick", sa.Integer(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("primary_position", sa.String(16), nullable=False),
        sa.Column("fantasy_positions_json", sa.Text(), nullable=False),
        sa.Column("starter_assignment", sa.String(64)),
        sa.Column("saved_personal_rank", sa.Integer()),
        sa.Column("saved_tier_order", sa.Integer()),
        sa.Column("saved_favorite", sa.Boolean(), nullable=False),
        sa.Column("safe_evidence_json", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "overall_pick >= 1 AND round_number >= 1",
            name="ck_post_draft_report_player_pick",
        ),
        sa.CheckConstraint(
            "saved_personal_rank IS NULL OR saved_personal_rank >= 1",
            name="ck_post_draft_report_player_personal_rank",
        ),
        sa.CheckConstraint(
            "saved_tier_order IS NULL OR saved_tier_order >= 1",
            name="ck_post_draft_report_player_tier_order",
        ),
        sa.CheckConstraint(
            "json_valid(fantasy_positions_json) = 1 "
            "AND json_valid(safe_evidence_json) = 1",
            name="ck_post_draft_report_player_json",
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["post_draft_report.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["player_id"], ["player.id"]),
        sa.UniqueConstraint(
            "report_id",
            "player_id",
            name="uq_post_draft_report_player_report_player",
        ),
        sa.UniqueConstraint(
            "report_id",
            "overall_pick",
            name="uq_post_draft_report_player_report_pick",
        ),
    )
    op.create_index(
        "ix_post_draft_report_player_report_position",
        "post_draft_report_player",
        ["report_id", "primary_position"],
    )

    op.create_table(
        "post_draft_report_section",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("report_id", sa.String(36), nullable=False),
        sa.Column("section_key", sa.String(80), nullable=False),
        sa.Column("availability", sa.String(16), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("metrics_json", sa.Text(), nullable=False),
        sa.Column("reason_codes_json", sa.Text(), nullable=False),
        sa.Column("limitation_codes_json", sa.Text(), nullable=False),
        sa.Column("explanation_template_key", sa.String(100), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("safe_provenance_json", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(section_key) BETWEEN 1 AND 80",
            name="ck_post_draft_report_section_key",
        ),
        sa.CheckConstraint(
            "availability IN ('supported', 'limited', 'unavailable', "
            "'not_applicable')",
            name="ck_post_draft_report_section_availability",
        ),
        sa.CheckConstraint(
            "confidence IN ('high', 'medium', 'low', 'unavailable')",
            name="ck_post_draft_report_section_confidence",
        ),
        sa.CheckConstraint(
            "length(explanation_template_key) BETWEEN 1 AND 100 "
            "AND length(explanation) >= 1",
            name="ck_post_draft_report_section_explanation",
        ),
        sa.CheckConstraint(
            "json_valid(metrics_json) = 1 "
            "AND json_valid(reason_codes_json) = 1 "
            "AND json_valid(limitation_codes_json) = 1 "
            "AND json_valid(safe_provenance_json) = 1",
            name="ck_post_draft_report_section_json",
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["post_draft_report.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "report_id",
            "section_key",
            name="uq_post_draft_report_section_report_key",
        ),
    )
    op.create_index(
        "ix_post_draft_report_section_report_availability",
        "post_draft_report_section",
        ["report_id", "availability"],
    )

    op.create_table(
        "post_draft_report_moment",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("report_id", sa.String(36), nullable=False),
        sa.Column("moment_key", sa.String(128), nullable=False),
        sa.Column("moment_kind", sa.String(32), nullable=False),
        sa.Column("overall_pick", sa.Integer()),
        sa.Column("primary_player_id", sa.String(36)),
        sa.Column("secondary_player_id", sa.String(36)),
        sa.Column("safe_summary_json", sa.Text(), nullable=False),
        sa.Column("reason_codes_json", sa.Text(), nullable=False),
        sa.Column("limitation_codes_json", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(moment_key) BETWEEN 1 AND 128",
            name="ck_post_draft_report_moment_key",
        ),
        sa.CheckConstraint(
            "moment_kind IN ('personal_board_choice', 'strategy_pivot', "
            "'strategy_guidance', 'alert_event')",
            name="ck_post_draft_report_moment_kind",
        ),
        sa.CheckConstraint(
            "overall_pick IS NULL OR overall_pick >= 1",
            name="ck_post_draft_report_moment_pick",
        ),
        sa.CheckConstraint(
            "primary_player_id IS NULL OR secondary_player_id IS NULL "
            "OR primary_player_id != secondary_player_id",
            name="ck_post_draft_report_moment_distinct_players",
        ),
        sa.CheckConstraint(
            "json_valid(safe_summary_json) = 1 "
            "AND json_valid(reason_codes_json) = 1 "
            "AND json_valid(limitation_codes_json) = 1",
            name="ck_post_draft_report_moment_json",
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["post_draft_report.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["primary_player_id"], ["player.id"]),
        sa.ForeignKeyConstraint(["secondary_player_id"], ["player.id"]),
        sa.UniqueConstraint(
            "report_id",
            "moment_key",
            name="uq_post_draft_report_moment_report_key",
        ),
    )
    op.create_index(
        "ix_post_draft_report_moment_report_kind_pick",
        "post_draft_report_moment",
        ["report_id", "moment_kind", "overall_pick"],
    )

    for table_name in (
        "post_draft_report",
        "post_draft_report_player",
        "post_draft_report_section",
        "post_draft_report_moment",
    ):
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_{table_name}_immutable_update
                BEFORE UPDATE ON {table_name}
                BEGIN
                    SELECT RAISE(ABORT, 'saved post-draft reports are immutable');
                END
                """
            )
        )

    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_post_draft_report_immutable_delete
            BEFORE DELETE ON post_draft_report
            WHEN EXISTS (
                SELECT 1 FROM draft_session
                WHERE id = OLD.draft_session_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'saved post-draft reports are draft-owned');
            END
            """
        )
    )
    for table_name in (
        "post_draft_report_player",
        "post_draft_report_section",
        "post_draft_report_moment",
    ):
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_{table_name}_immutable_delete
                BEFORE DELETE ON {table_name}
                WHEN EXISTS (
                    SELECT 1 FROM post_draft_report
                    WHERE id = OLD.report_id
                )
                BEGIN
                    SELECT RAISE(ABORT, 'saved post-draft report rows are immutable');
                END
                """
            )
        )


def downgrade() -> None:
    for table_name in (
        "post_draft_report_moment",
        "post_draft_report_section",
        "post_draft_report_player",
        "post_draft_report",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_immutable_delete")
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_immutable_update")

    op.drop_index(
        "ix_post_draft_report_moment_report_kind_pick",
        table_name="post_draft_report_moment",
    )
    op.drop_table("post_draft_report_moment")
    op.drop_index(
        "ix_post_draft_report_section_report_availability",
        table_name="post_draft_report_section",
    )
    op.drop_table("post_draft_report_section")
    op.drop_index(
        "ix_post_draft_report_player_report_position",
        table_name="post_draft_report_player",
    )
    op.drop_table("post_draft_report_player")
    op.drop_index(
        "ix_post_draft_report_draft_completed",
        table_name="post_draft_report",
    )
    op.drop_table("post_draft_report")
