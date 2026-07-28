from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from friendly_hub.domains.drafts.schemas import (
    DraftFormat,
    DraftSessionRead,
    DraftStatus,
    TeamName,
)
from friendly_hub.domains.mocks.definitions import (
    MAX_RANDOMNESS,
    SUPPORTED_FALLBACK_ARCHETYPES,
    SUPPORTED_STRATEGIES,
)
from friendly_hub.domains.mocks.engine import normalize_seed


class MockSessionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    league_profile_id: str | None = Field(default=None, max_length=36)
    draft_format: DraftFormat = "snake"
    third_round_reversal: bool = False
    team_count: int = Field(ge=2, le=32)
    round_count: int = Field(ge=1, le=60)
    user_slot: int = Field(ge=1, le=32)
    pick_timer_seconds: int | None = Field(default=None, ge=1, le=86_400)
    team_names: list[TeamName] | None = Field(
        default=None, min_length=2, max_length=32
    )
    seed: str
    randomness: int = Field(ge=0, le=MAX_RANDOMNESS)
    strategy_key: str = Field(min_length=1, max_length=32)
    fallback_archetypes: dict[int, str] = Field(default_factory=dict)
    include_in_learning: bool = False

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must contain at least one visible character")
        return cleaned

    @field_validator("team_names")
    @classmethod
    def normalize_team_names(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [team_name.strip() for team_name in value]
        if any(not team_name for team_name in cleaned):
            raise ValueError("every team name must contain a visible character")
        return cleaned

    @field_validator("seed")
    @classmethod
    def validate_seed(cls, value: str) -> str:
        return normalize_seed(value)

    @field_validator("strategy_key")
    @classmethod
    def validate_strategy(cls, value: str) -> str:
        if value not in SUPPORTED_STRATEGIES:
            raise ValueError("strategy_key is not supported")
        return value

    @field_validator("fallback_archetypes")
    @classmethod
    def validate_archetypes(cls, value: dict[int, str]) -> dict[int, str]:
        unknown = sorted(set(value.values()) - set(SUPPORTED_FALLBACK_ARCHETYPES))
        if unknown:
            raise ValueError(f"unsupported fallback archetype: {unknown[0]}")
        return value

    @model_validator(mode="after")
    def validate_configuration(self) -> MockSessionCreate:
        if self.third_round_reversal and self.draft_format != "snake":
            raise ValueError("third-round reversal is valid only for snake drafts")
        if self.user_slot > self.team_count:
            raise ValueError("user_slot cannot exceed team_count")
        if self.team_names is not None and len(self.team_names) != self.team_count:
            raise ValueError("team_names must contain one name per draft slot")
        invalid_slots = sorted(
            slot
            for slot in self.fallback_archetypes
            if slot < 1 or slot > self.team_count or slot == self.user_slot
        )
        if invalid_slots:
            raise ValueError(
                "fallback_archetypes may target only configured non-user slots"
            )
        return self


class MockCpuProfileRead(BaseModel):
    draft_slot: int
    source: Literal["fallback", "history"]
    archetype_key: str
    confidence: Literal["not_applicable", "low", "medium", "high"]
    draft_sample_count: int
    pick_sample_count: int


class MockStrategyRevisionRead(BaseModel):
    sequence_number: int
    reason: Literal["initial_strategy", "user_pivot"]
    previous_strategy_key: str | None
    next_strategy_key: str
    effective_overall_pick: int
    user_roster_counts: dict[str, int]
    created_at: str


class MockGuidanceRead(BaseModel):
    id: str
    strategy_key: str
    strategy_definition_version: str
    effective_overall_pick: int
    state: Literal[
        "on_plan",
        "watch",
        "off_plan_viable",
        "risk_checkpoint",
        "insufficient_evidence",
    ]
    confidence: Literal["unavailable", "low", "medium", "high"]
    observed_counts: dict[str, int]
    target_ranges: dict[str, object]
    affected_positions: list[str]
    reason_codes: list[str]
    limitation_codes: list[str]
    explanation_template_key: str
    explanation: str
    pivot_template_key: str | None
    viable_pivot_explanation: str | None
    status: Literal["open", "acknowledged", "dismissed"]
    created_at: str
    resolved_at: str | None


class MockStrategyPivotCreate(BaseModel):
    mock_revision: int = Field(ge=0)
    expected_current_overall_pick: int = Field(ge=1)
    strategy_key: str = Field(min_length=1, max_length=32)
    private_user_note: str | None = Field(default=None, max_length=5_000)

    @field_validator("strategy_key")
    @classmethod
    def validate_strategy(cls, value: str) -> str:
        if value not in SUPPORTED_STRATEGIES:
            raise ValueError("strategy_key is not supported")
        return value

    @field_validator("private_user_note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class MockGuidanceStatusPatch(BaseModel):
    mock_revision: int = Field(ge=0)
    status: Literal["open", "acknowledged", "dismissed"]


class MockGuidanceListResponse(BaseModel):
    items: list[MockGuidanceRead]
    total: int
    limit: int
    offset: int


class MockLearningPatch(BaseModel):
    mock_revision: int = Field(ge=0)
    include_in_learning: bool


class MockHistorySummaryRead(BaseModel):
    session_id: str
    name: str
    status: DraftStatus
    completion_state: Literal["incomplete", "completed", "reset"]
    seed: str
    randomness: int
    current_strategy_key: str
    pivot_count: int
    mock_revision: int
    draft_format: DraftFormat
    third_round_reversal: bool
    team_count: int
    round_count: int
    user_slot: int
    include_in_learning: bool
    learning_opted_in_at: str | None
    learning_withdrawn_at: str | None
    rng_version: str
    cpu_engine_version: str
    strategy_definition_version: str
    created_at: str
    updated_at: str
    completed_at: str | None
    reset_at: str | None


class MockHistoryListResponse(BaseModel):
    items: list[MockHistorySummaryRead]
    total: int
    limit: int
    offset: int


class MockConfigurationRead(BaseModel):
    seed: str
    rng_version: str
    cpu_engine_version: str
    strategy_definition_version: str
    content_fingerprint: str
    randomness: int
    current_strategy_key: str
    strategy_compatibility: Literal["compatible", "reduced"]
    strategy_limitations: list[str]
    reset_replay_status: Literal[
        "original",
        "exact_replay",
        "new_seed",
        "snapshot_changed",
        "unavailable",
    ]
    revision: int
    include_in_learning: bool
    learning_opted_in_at: str | None
    learning_withdrawn_at: str | None
    created_at: str
    updated_at: str


class MockCpuPickCreate(BaseModel):
    draft_revision: int = Field(ge=0)
    mock_revision: int = Field(ge=0)
    expected_overall_pick: int = Field(ge=1)
    expected_selecting_slot: int = Field(ge=1)


class MockScoreComponentsRead(BaseModel):
    board_order: int
    starter_need: int
    depth_need: int
    archetype_fit: int
    duplication_penalty: int
    random_variation: int


class MockPickDecisionSummary(BaseModel):
    id: str
    overall_pick: int
    selecting_slot: int
    chosen_player_id: str
    chosen_player_display_name: str
    chosen_player_position: str
    profile_source: Literal["fallback", "history"]
    profile_archetype_key: str
    profile_confidence: Literal["not_applicable", "low", "medium", "high"]
    engine_version: str
    rng_version: str
    total_score: int
    component_scores: MockScoreComponentsRead
    reason_codes: list[str]
    limitation_codes: list[str]
    decision_status: Literal["active", "historical"]
    manually_corrected: bool
    created_at: str


class MockDecisionAlternativeRead(BaseModel):
    player_id: str
    total_score: int
    component_scores: MockScoreComponentsRead


class MockPickDecisionAudit(MockPickDecisionSummary):
    random_audit: dict[str, object]
    alternatives: list[MockDecisionAlternativeRead]


class MockSessionRead(BaseModel):
    practice_simulation: Literal[True] = True
    draft: DraftSessionRead
    mock: MockConfigurationRead
    current_strategy_revision: MockStrategyRevisionRead
    user_roster_counts: dict[str, int]
    current_checkpoint: MockGuidanceRead
    guidance: list[MockGuidanceRead]
    cpu_profiles: list[MockCpuProfileRead]
    last_cpu_decision: MockPickDecisionSummary | None = None
    can_advance_cpu: bool
    recovery_guidance: str | None
