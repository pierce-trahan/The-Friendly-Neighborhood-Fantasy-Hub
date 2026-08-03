from __future__ import annotations

import hashlib
import json
import sqlite3
from zipfile import ZipFile

from fastapi.testclient import TestClient

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.db.backup import create_verified_backup
from friendly_hub.main import create_app


def test_verified_backup_preserves_database_and_manifest(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings)) as client:
        response = client.post(
            "/api/v1/league-profiles/samples/entropy",
            headers={"X-Friendly-Hub-Request": "1"},
        )
        assert response.status_code == 201

    source_before = runtime_settings.database_path.read_bytes()
    result = create_verified_backup(runtime_settings)

    assert result is not None
    assert result.path.parent == runtime_settings.data_dir / "backups"
    assert result.retained_count == 1
    assert runtime_settings.database_path.read_bytes() == source_before
    with ZipFile(result.path) as archive:
        assert set(archive.namelist()) == {"hub.sqlite3", "manifest.json"}
        database_bytes = archive.read("hub.sqlite3")
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["format_version"] == 1
    assert manifest["database_filename"] == "hub.sqlite3"
    assert manifest["database_bytes"] == len(database_bytes)
    assert manifest["database_sha256"] == hashlib.sha256(database_bytes).hexdigest()

    extracted = runtime_settings.data_dir / "recovery" / "verified.sqlite3"
    extracted.write_bytes(database_bytes)
    with sqlite3.connect(extracted) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_manual_backup_works_when_automatic_backups_are_disabled(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(
        create_app(runtime_settings),
        headers={"X-Friendly-Hub-Request": "1"},
    ) as client:
        current = client.get("/api/v1/config").json()
        current["backups"]["automatic"] = False
        assert client.put("/api/v1/config", json=current).status_code == 200

    assert create_verified_backup(runtime_settings) is None
    assert create_verified_backup(runtime_settings, force=True) is not None


def test_backup_retention_removes_only_expired_backup_archives(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(
        create_app(runtime_settings),
        headers={"X-Friendly-Hub-Request": "1"},
    ) as client:
        current = client.get("/api/v1/config").json()
        current["backups"]["retention_count"] = 2
        assert client.put("/api/v1/config", json=current).status_code == 200

    unrelated = runtime_settings.data_dir / "backups" / "keep-me.txt"
    unrelated.write_text("not a managed backup", encoding="utf-8")
    for _ in range(3):
        assert create_verified_backup(runtime_settings) is not None

    managed = list((runtime_settings.data_dir / "backups").glob("friendly-hub-backup-v1-*.zip"))
    assert len(managed) == 2
    assert unrelated.read_text(encoding="utf-8") == "not a managed backup"
