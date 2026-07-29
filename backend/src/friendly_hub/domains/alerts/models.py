from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from friendly_hub.db.base import Base


class AlertEvidenceSnapshotRow(Base):
    __tablename__ = "alert_evidence_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "content_hash",
            name="uq_alert_evidence_snapshot_content_hash",
        ),
        CheckConstraint(
            "schema_version = 1",
            name="ck_alert_evidence_snapshot_schema_version",
        ),
        CheckConstraint(
            "source_kind IN ('synthetic', 'user_entered', 'public', 'licensed')",
            name="ck_alert_evidence_snapshot_source_kind",
        ),
        CheckConstraint(
            "permitted_use_confirmed = 1",
            name="ck_alert_evidence_snapshot_permitted_use",
        ),
        CheckConstraint(
            "supported_draft_depth >= 1 AND supported_draft_depth <= 10000",
            name="ck_alert_evidence_snapshot_draft_depth",
        ),
        CheckConstraint(
            "length(content_hash) = 64",
            name="ck_alert_evidence_snapshot_content_hash",
        ),
        CheckConstraint(
            "status IN ('committed', 'superseded', 'invalidated')",
            name="ck_alert_evidence_snapshot_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_label: Mapped[str] = mapped_column(String(120), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    source_namespace: Mapped[str] = mapped_column(String(64), nullable=False)
    permitted_use_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    private_source_reference: Mapped[str | None] = mapped_column(String(256))
    format_json: Mapped[str] = mapped_column(Text, nullable=False)
    supported_draft_depth: Mapped[int] = mapped_column(Integer, nullable=False)
    source_as_of: Mapped[str] = mapped_column(String(32), nullable=False)
    imported_at: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class AlertPlayerSignalRow(Base):
    __tablename__ = "alert_player_signal"
    __table_args__ = (
        UniqueConstraint(
            "evidence_snapshot_id",
            "player_id",
            name="uq_alert_player_signal_snapshot_player",
        ),
        CheckConstraint(
            "(expected_pick_low IS NULL AND expected_pick_high IS NULL) OR "
            "(expected_pick_low >= 1 AND expected_pick_high >= expected_pick_low "
            "AND expected_pick_high <= 10000)",
            name="ck_alert_player_signal_expected_pick",
        ),
        CheckConstraint(
            "market_band IS NULL OR market_band IN "
            "('premium', 'strong', 'standard', 'depth', 'fringe')",
            name="ck_alert_player_signal_market_band",
        ),
        CheckConstraint(
            "win_now_production_band IS NULL OR "
            "win_now_production_band IN ('high', 'medium', 'low')",
            name="ck_alert_player_signal_production_band",
        ),
        CheckConstraint(
            "age_risk_band IS NULL OR age_risk_band IN ('lower', 'middle', 'higher')",
            name="ck_alert_player_signal_age_risk_band",
        ),
        Index(
            "ix_alert_player_signal_snapshot_player",
            "evidence_snapshot_id",
            "player_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evidence_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alert_evidence_snapshot.id"),
        nullable=False,
    )
    player_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("player.id"),
        nullable=False,
    )
    expected_pick_low: Mapped[int | None] = mapped_column(Integer)
    expected_pick_high: Mapped[int | None] = mapped_column(Integer)
    market_band: Mapped[str | None] = mapped_column(String(16))
    win_now_production_band: Mapped[str | None] = mapped_column(String(16))
    age_risk_band: Mapped[str | None] = mapped_column(String(16))
    field_timestamps_json: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_as_of: Mapped[str] = mapped_column(String(32), nullable=False)
    limitation_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    private_source_record_reference: Mapped[str | None] = mapped_column(String(256))


