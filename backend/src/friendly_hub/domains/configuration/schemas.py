from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DisplayConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str
    theme: Literal["system", "light", "dark"]
    reduced_motion: bool


class BackupConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    automatic: bool
    retention_count: int = Field(ge=1, le=50)


class SafetyConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm_reset: bool
    confirm_delete: bool


class AppConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    active_league_season_id: str | None
    display: DisplayConfiguration
    backups: BackupConfiguration
    safety: SafetyConfiguration


def default_configuration() -> AppConfiguration:
    return AppConfiguration(
        schema_version=1,
        active_league_season_id=None,
        display=DisplayConfiguration(
            timezone="America/Chicago",
            theme="system",
            reduced_motion=False,
        ),
        backups=BackupConfiguration(automatic=True, retention_count=10),
        safety=SafetyConfiguration(confirm_reset=True, confirm_delete=True),
    )
