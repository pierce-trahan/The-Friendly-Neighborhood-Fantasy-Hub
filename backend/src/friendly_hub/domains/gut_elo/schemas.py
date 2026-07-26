from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from friendly_hub.domains.players.schemas import PlayerPosition, PlayerRead

GutEloQueueMode = Literal["board", "position", "tier", "uncertainty"]
GutEloStatus = Literal["active", "paused", "completed"]
GutEloOutcome = Literal["a_win", "b_win", "insufficient", "skip"]


class GutEloSessionCreate(BaseModel):
    queue_mode: GutEloQueueMode = "board"
    position: PlayerPosition | None = None
    tier_id: str | None = Field(default=None, max_length=36)
    target_count: int | None = Field(default=None, ge=1, le=40)


class GutEloSessionPatch(BaseModel):
    status: Literal["active", "paused"]


class GutEloActionCreate(BaseModel):
    revision: int = Field(ge=0)
    player_a_id: str = Field(min_length=1, max_length=36)
    player_b_id: str = Field(min_length=1, max_length=36)
    outcome: GutEloOutcome


class GutEloParticipantRead(BaseModel):
    player: PlayerRead
    starting_manual_rank: int
    starting_tier_name: str | None
    gut_rank: int
    rating: float
    decisive_count: int


class GutEloPairRead(BaseModel):
    revision: int
    player_a: PlayerRead
    player_b: PlayerRead


class GutEloActionRead(BaseModel):
    id: str
    sequence_number: int
    player_a_id: str
    player_b_id: str
    outcome: GutEloOutcome
    created_at: str


class GutEloProgressRead(BaseModel):
    resolved_count: int
    decisive_count: int
    insufficient_count: int
    skip_count: int
    target_count: int
    progress_percent: int
    participants_with_decision: int
    participant_count: int
    coverage_percent: int
    stability_label: Literal[
        "starting",
        "developing",
        "useful_signal",
        "still_moving",
    ]
    stability_explanation: str


class GutEloSessionSummary(BaseModel):
    id: str
    board_id: str
    board_name: str
    board_scope: Literal["overall", "rookie", "veteran"]
    queue_mode: GutEloQueueMode
    position: PlayerPosition | None
    tier_id: str | None
    status: GutEloStatus
    participant_count: int
    resolved_count: int
    target_count: int
    created_at: str
    updated_at: str
    completed_at: str | None


class GutEloSessionListResponse(BaseModel):
    items: list[GutEloSessionSummary]


class GutEloSessionRead(GutEloSessionSummary):
    revision: int
    participants: list[GutEloParticipantRead]
    progress: GutEloProgressRead
    actions: list[GutEloActionRead]
    next_pair: GutEloPairRead | None
    manual_board_unchanged: Literal[True] = True
