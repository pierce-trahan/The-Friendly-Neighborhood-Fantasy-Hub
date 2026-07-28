from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

DraftMode = Literal["live", "mock"]
DraftFormat = Literal["linear", "snake"]
DraftStatus = Literal["active", "paused", "completed", "reset"]
DraftView = Literal["blind", "personal", "position", "tier"]
TeamName = Annotated[str, Field(min_length=1, max_length=200)]


class DraftSessionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    mode: DraftMode = "live"
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

    @model_validator(mode="after")
    def validate_configuration(self) -> DraftSessionCreate:
        if self.third_round_reversal and self.draft_format != "snake":
            raise ValueError("third-round reversal is valid only for snake drafts")
        if self.user_slot > self.team_count:
            raise ValueError("user_slot cannot exceed team_count")
        if self.team_names is not None and len(self.team_names) != self.team_count:
            raise ValueError("team_names must contain one name per draft slot")
        return self


class DraftSessionPatch(BaseModel):
    revision: int = Field(ge=0)
    status: Literal["active", "paused"]


class DraftRevisionGuard(BaseModel):
    revision: int = Field(ge=0)


class DraftPickCreate(DraftRevisionGuard):
    expected_overall_pick: int = Field(ge=1)
    player_id: str = Field(min_length=1, max_length=36)
    client_entered_at: str | None = Field(default=None, max_length=64)


class DraftPickCorrection(DraftRevisionGuard):
    expected_current_player_id: str = Field(min_length=1, max_length=36)
    replacement_player_id: str = Field(min_length=1, max_length=36)


class DraftTeamRead(BaseModel):
    draft_slot: int
    display_name: str
    is_user: bool


class DraftCurrentPickRead(BaseModel):
    overall_pick: int
    round_number: int
    pick_in_round: int
    selecting_slot: int
    selecting_team: str


class DraftPickRead(DraftCurrentPickRead):
    player_id: str
    player_display_name: str
    player_position: str
    player_team: str | None
    recorded_at: str
    correction_count: int


class DraftSessionSummary(BaseModel):
    id: str
    name: str
    board_id: str
    board_name: str
    mode: DraftMode
    draft_format: DraftFormat
    third_round_reversal: bool
    team_count: int
    round_count: int
    user_slot: int
    status: DraftStatus
    revision: int
    active_pick_count: int
    total_picks: int
    created_at: str
    updated_at: str


class DraftSessionListResponse(BaseModel):
    items: list[DraftSessionSummary]


class DraftSessionRead(DraftSessionSummary):
    league_profile_id: str | None
    pick_timer_seconds: int | None
    reset_from_session_id: str | None
    teams: list[DraftTeamRead]
    current_pick: DraftCurrentPickRead | None
    user_on_the_clock: bool
    picks_until_user: int | None
    picks: list[DraftPickRead]
    candidate_total: int
    available_count: int
    blind_data_hidden: Literal[True] = True
    recommendation_state_present: Literal[False] = False
    completed_at: str | None
    reset_at: str | None
    recovery_guidance: str | None


class DraftBlindCandidateRead(BaseModel):
    player_id: str
    display_name: str
    primary_position: str
    fantasy_positions: list[str]
    team: str | None
    player_status: str
    is_rookie: bool
    rookie_class: int | None
    drafted_overall_pick: int | None


class DraftContextCandidateRead(DraftBlindCandidateRead):
    snapshot_source: Literal["relevant_pool", "personal_board", "late_addition"]
    personal_rank: int | None
    tier_name: str | None
    tier_color: str | None
    favorite: bool
    board_note: str | None


class DraftBlindCandidateListResponse(BaseModel):
    view: Literal["blind"]
    items: list[DraftBlindCandidateRead]
    total: int
    limit: int
    offset: int


class DraftContextCandidateListResponse(BaseModel):
    view: Literal["personal", "position", "tier"]
    items: list[DraftContextCandidateRead]
    total: int
    limit: int
    offset: int


DraftCandidateListResponse = Annotated[
    DraftBlindCandidateListResponse | DraftContextCandidateListResponse,
    Field(discriminator="view"),
]
