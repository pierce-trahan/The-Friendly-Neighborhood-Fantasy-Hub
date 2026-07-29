from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from friendly_hub.domains.alerts.definitions import (
    DEFAULT_ELIGIBLE_TIER_COUNT,
    DEFAULT_SNOOZE_PICK_COUNT,
    DEFAULT_VALUE_GAP_MINIMUM,
)

SourceKind = Literal["synthetic", "user_entered", "public", "licensed"]
LeagueType = Literal["dynasty", "keeper", "redraft"]
DraftPurpose = Literal["startup", "rookie", "supplemental"]
DraftFormat = Literal["snake", "linear"]
QuarterbackMode = Literal["one_qb", "superflex"]
ReceptionScoring = Literal["standard", "half_ppr", "ppr"]
MappingStatus = Literal[
    "matched",
    "review_required",
    "unmatched",
    "ignored",
    "invalid",
]
FormatCompatibility = Literal[
    "exact",
    "family",
    "partial",
    "incompatible",
    "unknown",
]
PersonalQualifierMode = Literal[
    "tier_or_favorite",
    "tier_only",
    "favorite_only",
]


class AlertEvidencePreviewMetadata(BaseModel):
    snapshot_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    source_label: str = Field(min_length=1, max_length=120)
    source_kind: SourceKind
    source_namespace: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    permitted_use_confirmed: bool
    private_source_reference: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
    )
    as_of: datetime
    league_type: LeagueType
    draft_purpose: DraftPurpose
    team_count: int = Field(ge=2, le=32)
    draft_format: DraftFormat
    third_round_reversal: bool
    round_count: int = Field(ge=1, le=60)
    quarterback_mode: QuarterbackMode
    reception_scoring: ReceptionScoring
    tight_end_premium: bool
    supported_draft_depth: int = Field(ge=1, le=10000)

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of must include a UTC offset")
        return value

    @model_validator(mode="after")
    def validate_draft_shape(self) -> AlertEvidencePreviewMetadata:
        if self.draft_format == "linear" and self.third_round_reversal:
            raise ValueError("linear drafts cannot use third-round reversal")
        return self


class AlertEvidencePreviewRequest(BaseModel):
    player_filename: str = Field(
        default="player-signals.csv",
        min_length=1,
        max_length=200,
    )
    player_csv_text: str = Field(min_length=1, max_length=2_100_000)
    pick_filename: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    pick_csv_text: str | None = Field(
        default=None,
        max_length=1_100_000,
    )
    metadata: AlertEvidencePreviewMetadata

    @model_validator(mode="after")
    def validate_optional_pick_file(self) -> AlertEvidencePreviewRequest:
        has_name = self.pick_filename is not None
        has_text = self.pick_csv_text is not None
        if has_name != has_text:
            raise ValueError("pick_filename and pick_csv_text must be provided together")
        return self


class AlertEvidenceCandidateRead(BaseModel):
    id: str
    display_name: str
    position: str
    team: str | None


class AlertEvidenceMappingRowRead(BaseModel):
    id: str
    row_number: int
    source_player_key: str
    display_name: str
    position: str
    team: str | None
    status: MappingStatus
    resolved_player_id: str | None
    candidates: list[AlertEvidenceCandidateRead]
    reason_code: str
    limitation_codes: list[str]


class AlertEvidenceSourceSummary(BaseModel):
    label: str
    kind: SourceKind
    namespace: str
    permitted_use_confirmed: bool
    as_of: str


class AlertEvidenceFormatSummary(BaseModel):
    league_type: LeagueType
    draft_purpose: DraftPurpose
    team_count: int
    draft_format: DraftFormat
    third_round_reversal: bool
    rounds: int
    qb_mode: QuarterbackMode
    reception_scoring: ReceptionScoring
    te_premium: bool


