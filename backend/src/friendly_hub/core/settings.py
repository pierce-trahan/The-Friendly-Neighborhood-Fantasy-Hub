from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeSettings:
    project_root: Path
    data_dir: Path
    database_path: Path
    log_dir: Path
    frontend_dist: Path
    sample_fixture_path: Path
    player_fixture_path: Path

    @classmethod
    def from_environment(cls) -> RuntimeSettings:
        project_root = Path(__file__).resolve().parents[4]
        configured_data_dir = os.environ.get("FRIENDLY_HUB_DATA_DIR")
        if configured_data_dir:
            data_dir = Path(configured_data_dir).expanduser().resolve()
        else:
            local_app_data = os.environ.get("LOCALAPPDATA")
            base_dir = Path(local_app_data) if local_app_data else Path.home() / ".local" / "share"
            data_dir = base_dir / "FriendlyNeighborhoodFantasyHub"

        fixture_override = os.environ.get("FRIENDLY_HUB_SAMPLE_FIXTURE")
        sample_fixture_path = (
            Path(fixture_override).expanduser().resolve()
            if fixture_override
            else project_root
            / "tests"
            / "fixtures"
            / "league_profiles"
            / "entropy-2026.sanitized.json"
        )
        player_fixture_override = os.environ.get("FRIENDLY_HUB_PLAYER_FIXTURE")
        player_fixture_path = (
            Path(player_fixture_override).expanduser().resolve()
            if player_fixture_override
            else project_root
            / "tests"
            / "fixtures"
            / "players"
            / "phase-1-players.sanitized.json"
        )

        return cls(
            project_root=project_root,
            data_dir=data_dir,
            database_path=data_dir / "hub.sqlite3",
            log_dir=data_dir / "logs",
            frontend_dist=project_root / "frontend" / "dist",
            sample_fixture_path=sample_fixture_path,
            player_fixture_path=player_fixture_path,
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        for directory in ("backups", "exports", "cache", "recovery"):
            (self.data_dir / directory).mkdir(exist_ok=True)
