from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from friendly_hub.domains.players.schemas import PlayerRead

BoardScope = Literal["overall", "rookie", "veteran"]


class BoardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    league_profile_id: str | None = None
    scope: BoardScope = "overall"


class BoardPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    league_profile_id: str | None = None
    scope: BoardScope | None = None
    archived: bool | None = None


class BoardSummary(BaseModel):
    id: str
    name: str
    description: str | None
    league_profile_id: str | None
    scope: BoardScope
    archived: bool
    entry_count: int
    created_at: str
    updated_at: str


class BoardListResponse(BaseModel):
    items: list[BoardSummary]


class BoardTierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str | None = Field(default=None, max_length=32)
    tier_order: int | None = Field(default=None, ge=1)


class BoardTierPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: str | None = Field(default=None, max_length=32)
    tier_order: int | None = Field(default=None, ge=1)


class BoardTierRead(BaseModel):
    id: str
    name: str
    color: str | None
    tier_order: int
    created_at: str
    updated_at: str


class BoardEntryCreate(BaseModel):
    player_id: str = Field(min_length=1, max_length=36)


class BoardEntryPatch(BaseModel):
    tier_id: str | None = Field(default=None, max_length=36)
    note: str | None = Field(default=None, max_length=5_000)
    favorite: bool | None = None


class BoardEntryRead(BaseModel):
    id: str
    player: PlayerRead
    tier_id: str | None
    rank: int
    note: str | None
    favorite: bool
    updated_at: str


class BoardRead(BoardSummary):
    tiers: list[BoardTierRead]
    entries: list[BoardEntryRead]


class BoardOrderUpdate(BaseModel):
    player_ids: list[str] = Field(max_length=500)
