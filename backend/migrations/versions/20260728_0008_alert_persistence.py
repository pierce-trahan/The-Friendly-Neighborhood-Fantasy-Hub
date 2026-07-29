"""Create the Phase 5 alert persistence tables.

Revision ID: 20260728_0008
Revises: 20260728_0007
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0008"
down_revision: str | None = "20260728_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_evidence_snapshot",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("source_label", sa.String(120), nullable=False),
        sa.Column("source_kind", sa.String(24), nullable=False),
        sa.Column("source_namespace", sa.String(64), nullable=False),
        sa.Column("permitted_use_confirmed", sa.Boolean(), nullable=False),
        sa.Column("private_source_reference", sa.String(256)),
        sa.Column("format_json", sa.Text(), nullable=False),
        sa.Column("supported_draft_depth", sa.Integer(), nullable=False),
        sa.Column("source_as_of", sa.String(32), nullable=False),
        sa.Column("imported_at", sa.String(32), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "schema_version = 1",
            name="ck_alert_evidence_snapshot_schema_version",
        ),
        sa.CheckConstraint(
            "source_kind IN ('synthetic', 'user_entered', 'public', 'licensed')",
            name="ck_alert_evidence_snapshot_source_kind",
        ),
        sa.CheckConstraint(
            "permitted_use_confirmed = 1",
            name="ck_alert_evidence_snapshot_permitted_use",
        ),
        sa.CheckConstraint(
            "supported_draft_depth >= 1 AND supported_draft_depth <= 10000",
            name="ck_alert_evidence_snapshot_draft_depth",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_alert_evidence_snapshot_content_hash",
        ),
        sa.CheckConstraint(
            "status IN ('committed', 'superseded', 'invalidated')",
            name="ck_alert_evidence_snapshot_status",
        ),
        sa.UniqueConstraint(
            "content_hash",
            name="uq_alert_evidence_snapshot_content_hash",
        ),
    )

    op.create_table(
        "alert_player_signal",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("evidence_snapshot_id", sa.String(36), nullable=False),
        sa.Column("player_id", sa.String(36), nullable=False),
        sa.Column("expected_pick_low", sa.Integer()),
        sa.Column("expected_pick_high", sa.Integer()),
        sa.Column("market_band", sa.String(16)),
        sa.Column("win_now_production_band", sa.String(16)),
        sa.Column("age_risk_band", sa.String(16)),
        sa.Column("field_timestamps_json", sa.Text(), nullable=False),
        sa.Column("evidence_as_of", sa.String(32), nullable=False),
        sa.Column("limitation_codes_json", sa.Text(), nullable=False),
        sa.Column("private_source_record_reference", sa.String(256)),
        sa.CheckConstraint(
            "(expected_pick_low IS NULL AND expected_pick_high IS NULL) OR "
            "(expected_pick_low >= 1 AND expected_pick_high >= expected_pick_low "
            "AND expected_pick_high <= 10000)",
            name="ck_alert_player_signal_expected_pick",
        ),
        sa.CheckConstraint(
            "market_band IS NULL OR market_band IN "
            "('premium', 'strong', 'standard', 'depth', 'fringe')",
            name="ck_alert_player_signal_market_band",
        ),
        sa.CheckConstraint(
            "win_now_production_band IS NULL OR "
            "win_now_production_band IN ('high', 'medium', 'low')",
            name="ck_alert_player_signal_production_band",
        ),
        sa.CheckConstraint(
            "age_risk_band IS NULL OR age_risk_band IN ('lower', 'middle', 'higher')",
            name="ck_alert_player_signal_age_risk_band",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["alert_evidence_snapshot.id"],
        ),
        sa.ForeignKeyConstraint(["player_id"], ["player.id"]),
        sa.UniqueConstraint(
            "evidence_snapshot_id",
            "player_id",
            name="uq_alert_player_signal_snapshot_player",
        ),
    )
    op.create_index(
        "ix_alert_player_signal_snapshot_player",
        "alert_player_signal",
        ["evidence_snapshot_id", "player_id"],
    )

    op.create_table(
        "alert_pick_value_signal",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("evidence_snapshot_id", sa.String(36), nullable=False),
        sa.Column("asset_key", sa.String(128), nullable=False),
        sa.Column("asset_type", sa.String(24), nullable=False),
        sa.Column("season_offset", sa.Integer()),
        sa.Column("round_number", sa.Integer()),
        sa.Column("overall_pick", sa.Integer()),
        sa.Column("value_low", sa.Integer(), nullable=False),
        sa.Column("value_high", sa.Integer(), nullable=False),
        sa.Column("evidence_as_of", sa.String(32), nullable=False),
        sa.Column("limitation_codes_json", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "asset_type IN ('current_draft_pick', 'future_round')",
            name="ck_alert_pick_value_signal_asset_type",
        ),
        sa.CheckConstraint(
            "(asset_type = 'current_draft_pick' "
            "AND overall_pick >= 1 AND overall_pick <= 10000 "
            "AND season_offset IS NULL AND round_number IS NULL) OR "
            "(asset_type = 'future_round' AND overall_pick IS NULL "
            "AND season_offset >= 1 AND season_offset <= 5 "
            "AND round_number >= 1 AND round_number <= 10)",
            name="ck_alert_pick_value_signal_coordinates",
        ),
        sa.CheckConstraint(
            "value_low >= 0 AND value_high >= value_low AND value_high <= 1000000",
            name="ck_alert_pick_value_signal_value_range",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["alert_evidence_snapshot.id"],
        ),
        sa.UniqueConstraint(
            "evidence_snapshot_id",
            "asset_key",
            name="uq_alert_pick_value_signal_snapshot_asset",
        ),
    )
    op.create_index(
        "ix_alert_pick_value_signal_snapshot_current_pick",
        "alert_pick_value_signal",
        ["evidence_snapshot_id", "overall_pick"],
        unique=True,
        sqlite_where=sa.text("asset_type = 'current_draft_pick'"),
    )
    op.create_index(
        "ix_alert_pick_value_signal_snapshot_future_round",
        "alert_pick_value_signal",
        ["evidence_snapshot_id", "season_offset", "round_number"],
        unique=True,
        sqlite_where=sa.text("asset_type = 'future_round'"),
    )

    op.create_table(
        "draft_alert_configuration",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("draft_session_id", sa.String(36), nullable=False),
        sa.Column("evidence_snapshot_id", sa.String(36), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("personal_qualifier_mode", sa.String(24), nullable=False),
        sa.Column("eligible_tier_count", sa.Integer(), nullable=False),
        sa.Column("minimum_conservative_gap", sa.Integer(), nullable=False),
        sa.Column("snooze_pick_count", sa.Integer(), nullable=False),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("freshness_policy_version", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "personal_qualifier_mode IN "
            "('tier_or_favorite', 'tier_only', 'favorite_only')",
            name="ck_draft_alert_configuration_qualifier_mode",
        ),
        sa.CheckConstraint(
            "eligible_tier_count >= 0 AND eligible_tier_count <= 100",
            name="ck_draft_alert_configuration_tier_count",
        ),
        sa.CheckConstraint(
            "minimum_conservative_gap >= 0 "
            "AND minimum_conservative_gap <= 10000",
            name="ck_draft_alert_configuration_gap",
        ),
        sa.CheckConstraint(
            "snooze_pick_count >= 1 AND snooze_pick_count <= 100",
            name="ck_draft_alert_configuration_snooze_count",
        ),
        sa.CheckConstraint(
            "revision >= 0",
            name="ck_draft_alert_configuration_revision",
        ),
        sa.ForeignKeyConstraint(
            ["draft_session_id"],
            ["draft_session.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_snapshot_id"],
            ["alert_evidence_snapshot.id"],
        ),
        sa.UniqueConstraint(
            "draft_session_id",
            name="uq_draft_alert_configuration_draft_session",
        ),
    )

    op.create_table(
        "draft_alert_configuration_revision",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("configuration_id", sa.String(36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("previous_evidence_snapshot_id", sa.String(36)),
        sa.Column("next_evidence_snapshot_id", sa.String(36), nullable=False),
        sa.Column("previous_settings_json", sa.Text()),
        sa.Column("next_settings_json", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(24), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "sequence_number >= 1",
            name="ck_draft_alert_configuration_revision_sequence",
        ),
        sa.CheckConstraint(
            "reason IN ('initial', 'settings_changed', 'snapshot_replaced', 'reset_copy')",
            name="ck_draft_alert_configuration_revision_reason",
        ),
        sa.ForeignKeyConstraint(
            ["configuration_id"],
            ["draft_alert_configuration.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["previous_evidence_snapshot_id"],
            ["alert_evidence_snapshot.id"],
        ),
        sa.ForeignKeyConstraint(
            ["next_evidence_snapshot_id"],
            ["alert_evidence_snapshot.id"],
        ),
        sa.UniqueConstraint(
            "configuration_id",
            "sequence_number",
            name="uq_draft_alert_configuration_revision_sequence",
        ),
    )
    op.create_index(
        "ix_draft_alert_configuration_revision_configuration",
        "draft_alert_configuration_revision",
        ["configuration_id"],
    )

    op.create_table(
        "draft_alert_evaluation",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("configuration_id", sa.String(36), nullable=False),
        sa.Column("draft_revision", sa.Integer(), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("current_overall_pick", sa.Integer()),
        sa.Column("next_user_pick", sa.Integer()),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("opened_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("superseded_count", sa.Integer(), nullable=False),
        sa.Column("limitation_codes_json", sa.Text(), nullable=False),
        sa.Column("evaluated_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "draft_revision >= 0",
            name="ck_draft_alert_evaluation_draft_revision",
        ),
        sa.CheckConstraint(
            "length(input_fingerprint) = 64",
            name="ck_draft_alert_evaluation_fingerprint",
        ),
        sa.CheckConstraint(
            "current_overall_pick IS NULL OR current_overall_pick >= 1",
            name="ck_draft_alert_evaluation_current_pick",
        ),
        sa.CheckConstraint(
            "next_user_pick IS NULL OR next_user_pick >= 1",
            name="ck_draft_alert_evaluation_next_user_pick",
        ),
        sa.CheckConstraint(
            "candidate_count >= 0 AND opened_count >= 0 AND updated_count >= 0 "
            "AND superseded_count >= 0",
            name="ck_draft_alert_evaluation_counts",
        ),
        sa.ForeignKeyConstraint(
            ["configuration_id"],
            ["draft_alert_configuration.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "configuration_id",
            "input_fingerprint",
            name="uq_draft_alert_evaluation_fingerprint",
        ),
    )
    op.create_index(
        "ix_draft_alert_evaluation_configuration_revision",
        "draft_alert_evaluation",
        ["configuration_id", "draft_revision"],
    )

    op.create_table(
        "draft_alert_event",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("configuration_id", sa.String(36), nullable=False),
        sa.Column("player_id", sa.String(36), nullable=False),
        sa.Column("deterministic_event_key", sa.String(128), nullable=False),
        sa.Column("alert_kind", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("freshness", sa.String(16), nullable=False),
        sa.Column("first_confirmed_draft_revision", sa.Integer(), nullable=False),
        sa.Column("last_confirmed_draft_revision", sa.Integer(), nullable=False),
        sa.Column("original_evidence_json", sa.Text(), nullable=False),
        sa.Column("current_evidence_json", sa.Text(), nullable=False),
        sa.Column("explanation_template_keys_json", sa.Text(), nullable=False),
        sa.Column("limitation_codes_json", sa.Text(), nullable=False),
        sa.Column("snooze_boundary", sa.Integer()),
        sa.Column("dismissed_at", sa.String(32)),
        sa.Column("superseded_at", sa.String(32)),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "alert_kind IN "
            "('value_watch', 'return_risk', 'trade_up_window', 'evidence_warning')",
            name="ck_draft_alert_event_kind",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'snoozed', 'dismissed', 'superseded')",
            name="ck_draft_alert_event_status",
        ),
        sa.CheckConstraint(
            "confidence IN ('high', 'medium', 'low', 'unavailable')",
            name="ck_draft_alert_event_confidence",
        ),
        sa.CheckConstraint(
            "freshness IN ('fresh', 'aging', 'stale', 'expired', 'invalid')",
            name="ck_draft_alert_event_freshness",
        ),
        sa.CheckConstraint(
            "first_confirmed_draft_revision >= 0 "
            "AND last_confirmed_draft_revision >= first_confirmed_draft_revision",
            name="ck_draft_alert_event_revisions",
        ),
        sa.CheckConstraint(
            "snooze_boundary IS NULL OR snooze_boundary >= 1",
            name="ck_draft_alert_event_snooze_boundary",
        ),
        sa.CheckConstraint(
            "status != 'snoozed' OR snooze_boundary IS NOT NULL",
            name="ck_draft_alert_event_snoozed_state",
        ),
        sa.CheckConstraint(
            "status != 'dismissed' OR dismissed_at IS NOT NULL",
            name="ck_draft_alert_event_dismissed_state",
        ),
        sa.CheckConstraint(
            "status != 'superseded' OR superseded_at IS NOT NULL",
            name="ck_draft_alert_event_superseded_state",
        ),
        sa.ForeignKeyConstraint(
            ["configuration_id"],
            ["draft_alert_configuration.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["player_id"], ["player.id"]),
        sa.UniqueConstraint(
            "configuration_id",
            "deterministic_event_key",
            name="uq_draft_alert_event_key",
        ),
    )
    op.create_index(
        "ix_draft_alert_event_configuration_status",
        "draft_alert_event",
        ["configuration_id", "status"],
    )
    op.create_index(
        "ix_draft_alert_event_configuration_player",
        "draft_alert_event",
        ["configuration_id", "player_id"],
    )

    op.create_table(
        "draft_alert_trade_reference",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("target_overall_pick_low", sa.Integer(), nullable=False),
        sa.Column("target_overall_pick_high", sa.Integer(), nullable=False),
        sa.Column("target_round_pick_labels_json", sa.Text(), nullable=False),
        sa.Column("cost_range_json", sa.Text(), nullable=False),
        sa.Column("pick_curve_snapshot_id", sa.String(36), nullable=False),
        sa.Column("explanation_template_key", sa.String(64), nullable=False),
        sa.Column("limitation_codes_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "target_overall_pick_low >= 1 "
            "AND target_overall_pick_high >= target_overall_pick_low",
            name="ck_draft_alert_trade_reference_target_range",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["draft_alert_event.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pick_curve_snapshot_id"],
            ["alert_evidence_snapshot.id"],
        ),
    )
    op.create_index(
        "ix_draft_alert_trade_reference_event",
        "draft_alert_trade_reference",
        ["event_id"],
    )

    for table_name in (
        "alert_evidence_snapshot",
        "alert_player_signal",
        "alert_pick_value_signal",
    ):
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_{table_name}_immutable_update
                BEFORE UPDATE ON {table_name}
                BEGIN
                    SELECT RAISE(ABORT, 'committed alert evidence is immutable');
                END
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_{table_name}_immutable_delete
                BEFORE DELETE ON {table_name}
                BEGIN
                    SELECT RAISE(ABORT, 'committed alert evidence is retained');
                END
                """
            )
        )


