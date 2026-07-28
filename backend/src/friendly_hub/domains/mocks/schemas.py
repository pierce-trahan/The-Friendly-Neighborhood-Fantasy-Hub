from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from friendly_hub.domains.drafts.schemas import DraftFormat, DraftSessionRead, TeamName
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
    previous_strategy_key: str | None
    next_strategy_key: str
    effective_overall_pick: int
    user_roster_counts: dict[str, int]
    created_at: str


class MockGuidanceRead(BaseModel):
    id: str
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
    reason_codes: list[str]
    limitation_codes: list[str]
    explanation_template_key: str
    pivot_template_key: str | None
    status: Literal["open", "acknowledged", "dismissed"]
    created_at: str
    resolved_at: str | None


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
    revision: int
    include_in_learning: bool
    learning_opted_in_at: str | None
    learning_withdrawn_at: str | None
    created_at: str
    updated_at: str


class MockSessionRead(BaseModel):
    practice_simulation: Literal[True] = True
    draft: DraftSessionRead
    mock: MockConfigurationRead
    current_strategy_revision: MockStrategyRevisionRead
    user_roster_counts: dict[str, int]
    current_checkpoint: MockGuidanceRead
    guidance: list[MockGuidanceRead]
    cpu_profiles: list[MockCpuProfileRead]
    last_cpu_decision: None = None
    can_advance_cpu: bool
    recovery_guidance: str | None
