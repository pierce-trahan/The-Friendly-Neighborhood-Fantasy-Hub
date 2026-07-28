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
)
from sqlalchemy.orm import Mapped, mapped_column

from friendly_hub.db.base import Base


class MockConfigurationRow(Base):
    __tablename__ = "mock_configuration"
    __table_args__ = (
        UniqueConstraint(
            "draft_session_id",
            name="uq_mock_configuration_draft_session",
        ),
        CheckConstraint(
            "randomness >= 0 AND randomness <= 100",
            name="ck_mock_configuration_randomness",
        ),
        CheckConstraint(
            "revision >= 0",
            name="ck_mock_configuration_revision",
        ),
        CheckConstraint(
            "length(content_fingerprint) = 64",
            name="ck_mock_configuration_fingerprint",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    draft_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("draft_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    seed: Mapped[str] = mapped_column(String(20), nullable=False)
    rng_version: Mapped[str] = mapped_column(String(64), nullable=False)
    cpu_engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_definition_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    league_shape_json: Mapped[str] = mapped_column(Text, nullable=False)
    league_shape_source_timestamp: Mapped[str | None] = mapped_column(String(32))
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    randomness: Mapped[int] = mapped_column(Integer, nullable=False)
    current_strategy_key: Mapped[str] = mapped_column(String(32), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    include_in_learning: Mapped[bool] = mapped_column(Boolean, nullable=False)
    learning_opted_in_at: Mapped[str | None] = mapped_column(String(32))
    learning_withdrawn_at: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class MockStrategyRevisionRow(Base):
    __tablename__ = "mock_strategy_revision"
    __table_args__ = (
        UniqueConstraint(
            "mock_configuration_id",
            "sequence_number",
            name="uq_mock_strategy_revision_sequence",
        ),
        CheckConstraint(
            "sequence_number >= 1",
            name="ck_mock_strategy_revision_sequence",
        ),
        CheckConstraint(
            "effective_overall_pick >= 1",
            name="ck_mock_strategy_revision_effective_pick",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mock_configuration_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mock_configuration.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_strategy_key: Mapped[str | None] = mapped_column(String(32))
    next_strategy_key: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_overall_pick: Mapped[int] = mapped_column(Integer, nullable=False)
    user_roster_counts_json: Mapped[str] = mapped_column(Text, nullable=False)
    private_user_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class MockCpuProfileRow(Base):
    __tablename__ = "mock_cpu_profile"
    __table_args__ = (
        UniqueConstraint(
            "mock_configuration_id",
            "draft_slot",
            name="uq_mock_cpu_profile_slot",
        ),
        CheckConstraint(
            "draft_slot >= 1",
            name="ck_mock_cpu_profile_slot",
        ),
        CheckConstraint(
            "source IN ('fallback', 'history')",
            name="ck_mock_cpu_profile_source",
        ),
        CheckConstraint(
            "draft_sample_count >= 0",
            name="ck_mock_cpu_profile_draft_samples",
        ),
        CheckConstraint(
            "pick_sample_count >= 0",
            name="ck_mock_cpu_profile_pick_samples",
        ),
        CheckConstraint(
            "confidence IN ('not_applicable', 'low', 'medium', 'high')",
            name="ck_mock_cpu_profile_confidence",
        ),
        CheckConstraint(
            "("
            "source = 'fallback' AND confidence = 'not_applicable' "
            "AND draft_sample_count = 0 AND pick_sample_count = 0"
            ") OR ("
            "source = 'history' AND confidence IN ('low', 'medium', 'high') "
            "AND draft_sample_count >= 3 AND pick_sample_count >= 20"
            ")",
            name="ck_mock_cpu_profile_evidence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mock_configuration_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mock_configuration.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    draft_slot: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    archetype_key: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    draft_sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pick_sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    tendency_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    internal_manager_reference: Mapped[str | None] = mapped_column(String(128))
    source_timestamp: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class MockPickDecisionRow(Base):
    __tablename__ = "mock_pick_decision"
    __table_args__ = (
        UniqueConstraint(
            "draft_pick_revision_id",
            name="uq_mock_pick_decision_pick_revision",
        ),
        CheckConstraint(
            "overall_pick >= 1",
            name="ck_mock_pick_decision_overall_pick",
        ),
        CheckConstraint(
            "selecting_slot >= 1",
            name="ck_mock_pick_decision_selecting_slot",
        ),
        CheckConstraint(
            "profile_source IN ('fallback', 'history')",
            name="ck_mock_pick_decision_profile_source",
        ),
        Index(
            "ix_mock_pick_decision_configuration_overall",
            "mock_configuration_id",
            "overall_pick",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mock_configuration_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mock_configuration.id", ondelete="CASCADE"),
        nullable=False,
    )
    draft_pick_revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("draft_pick_revision.id", ondelete="CASCADE"),
        nullable=False,
    )
    overall_pick: Mapped[int] = mapped_column(Integer, nullable=False)
    selecting_slot: Mapped[int] = mapped_column(Integer, nullable=False)
    chosen_player_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("player.id"),
        nullable=False,
    )
    profile_source: Mapped[str] = mapped_column(String(16), nullable=False)
    profile_archetype_key: Mapped[str] = mapped_column(String(32), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rng_version: Mapped[str] = mapped_column(String(64), nullable=False)
    total_score: Mapped[int] = mapped_column(Integer, nullable=False)
    component_scores_json: Mapped[str] = mapped_column(Text, nullable=False)
    random_audit_json: Mapped[str] = mapped_column(Text, nullable=False)
    alternatives_json: Mapped[str] = mapped_column(Text, nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    limitation_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class MockGuidanceEventRow(Base):
    __tablename__ = "mock_guidance_event"
    __table_args__ = (
        UniqueConstraint(
            "mock_configuration_id",
            "deterministic_event_key",
            name="uq_mock_guidance_event_key",
        ),
        CheckConstraint(
            "effective_overall_pick >= 1",
            name="ck_mock_guidance_event_effective_pick",
        ),
        CheckConstraint(
            "status IN ('open', 'acknowledged', 'dismissed')",
            name="ck_mock_guidance_event_status",
        ),
        CheckConstraint(
            "state IN ("
            "'on_plan', 'watch', 'off_plan_viable', "
            "'risk_checkpoint', 'insufficient_evidence'"
            ")",
            name="ck_mock_guidance_event_state",
        ),
        CheckConstraint(
            "confidence IN ('unavailable', 'low', 'medium', 'high')",
            name="ck_mock_guidance_event_confidence",
        ),
        Index(
            "ix_mock_guidance_event_configuration_pick",
            "mock_configuration_id",
            "effective_overall_pick",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mock_configuration_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mock_configuration.id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy_revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mock_strategy_revision.id", ondelete="CASCADE"),
        nullable=False,
    )
    deterministic_event_key: Mapped[str] = mapped_column(String(128), nullable=False)
    effective_overall_pick: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_counts_json: Mapped[str] = mapped_column(Text, nullable=False)
    target_ranges_json: Mapped[str] = mapped_column(Text, nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    limitation_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    explanation_template_key: Mapped[str] = mapped_column(String(64), nullable=False)
    pivot_template_key: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    resolved_at: Mapped[str | None] = mapped_column(String(32))
