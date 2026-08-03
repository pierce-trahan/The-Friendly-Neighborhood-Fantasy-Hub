from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from friendly_hub.db.engine import create_database_engine, create_session_factory
from friendly_hub.domains.players.models import (
    PlayerExternalIdRow,
    PlayerImportSessionRow,
    PlayerRow,
)
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}


def _player(name: str, external_id: str, position: str = "WR") -> dict[str, object]:
    return {
        "name": name,
        "position": position,
        "fantasy_positions": [position],
        "team": "CHI",
        "status": "active",
        "rookie_class": 2026,
        "is_rookie": True,
        "provider": "nflverse",
        "external_id": external_id,
        "include": True,
    }


def _write_snapshot(path: Path, players: list[dict[str, object]]) -> Path:
    document = {
        "schema_version": 1,
        "source": {
            "name": "nflverse",
            "dataset": "players",
            "url": "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv",
            "license": "CC BY 4.0",
            "license_url": "https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md",
            "source_asset_updated_at": "2026-08-02T09:52:58Z",
            "source_sha256": "test-source-hash",
            "transformed": True,
        },
        "snapshot": {"season": 2026, "minimum_last_season": 2025, "player_count": len(players)},
        "players": players,
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_fresh_offline_launch_seeds_players_and_repeat_launch_is_idempotent(
    runtime_settings,
    tmp_path: Path,
) -> None:
    snapshot_path = _write_snapshot(
        tmp_path / "players.json",
        [
            _player("Alpha Quarterback", "00-test-1", "QB"),
            _player("Beta Runner", "00-test-2", "RB"),
            _player("Gamma Receiver", "00-test-3"),
        ],
    )
    runtime = replace(runtime_settings, bundled_player_snapshot_path=snapshot_path)

    with TestClient(create_app(runtime), headers=TRUSTED_HEADERS) as client:
        response = client.get("/api/v1/players?limit=100")
        assert response.status_code == 200
        assert response.json()["total"] == 3
        assert {row["display_name"] for row in response.json()["items"]} == {
            "Alpha Quarterback",
            "Beta Runner",
            "Gamma Receiver",
        }

    with TestClient(create_app(runtime), headers=TRUSTED_HEADERS) as client:
        assert client.get("/api/v1/players?limit=100").json()["total"] == 3

    engine = create_database_engine(runtime.database_path)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PlayerRow)) == 3
        assert session.scalar(select(func.count()).select_from(PlayerExternalIdRow)) == 3
        imports = list(
            session.scalars(
                select(PlayerImportSessionRow).where(
                    PlayerImportSessionRow.source == "nflverse_snapshot"
                )
            )
        )
        assert len(imports) == 1
        assert imports[0].status == "committed"
        assert imports[0].new_count == 3
    engine.dispose()


def test_seed_skips_uncertain_manual_name_collision_without_duplication(
    runtime_settings,
    tmp_path: Path,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        preview = client.post(
            "/api/v1/player-imports/csv/preview",
            json={
                "filename": "manual.csv",
                "csv_text": "name,position,team,status\nCollision Player,WR,CHI,active\n",
            },
        )
        assert preview.status_code == 201
        committed = client.post(
            f"/api/v1/player-imports/{preview.json()['id']}/commit"
        )
        assert committed.status_code == 200

    snapshot_path = _write_snapshot(
        tmp_path / "players.json",
        [
            _player("Collision Player", "00-collision"),
            _player("New Player", "00-new", "QB"),
        ],
    )
    runtime = replace(runtime_settings, bundled_player_snapshot_path=snapshot_path)
    with TestClient(create_app(runtime), headers=TRUSTED_HEADERS) as client:
        players = client.get("/api/v1/players?limit=100").json()
        assert players["total"] == 2
        assert [row["display_name"] for row in players["items"]].count("Collision Player") == 1

    engine = create_database_engine(runtime.database_path)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        assert session.scalar(
            select(PlayerExternalIdRow).where(
                PlayerExternalIdRow.provider == "nflverse",
                PlayerExternalIdRow.external_id == "00-collision",
            )
        ) is None
        seed_import = session.scalar(
            select(PlayerImportSessionRow).where(
                PlayerImportSessionRow.source == "nflverse_snapshot"
            )
        )
        assert seed_import is not None
        assert seed_import.new_count == 1
        assert seed_import.ignored_count == 1
    engine.dispose()


def test_new_snapshot_preserves_exact_id_player_corrections(
    runtime_settings,
    tmp_path: Path,
) -> None:
    first_snapshot = _write_snapshot(
        tmp_path / "players-v1.json",
        [_player("Original Name", "00-stable", "QB")],
    )
    first_runtime = replace(runtime_settings, bundled_player_snapshot_path=first_snapshot)
    with TestClient(create_app(first_runtime), headers=TRUSTED_HEADERS) as client:
        player = client.get("/api/v1/players?limit=100").json()["items"][0]
        corrected = client.patch(
            f"/api/v1/players/{player['id']}",
            json={"display_name": "My Corrected Name", "team": "FA"},
        )
        assert corrected.status_code == 200

    second_snapshot = _write_snapshot(
        tmp_path / "players-v2.json",
        [
            _player("Upstream Replacement", "00-stable", "QB"),
            _player("Added Later", "00-added", "TE"),
        ],
    )
    second_runtime = replace(runtime_settings, bundled_player_snapshot_path=second_snapshot)
    with TestClient(create_app(second_runtime), headers=TRUSTED_HEADERS) as client:
        players = client.get("/api/v1/players?limit=100").json()
        assert players["total"] == 2
        preserved = next(row for row in players["items"] if row["id"] == player["id"])
        assert preserved["display_name"] == "My Corrected Name"
        assert preserved["team"] == "FA"


def test_invalid_snapshot_never_partially_seeds_players(
    runtime_settings,
    tmp_path: Path,
) -> None:
    snapshot_path = _write_snapshot(
        tmp_path / "invalid.json",
        [_player("Valid First", "00-duplicate"), _player("Duplicate Second", "00-duplicate")],
    )
    runtime = replace(runtime_settings, bundled_player_snapshot_path=snapshot_path)

    try:
        with TestClient(create_app(runtime), headers=TRUSTED_HEADERS):
            raise AssertionError("The invalid snapshot should stop application startup.")
    except RuntimeError as exc:
        assert "repeats ID" in str(exc)

    engine = create_database_engine(runtime.database_path)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PlayerRow)) == 0
    engine.dispose()


def test_release_snapshot_is_attributed_and_seeds_expected_player_count(
    runtime_settings,
) -> None:
    snapshot_path = (
        runtime_settings.project_root
        / "data"
        / "player_universe"
        / "nflverse-players-2026.json"
    )
    document = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert document["source"]["name"] == "nflverse"
    assert document["source"]["license"] == "CC BY 4.0"
    assert document["source"]["source_asset_updated_at"] == "2026-08-02T09:52:58Z"
    assert document["source"]["transformed"] is True
    assert document["snapshot"]["player_count"] == 1148
    assert len(document["players"]) == 1148
    assert len({player["external_id"] for player in document["players"]}) == 1148

    runtime = replace(runtime_settings, bundled_player_snapshot_path=snapshot_path)
    with TestClient(create_app(runtime), headers=TRUSTED_HEADERS) as client:
        response = client.get("/api/v1/players?limit=500")
        assert response.status_code == 200
        assert response.json()["total"] == 1148
