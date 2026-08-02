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


class PostDraftReportRow(Base):
    __tablename__ = "post_draft_report"
    __table_args__ = (
        UniqueConstraint(
            "draft_session_id",
            "input_fingerprint",
            name="uq_post_draft_report_draft_fingerprint",
        ),
        CheckConstraint(
            "draft_revision >= 0",
            name="ck_post_draft_report_revision",
        ),
        CheckConstraint(
            "length(input_fingerprint) = 64 "
            "AND input_fingerprint NOT GLOB '*[^0-9a-f]*'",
            name="ck_post_draft_report_input_fingerprint",
        ),
        CheckConstraint(
            "length(league_shape_fingerprint) = 64 "
            "AND league_shape_fingerprint NOT GLOB '*[^0-9a-f]*'",
            name="ck_post_draft_report_league_fingerprint",
        ),
        CheckConstraint(
            "length(report_engine_version) BETWEEN 1 AND 64 "
            "AND length(report_rules_version) BETWEEN 1 AND 64 "
            "AND length(explanation_template_version) BETWEEN 1 AND 64",
            name="ck_post_draft_report_versions",
        ),
        CheckConstraint(
            "draft_mode IN ('live', 'mock')",
            name="ck_post_draft_report_mode",
        ),
        CheckConstraint(
            "json_valid(section_summary_json) = 1 "
            "AND json_valid(limitation_codes_json) = 1",
            name="ck_post_draft_report_json",
        ),
        Index(
            "ix_post_draft_report_draft_completed",
            "draft_session_id",
            "completed_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    draft_session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("draft_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    draft_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    league_shape_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    report_engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    report_rules_version: Mapped[str] = mapped_column(String(64), nullable=False)
    explanation_template_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    draft_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    generated_at: Mapped[str] = mapped_column(String(32), nullable=False)
    completed_at: Mapped[str] = mapped_column(String(32), nullable=False)
    section_summary_json: Mapped[str] = mapped_column(Text, nullable=False)
    limitation_codes_json: Mapped[str] = mapped_column(Text, nullable=False)


class PostDraftReportPlayerRow(Base):
    __tablename__ = "post_draft_report_player"
    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "player_id",
            name="uq_post_draft_report_player_report_player",
        ),
        UniqueConstraint(
            "report_id",
            "overall_pick",
            name="uq_post_draft_report_player_report_pick",
        ),
        CheckConstraint(
            "overall_pick >= 1 AND round_number >= 1",
            name="ck_post_draft_report_player_pick",
        ),
        CheckConstraint(
            "saved_personal_rank IS NULL OR saved_personal_rank >= 1",
            name="ck_post_draft_report_player_personal_rank",
        ),
        CheckConstraint(
            "saved_tier_order IS NULL OR saved_tier_order >= 1",
            name="ck_post_draft_report_player_tier_order",
        ),
        CheckConstraint(
            "json_valid(fantasy_positions_json) = 1 "
            "AND json_valid(safe_evidence_json) = 1",
            name="ck_post_draft_report_player_json",
        ),
        Index(
            "ix_post_draft_report_player_report_position",
            "report_id",
            "primary_position",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    report_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("post_draft_report.id", ondelete="CASCADE"),
        nullable=False,
    )
    player_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("player.id"),
        nullable=False,
    )
    overall_pick: Mapped[int] = mapped_column(Integer, nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    primary_position: Mapped[str] = mapped_column(String(16), nullable=False)
    fantasy_positions_json: Mapped[str] = mapped_column(Text, nullable=False)
    starter_assignment: Mapped[str | None] = mapped_column(String(64))
    saved_personal_rank: Mapped[int | None] = mapped_column(Integer)
    saved_tier_order: Mapped[int | None] = mapped_column(Integer)
    saved_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False)
    safe_evidence_json: Mapped[str] = mapped_column(Text, nullable=False)


class PostDraftReportSectionRow(Base):
    __tablename__ = "post_draft_report_section"
    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "section_key",
            name="uq_post_draft_report_section_report_key",
        ),
        CheckConstraint(
            "length(section_key) BETWEEN 1 AND 80",
            name="ck_post_draft_report_section_key",
        ),
        CheckConstraint(
            "availability IN ('supported', 'limited', 'unavailable', "
            "'not_applicable')",
            name="ck_post_draft_report_section_availability",
        ),
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low', 'unavailable')",
            name="ck_post_draft_report_section_confidence",
        ),
        CheckConstraint(
            "length(explanation_template_key) BETWEEN 1 AND 100 "
            "AND length(explanation) >= 1",
            name="ck_post_draft_report_section_explanation",
        ),
        CheckConstraint(
            "json_valid(metrics_json) = 1 "
            "AND json_valid(reason_codes_json) = 1 "
            "AND json_valid(limitation_codes_json) = 1 "
            "AND json_valid(safe_provenance_json) = 1",
            name="ck_post_draft_report_section_json",
        ),
        Index(
            "ix_post_draft_report_section_report_availability",
            "report_id",
            "availability",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    report_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("post_draft_report.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_key: Mapped[str] = mapped_column(String(80), nullable=False)
    availability: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    limitation_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    explanation_template_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    safe_provenance_json: Mapped[str] = mapped_column(Text, nullable=False)


class PostDraftReportMomentRow(Base):
    __tablename__ = "post_draft_report_moment"
    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "moment_key",
            name="uq_post_draft_report_moment_report_key",
        ),
        CheckConstraint(
            "length(moment_key) BETWEEN 1 AND 128",
            name="ck_post_draft_report_moment_key",
        ),
        CheckConstraint(
            "moment_kind IN ('personal_board_choice', 'strategy_pivot', "
            "'strategy_guidance', 'alert_event')",
            name="ck_post_draft_report_moment_kind",
        ),
        CheckConstraint(
            "overall_pick IS NULL OR overall_pick >= 1",
            name="ck_post_draft_report_moment_pick",
        ),
        CheckConstraint(
            "primary_player_id IS NULL OR secondary_player_id IS NULL "
            "OR primary_player_id != secondary_player_id",
            name="ck_post_draft_report_moment_distinct_players",
        ),
        CheckConstraint(
            "json_valid(safe_summary_json) = 1 "
            "AND json_valid(reason_codes_json) = 1 "
            "AND json_valid(limitation_codes_json) = 1",
            name="ck_post_draft_report_moment_json",
        ),
        Index(
            "ix_post_draft_report_moment_report_kind_pick",
            "report_id",
            "moment_kind",
            "overall_pick",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    report_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("post_draft_report.id", ondelete="CASCADE"),
        nullable=False,
    )
    moment_key: Mapped[str] = mapped_column(String(128), nullable=False)
    moment_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    overall_pick: Mapped[int | None] = mapped_column(Integer)
    primary_player_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("player.id"),
    )
    secondary_player_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("player.id"),
    )
    safe_summary_json: Mapped[str] = mapped_column(Text, nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    limitation_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
