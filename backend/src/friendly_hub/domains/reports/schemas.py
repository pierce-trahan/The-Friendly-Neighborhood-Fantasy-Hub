from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PostDraftReportGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_revision: int = Field(ge=0)
    expected_completed_at: datetime

    @field_validator("expected_completed_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expected_completed_at must include a UTC offset")
        return value.astimezone(UTC)


class PostDraftReportSectionRead(BaseModel):
    section_key: str
    title: str
    availability: Literal["supported", "limited", "unavailable", "not_applicable"]
    confidence: Literal["high", "medium", "low", "unavailable"]
    metrics: dict[str, Any]
    reason_codes: list[str]
    limitation_codes: list[str]
    explanation_template_key: str
    explanation: str
    safe_provenance: dict[str, Any]


class PostDraftReportPlayerRead(BaseModel):
    player_id: str
    display_name: str
    overall_pick: int
    round_number: int
    primary_position: str
    fantasy_positions: list[str]
    starter_assignment: str | None
    saved_personal_rank: int | None
    saved_tier_order: int | None
    saved_favorite: bool


class PostDraftReportMomentRead(BaseModel):
    moment_key: str
    moment_kind: Literal[
        "personal_board_choice",
        "strategy_pivot",
        "strategy_guidance",
        "alert_event",
    ]
    overall_pick: int | None
    primary_player_id: str | None
    secondary_player_id: str | None
    safe_summary: dict[str, Any]
    reason_codes: list[str]
    limitation_codes: list[str]


class PostDraftReportRead(BaseModel):
    id: str
    draft_session_id: str
    draft_name: str
    draft_mode: Literal["live", "mock"]
    draft_revision: int
    completed_at: str
    generated_at: str
    report_engine_version: str
    report_rules_version: str
    explanation_template_version: str
    league_shape_fingerprint: str
    summary: dict[str, Any]
    section_summary: dict[str, str]
    sections: list[PostDraftReportSectionRead]
    roster: list[PostDraftReportPlayerRead]
    moments: list[PostDraftReportMomentRead]
    limitations: list[str]
    comparison_eligible: bool
    export_available: bool
    available_actions: list[str]


class PostDraftReportGenerateResponse(BaseModel):
    idempotent: bool
    report: PostDraftReportRead


class PostDraftReportSummaryRead(BaseModel):
    id: str
    draft_session_id: str
    draft_name: str
    draft_mode: Literal["live", "mock"]
    draft_revision: int
    completed_at: str
    generated_at: str
    report_engine_version: str
    report_rules_version: str
    explanation_template_version: str
    league_shape_fingerprint: str
    draft_format: Literal["snake", "linear"]
    team_count: int = Field(ge=2, le=32)
    round_count: int = Field(ge=1, le=60)
    initial_strategy: str | None
    final_strategy: str | None
    strategy_definition_version: str | None
    section_summary: dict[str, str]
    limitations: list[str]


class PostDraftReportListResponse(BaseModel):
    items: list[PostDraftReportSummaryRead]
    total: int
    limit: int
    offset: int


class PostDraftReportComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_ids: list[str] = Field(min_length=2, max_length=4)

    @field_validator("report_ids")
    @classmethod
    def require_unique_nonempty_ids(cls, value: list[str]) -> list[str]:
        if any(
            not report_id
            or report_id != report_id.strip()
            or len(report_id) > 36
            for report_id in value
        ):
            raise ValueError("report_ids must contain bounded canonical ids")
        if len(value) != len(set(value)):
            raise ValueError("report_ids must be unique")
        return value


class PostDraftReportComparisonIdentityRead(BaseModel):
    report_id: str
    draft_session_id: str
    draft_name: str
    draft_mode: Literal["live", "mock"]
    completed_at: str
    draft_format: str
    team_count: int
    round_count: int
    initial_strategy: str | None
    final_strategy: str | None
    strategy_definition_version: str | None
    report_engine_version: str
    report_rules_version: str
    explanation_template_version: str
    league_shape_fingerprint: str


class PostDraftReportComparisonValueRead(BaseModel):
    report_id: str
    availability: Literal["supported", "limited", "unavailable", "not_applicable"]
    confidence: Literal["high", "medium", "low", "unavailable"]
    metrics: dict[str, Any]
    delta_from_first: dict[str, Any]


class PostDraftReportComparisonSectionRead(BaseModel):
    section_key: str
    title: str
    comparison_state: Literal["comparable", "not_comparable"]
    values: list[PostDraftReportComparisonValueRead]
    reason_codes: list[str]
    limitation_codes: list[str]
    explanation_template_key: str
    explanation: str


class PostDraftReportComparisonRead(BaseModel):
    report_count: int
    baseline_report_id: str
    league_shape_fingerprint: str
    report_rules_version: str
    reports: list[PostDraftReportComparisonIdentityRead]
    sections: list[PostDraftReportComparisonSectionRead]
    limitations: list[str]
    explanation_template_key: str
    explanation: str
