from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class LeagueIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    sport: Literal["nfl"]
    season: int
    league_type: Literal["dynasty", "keeper", "redraft", "unknown"]
    status: Literal["pre_draft", "drafting", "in_season", "complete", "unknown"]
    team_count: int


class LeagueProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    imported_at: str
    source_as_of: str | None
    sanitized: bool


class LeagueProfileDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    profile_id: str
    league: LeagueIdentity
    roster: dict[str, Any]
    scoring: dict[str, Any]
    management: dict[str, Any]
    playoffs: dict[str, Any]
    drafts: list[dict[str, Any]]
    unmapped_provider_settings: dict[str, Any]
    provenance: LeagueProvenance


class LeagueProfileSummary(BaseModel):
    id: str
    profile_id: str
    name: str
    season: int
    league_type: str
    team_count: int
    sanitized: bool
    imported_at: str
    source_as_of: str | None