class AlertPickValueSignalRow(Base):
    __tablename__ = "alert_pick_value_signal"
    __table_args__ = (
        UniqueConstraint(
            "evidence_snapshot_id",
            "asset_key",
            name="uq_alert_pick_value_signal_snapshot_asset",
        ),
        CheckConstraint(
            "asset_type IN ('current_draft_pick', 'future_round')",
            name="ck_alert_pick_value_signal_asset_type",
        ),
        CheckConstraint(
            "(asset_type = 'current_draft_pick' "
            "AND overall_pick >= 1 AND overall_pick <= 10000 "
            "AND season_offset IS NULL AND round_number IS NULL) OR "
            "(asset_type = 'future_round' AND overall_pick IS NULL "
            "AND season_offset >= 1 AND season_offset <= 5 "
            "AND round_number >= 1 AND round_number <= 10)",
            name="ck_alert_pick_value_signal_coordinates",
        ),
        CheckConstraint(
            "value_low >= 0 AND value_high >= value_low AND value_high <= 1000000",
            name="ck_alert_pick_value_signal_value_range",
        ),
        Index(
            "ix_alert_pick_value_signal_snapshot_current_pick",
            "evidence_snapshot_id",
            "overall_pick",
            unique=True,
            sqlite_where=text("asset_type = 'current_draft_pick'"),
        ),
        Index(
            "ix_alert_pick_value_signal_snapshot_future_round",
            "evidence_snapshot_id",
            "season_offset",
            "round_number",
            unique=True,
            sqlite_where=text("asset_type = 'future_round'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evidence_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alert_evidence_snapshot.id"),
        nullable=False,
    )
    asset_key: Mapped[str] = mapped_column(String(128), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(24), nullable=False)
    season_offset: Mapped[int | None] = mapped_column(Integer)
    round_number: Mapped[int | None] = mapped_column(Integer)
    overall_pick: Mapped[int | None] = mapped_column(Integer)
    value_low: Mapped[int] = mapped_column(Integer, nullable=False)
    value_high: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_as_of: Mapped[str] = mapped_column(String(32), nullable=False)
    limitation_codes_json: Mapped[str] = mapped_column(Text, nullable=False)


class DraftAlertConfigurationRow(Base):
    __tablename__ = "draft_alert_configuration"
    __table_args__ = (
        UniqueConstraint(
            "draft_session_id",
            name="uq_draft_alert_configuration_draft_session",
        ),
        CheckConstraint(
            "personal_qualifier_mode IN "
            "('tier_or_favorite', 'tier_only', 'favorite_only')",
            name="ck_draft_alert_configuration_qualifier_mode",
        ),
        CheckConstraint(
            "eligible_tier_count >= 0 AND eligible_tier_count <= 100",
            name="ck_draft_alert_configuration_tier_count",
        ),
        CheckConstraint(
            "minimum_conservative_gap >= 0 "
            "AND minimum_conservative_gap <= 10000",
            name="ck_draft_alert_configuration_gap",
        ),
        CheckConstraint(
            "snooze_pick_count >= 1 AND snooze_pick_count <= 100",
            name="ck_draft_alert_configuration_snooze_count",
        ),
        CheckConstraint(
            "revision >= 0",
            name="ck_draft_alert_configuration_revision",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    draft_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("draft_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alert_evidence_snapshot.id"),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    personal_qualifier_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    eligible_tier_count: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_conservative_gap: Mapped[int] = mapped_column(Integer, nullable=False)
    snooze_pick_count: Mapped[int] = mapped_column(Integer, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    freshness_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class DraftAlertConfigurationRevisionRow(Base):
    __tablename__ = "draft_alert_configuration_revision"
    __table_args__ = (
        UniqueConstraint(
            "configuration_id",
            "sequence_number",
            name="uq_draft_alert_configuration_revision_sequence",
        ),
        CheckConstraint(
            "sequence_number >= 1",
            name="ck_draft_alert_configuration_revision_sequence",
        ),
        CheckConstraint(
            "reason IN ('initial', 'settings_changed', 'snapshot_replaced', 'reset_copy')",
            name="ck_draft_alert_configuration_revision_reason",
        ),
        Index(
            "ix_draft_alert_configuration_revision_configuration",
            "configuration_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    configuration_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("draft_alert_configuration.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_evidence_snapshot_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("alert_evidence_snapshot.id"),
    )
    next_evidence_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alert_evidence_snapshot.id"),
        nullable=False,
    )
    previous_settings_json: Mapped[str | None] = mapped_column(Text)
    next_settings_json: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class DraftAlertEvaluationRow(Base):
    __tablename__ = "draft_alert_evaluation"
    __table_args__ = (
        UniqueConstraint(
            "configuration_id",
            "input_fingerprint",
            name="uq_draft_alert_evaluation_fingerprint",
        ),
        CheckConstraint(
            "draft_revision >= 0",
            name="ck_draft_alert_evaluation_draft_revision",
        ),
        CheckConstraint(
            "length(input_fingerprint) = 64",
            name="ck_draft_alert_evaluation_fingerprint",
        ),
        CheckConstraint(
            "current_overall_pick IS NULL OR current_overall_pick >= 1",
            name="ck_draft_alert_evaluation_current_pick",
        ),
        CheckConstraint(
            "next_user_pick IS NULL OR next_user_pick >= 1",
            name="ck_draft_alert_evaluation_next_user_pick",
        ),
        CheckConstraint(
            "candidate_count >= 0 AND opened_count >= 0 AND updated_count >= 0 "
            "AND superseded_count >= 0",
            name="ck_draft_alert_evaluation_counts",
        ),
        Index(
            "ix_draft_alert_evaluation_configuration_revision",
            "configuration_id",
            "draft_revision",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    configuration_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("draft_alert_configuration.id", ondelete="CASCADE"),
        nullable=False,
    )
    draft_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    current_overall_pick: Mapped[int | None] = mapped_column(Integer)
    next_user_pick: Mapped[int | None] = mapped_column(Integer)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    opened_count: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False)
    superseded_count: Mapped[int] = mapped_column(Integer, nullable=False)
    limitation_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    evaluated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class DraftAlertEventRow(Base):
    __tablename__ = "draft_alert_event"
    __table_args__ = (
        UniqueConstraint(
            "configuration_id",
            "deterministic_event_key",
            name="uq_draft_alert_event_key",
        ),
        CheckConstraint(
            "alert_kind IN "
            "('value_watch', 'return_risk', 'trade_up_window', 'evidence_warning')",
            name="ck_draft_alert_event_kind",
        ),
        CheckConstraint(
            "status IN ('open', 'snoozed', 'dismissed', 'superseded')",
            name="ck_draft_alert_event_status",
        ),
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low', 'unavailable')",
            name="ck_draft_alert_event_confidence",
        ),
        CheckConstraint(
            "freshness IN ('fresh', 'aging', 'stale', 'expired', 'invalid')",
            name="ck_draft_alert_event_freshness",
        ),
        CheckConstraint(
            "first_confirmed_draft_revision >= 0 "
            "AND last_confirmed_draft_revision >= first_confirmed_draft_revision",
            name="ck_draft_alert_event_revisions",
        ),
        CheckConstraint(
            "snooze_boundary IS NULL OR snooze_boundary >= 1",
            name="ck_draft_alert_event_snooze_boundary",
        ),
        CheckConstraint(
            "status != 'snoozed' OR snooze_boundary IS NOT NULL",
            name="ck_draft_alert_event_snoozed_state",
        ),
        CheckConstraint(
            "status != 'dismissed' OR dismissed_at IS NOT NULL",
            name="ck_draft_alert_event_dismissed_state",
        ),
        CheckConstraint(
            "status != 'superseded' OR superseded_at IS NOT NULL",
            name="ck_draft_alert_event_superseded_state",
        ),
        Index(
            "ix_draft_alert_event_configuration_status",
            "configuration_id",
            "status",
        ),
        Index(
            "ix_draft_alert_event_configuration_player",
            "configuration_id",
            "player_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    configuration_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("draft_alert_configuration.id", ondelete="CASCADE"),
        nullable=False,
    )
    player_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("player.id"),
        nullable=False,
    )
    deterministic_event_key: Mapped[str] = mapped_column(String(128), nullable=False)
    alert_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    freshness: Mapped[str] = mapped_column(String(16), nullable=False)
    first_confirmed_draft_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    last_confirmed_draft_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    original_evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    current_evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    explanation_template_keys_json: Mapped[str] = mapped_column(Text, nullable=False)
    limitation_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    snooze_boundary: Mapped[int | None] = mapped_column(Integer)
    dismissed_at: Mapped[str | None] = mapped_column(String(32))
    superseded_at: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class DraftAlertTradeReferenceRow(Base):
    __tablename__ = "draft_alert_trade_reference"
    __table_args__ = (
        CheckConstraint(
            "target_overall_pick_low >= 1 "
            "AND target_overall_pick_high >= target_overall_pick_low",
            name="ck_draft_alert_trade_reference_target_range",
        ),
        Index(
            "ix_draft_alert_trade_reference_event",
            "event_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("draft_alert_event.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_overall_pick_low: Mapped[int] = mapped_column(Integer, nullable=False)
    target_overall_pick_high: Mapped[int] = mapped_column(Integer, nullable=False)
    target_round_pick_labels_json: Mapped[str] = mapped_column(Text, nullable=False)
    cost_range_json: Mapped[str] = mapped_column(Text, nullable=False)
    pick_curve_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("alert_evidence_snapshot.id"),
        nullable=False,
    )
    explanation_template_key: Mapped[str] = mapped_column(String(64), nullable=False)
    limitation_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
