from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from friendly_hub.core.settings import RuntimeSettings

BACKUP_PREFIX = "friendly-hub-backup-v1-"
DEFAULT_RETENTION = 10


@dataclass(frozen=True)
class BackupResult:
    path: Path
    retained_count: int


def _backup_policy(database_path: Path) -> tuple[bool, int]:
    """Read the persisted policy without requiring application migrations."""
    try:
        with closing(sqlite3.connect(database_path)) as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                ("app_configuration",),
            ).fetchone()
            if exists is None:
                return True, DEFAULT_RETENTION
            row = connection.execute(
                "SELECT payload_json FROM app_configuration WHERE id = 1"
            ).fetchone()
    except sqlite3.Error as error:
        raise RuntimeError(
            "The local database could not be opened for its pre-launch safety backup. "
            "The original file was not changed."
        ) from error

    if row is None:
        return True, DEFAULT_RETENTION
    try:
        backup_settings = json.loads(row[0])["backups"]
        automatic = bool(backup_settings["automatic"])
        retention = int(backup_settings["retention_count"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return True, DEFAULT_RETENTION
    return automatic, min(max(retention, 1), 50)


def _available_backup_path(backup_dir: Path, created_at: datetime) -> Path:
    timestamp = created_at.strftime("%Y%m%d-%H%M%S")
    candidate = backup_dir / f"{BACKUP_PREFIX}{timestamp}.zip"
    suffix = 1
    while candidate.exists():
        candidate = backup_dir / f"{BACKUP_PREFIX}{timestamp}-{suffix:02d}.zip"
        suffix += 1
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prune_backups(backup_dir: Path, retention: int) -> int:
    backups = sorted(
        backup_dir.glob(f"{BACKUP_PREFIX}*.zip"),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    for expired in backups[retention:]:
        expired.unlink()
    return min(len(backups), retention)


def create_verified_backup(
    settings: RuntimeSettings,
    *,
    force: bool = False,
) -> BackupResult | None:
    """Create and verify a private, atomic SQLite backup archive."""
    database_path = settings.database_path
    if not database_path.is_file():
        return None

    automatic, retention = _backup_policy(database_path)
    if not force and not automatic:
        return None

    backup_dir = settings.data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(UTC)
    final_path = _available_backup_path(backup_dir, created_at)
    temporary_database = backup_dir / f".{final_path.stem}.sqlite3.tmp"
    temporary_archive = backup_dir / f".{final_path.name}.tmp"

    try:
        with (
            closing(sqlite3.connect(database_path)) as source,
            closing(sqlite3.connect(temporary_database)) as destination,
        ):
            source.backup(destination)
            integrity = destination.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise RuntimeError("The copied database did not pass SQLite integrity checks.")

        manifest = {
            "format_version": 1,
            "created_at": created_at.isoformat().replace("+00:00", "Z"),
            "database_filename": "hub.sqlite3",
            "database_bytes": temporary_database.stat().st_size,
            "database_sha256": _sha256(temporary_database),
        }
        with ZipFile(temporary_archive, "w", compression=ZIP_DEFLATED) as archive:
            archive.write(temporary_database, "hub.sqlite3")
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            )
        with ZipFile(temporary_archive) as archive:
            if set(archive.namelist()) != {"hub.sqlite3", "manifest.json"}:
                raise RuntimeError("The backup archive did not contain the expected files.")
            archived_manifest = json.loads(archive.read("manifest.json"))
            if archived_manifest != manifest:
                raise RuntimeError("The backup manifest could not be verified.")
        os.replace(temporary_archive, final_path)
    except (OSError, sqlite3.Error) as error:
        raise RuntimeError(
            "The pre-launch safety backup failed. The original database was not changed."
        ) from error
    finally:
        temporary_database.unlink(missing_ok=True)
        temporary_archive.unlink(missing_ok=True)

    retained_count = _prune_backups(backup_dir, retention)
    return BackupResult(path=final_path, retained_count=retained_count)


def main() -> None:
    result = create_verified_backup(RuntimeSettings.from_environment(), force=True)
    if result is None:
        print("No local database exists yet; there is nothing to back up.")
        return
    print(f"Verified backup created: {result.path}")
    print(f"Backups retained: {result.retained_count}")


if __name__ == "__main__":
    main()