class AlertEvidencePreviewRead(BaseModel):
    schema_version: int
    id: str
    status: Literal["preview", "committed"]
    content_hash: str
    source: AlertEvidenceSourceSummary
    format: AlertEvidenceFormatSummary
    supported_draft_depth: int
    freshness_states: dict[str, str]
    total_player_count: int
    valid_player_count: int
    matched_player_count: int
    review_required_player_count: int
    unmatched_player_count: int
    ignored_player_count: int
    invalid_player_count: int
    total_pick_value_count: int
    valid_pick_value_count: int
    expected_selection_available: bool
    pick_curve_available: bool
    warnings: list[str]
    limitation_codes: list[str]
    rows: list[AlertEvidenceMappingRowRead]
    committed_snapshot_id: str | None


class AlertEvidenceMappingDecisionRequest(BaseModel):
    decision: Literal["confirm", "ignore", "reject", "clear"]
    player_id: str | None = None

    @model_validator(mode="after")
    def require_player_for_confirmation(
        self,
    ) -> AlertEvidenceMappingDecisionRequest:
        if self.decision == "confirm" and not self.player_id:
            raise ValueError("player_id is required when confirming a mapping")
        if self.decision != "confirm" and self.player_id is not None:
            raise ValueError("player_id is accepted only for confirm decisions")
        return self


class AlertEvidenceCommitRequest(BaseModel):
    content_hash: str = Field(min_length=64, max_length=64)
    permitted_use_confirmed: bool


class AlertEvidenceSnapshotSummaryRead(BaseModel):
    id: str
    schema_version: int
    source_label: str
    source_kind: SourceKind
    source_namespace: str
    source_as_of: str
    imported_at: str
    content_hash: str
    status: str
    format: AlertEvidenceFormatSummary
    supported_draft_depth: int
    freshness_states: dict[str, str]
    mapped_player_count: int
    expected_selection_count: int
    pick_value_count: int
    expected_selection_available: bool
    pick_curve_available: bool
    compatibility_state: Literal[
        "not_evaluated",
        "exact",
        "family",
        "partial",
        "incompatible",
        "unknown",
    ]
    limitation_codes: list[str]


class AlertEvidenceSnapshotListResponse(BaseModel):
    items: list[AlertEvidenceSnapshotSummaryRead]
    total: int
    limit: int
    offset: int


class AlertEvidenceCommitResponse(BaseModel):
    snapshot: AlertEvidenceSnapshotSummaryRead
    idempotent: bool


class DraftAlertConfigurationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_revision: int = Field(ge=0)
    evidence_snapshot_id: str = Field(min_length=1, max_length=36)
    enabled: bool = True
    personal_qualifier_mode: PersonalQualifierMode = "tier_or_favorite"
    eligible_tier_count: int = Field(
        default=DEFAULT_ELIGIBLE_TIER_COUNT,
        ge=0,
        le=100,
    )
    minimum_conservative_gap: int = Field(
        default=DEFAULT_VALUE_GAP_MINIMUM,
        ge=0,
        le=10_000,
    )
    snooze_pick_count: int = Field(
        default=DEFAULT_SNOOZE_PICK_COUNT,
        ge=1,
        le=100,
    )


class DraftAlertConfigurationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_revision: int = Field(ge=0)
    configuration_revision: int = Field(ge=0)
    evidence_snapshot_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=36,
    )
    enabled: bool | None = None
    personal_qualifier_mode: PersonalQualifierMode | None = None
    eligible_tier_count: int | None = Field(default=None, ge=0, le=100)
    minimum_conservative_gap: int | None = Field(
        default=None,
        ge=0,
        le=10_000,
    )
    snooze_pick_count: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def require_change(self) -> DraftAlertConfigurationPatch:
        changes = self.model_dump(
            exclude={"draft_revision", "configuration_revision"},
            exclude_none=True,
        )
        if not changes:
            raise ValueError("at least one configuration change is required")
        return self


class DraftAlertConfigurationRead(BaseModel):
    id: str
    draft_session_id: str
    draft_revision: int
    evidence_snapshot_id: str
    enabled: bool
    personal_qualifier_mode: PersonalQualifierMode
    eligible_tier_count: int
    minimum_conservative_gap: int
    snooze_pick_count: int
    engine_version: str
    rule_version: str
    freshness_policy_version: str
    revision: int
    format_compatibility: FormatCompatibility
    compatibility_reasons: list[str]
    evidence_snapshot: AlertEvidenceSnapshotSummaryRead
    created_at: str
    updated_at: str