def downgrade() -> None:
    for table_name in (
        "alert_pick_value_signal",
        "alert_player_signal",
        "alert_evidence_snapshot",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_immutable_delete")
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_immutable_update")

    op.drop_index(
        "ix_draft_alert_trade_reference_event",
        table_name="draft_alert_trade_reference",
    )
    op.drop_table("draft_alert_trade_reference")
    op.drop_index(
        "ix_draft_alert_event_configuration_player",
        table_name="draft_alert_event",
    )
    op.drop_index(
        "ix_draft_alert_event_configuration_status",
        table_name="draft_alert_event",
    )
    op.drop_table("draft_alert_event")
    op.drop_index(
        "ix_draft_alert_evaluation_configuration_revision",
        table_name="draft_alert_evaluation",
    )
    op.drop_table("draft_alert_evaluation")
    op.drop_index(
        "ix_draft_alert_configuration_revision_configuration",
        table_name="draft_alert_configuration_revision",
    )
    op.drop_table("draft_alert_configuration_revision")
    op.drop_table("draft_alert_configuration")
    op.drop_index(
        "ix_alert_pick_value_signal_snapshot_future_round",
        table_name="alert_pick_value_signal",
    )
    op.drop_index(
        "ix_alert_pick_value_signal_snapshot_current_pick",
        table_name="alert_pick_value_signal",
    )
    op.drop_table("alert_pick_value_signal")
    op.drop_index(
        "ix_alert_player_signal_snapshot_player",
        table_name="alert_player_signal",
    )
    op.drop_table("alert_player_signal")
    op.drop_table("alert_evidence_snapshot")
