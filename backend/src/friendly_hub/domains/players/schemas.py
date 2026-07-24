from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PlayerPosition = Literal["QB", "RB", "WR", "TE", "K", "DEF", "UNKNOWN"]
PlayerStatus = Literal["active", "inactive", "injured", "reserve", "unknown"]
ImportOutcome = Literal["new", "matched", "changed", "ambiguous", "invalid", "ignored"]


class PlayerCandidate(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    first_name: str | None = None
    last_name: str | None = None
    suffix: str | None = None
    search_name: str
    team: str | None = None
    primary_position: PlayerPosition
    fantasy_positions: list[PlayerPosition] = Field(min_length=1)
    status: PlayerStatus
    rookie_class: int | None = Field(default=None, ge=1900, le=2200)
    is_rookie: bool = False
    provider: str | None = None
    external_id: str | None = None
    include: bool = True


class PlayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    first_name: str | None
    last_name: str | None
    suffix: str | None
    team: str | None
    primary_position: PlayerPosition
    fantasy_positions: list[PlayerPosition]
    status: PlayerStatus
    rookie_class: int | None
    is_rookie: bool
    relevant: bool
    updated_at: str


class PlayerListResponse(BaseModel):
    items: list[PlayerRead]
    total: int
    limit: int
    offset: int


class PlayerPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    team: str | None = Field(default=None, max_length=8)
    primary_position: PlayerPosition | None = None
    fantasy_positions: list[PlayerPosition] | None = Field(default=None, min_length=1)
    status: PlayerStatus | None = None
    rookie_class: int | None = Field(default=None, ge=1900, le=2200)
    is_rookie: bool | None = None


class CsvPreviewRequest(BaseModel):
    filename: str = Field(default="players.csv", min_length=1, max_length=200)
    csv_text: str = Field(min_length=1, max_length=5_000_000)


class MappingDecisionRequest(BaseModel):
    decision: Literal["match_existing", "create_new", "ignore", "clear"]
    player_id: str | None = None
    note: str | None = Field(default=None, max_length=300)

    @field_validator("player_id")
    @classmethod
    def player_required_for_match(cls, value: str | None, info: object) -> str | None:
        data = getattr(info, "data", {})
        if data.get("decision") == "match_existing" and not value:
            raise ValueError("player_id is required when matching an existing player")
        return value


class PlayerImportRowRead(BaseModel):
    id: str
    row_number: int
    source_name: str | None
    candidate: PlayerCandidate | None
    outcome: ImportOutcome
    proposed_player_id: str | None
    resolved_player_id: str | None
    candidate_players: list[PlayerRead]
    reason_code: str
    explanation: str


class PlayerImportSessionRead(BaseModel):
    id: str
    source: str
    status: Literal["preview", "committed", "cancelled", "failed"]
    filename: str | None
    new_count: int
    matched_count: int
    changed_count: int
    ambiguous_count: int
    invalid_count: int
    ignored_count: int
    created_at: str
    committed_at: str | None
    rows: list[PlayerImportRowRead]


class PlayerImportCommitResponse(BaseModel):
    session: PlayerImportSessionRead
    created_players: int
    updated_players: int
    ignored_rows: int
