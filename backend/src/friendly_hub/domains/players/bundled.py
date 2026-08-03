from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.players.models import PlayerImportSessionRow
from friendly_hub.domains.players.repository import (
    create_import_session,
    create_player,
    ensure_external_mapping,
    ensure_relevance,
    find_name_candidates,
    get_external_mapping,
    get_player_row,
)
from friendly_hub.domains.players.schemas import PlayerCandidate
from friendly_hub.domains.players.service import candidate_from_source

SNAPSHOT_SOURCE = "nflverse_snapshot"
RELEVANCE_REASON = "nflverse_snapshot"


@dataclass(frozen=True)
class BundledSeedResult:
    snapshot_count: int
    created_count: int
    matched_count: int
    skipped_count: int
    already_seeded: bool


def _load_candidates(path: Path) -> tuple[bytes, list[PlayerCandidate]]:
    if not path.is_file():
        raise RuntimeError(
            "The bundled NFL player database is missing. Reinstall the application files."
        )
    content = path.read_bytes()
    try:
        document = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The bundled NFL player database is not valid JSON.") from exc
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise RuntimeError("The bundled NFL player database schema is not supported.")
    source = document.get("source")
    snapshot = document.get("snapshot")
    players = document.get("players")
    if (
        not isinstance(source, dict)
        or source.get("name") != "nflverse"
        or source.get("license") != "CC BY 4.0"
        or not isinstance(snapshot, dict)
        or not isinstance(players, list)
        or snapshot.get("player_count") != len(players)
    ):
        raise RuntimeError("The bundled NFL player database provenance or row count is invalid.")

    candidates: list[PlayerCandidate] = []
    seen_external_ids: set[str] = set()
    for row in players:
        if not isinstance(row, dict):
            raise RuntimeError("The bundled NFL player database contains an invalid row.")
        try:
            candidate = candidate_from_source(row, default_provider="nflverse")
        except (TypeError, ValueError, ValidationError) as exc:
            raise RuntimeError(
                f"The bundled NFL player database contains an invalid row: {exc}"
            ) from exc
        if (
            candidate.provider != "nflverse"
            or not candidate.external_id
            or not candidate.include
        ):
            raise RuntimeError("Every bundled player must have one nflverse external ID.")
        if candidate.external_id in seen_external_ids:
            raise RuntimeError(
                f"The bundled NFL player database repeats ID {candidate.external_id}."
            )
        seen_external_ids.add(candidate.external_id)
        candidates.append(candidate)
    return content, candidates


def seed_bundled_player_universe(
    session: Session,
    snapshot_path: Path | None,
) -> BundledSeedResult | None:
    if snapshot_path is None:
        return None

    content, candidates = _load_candidates(snapshot_path)
    content_hash = hashlib.sha256(content).hexdigest()
    existing_import = session.scalar(
        select(PlayerImportSessionRow).where(
            PlayerImportSessionRow.source == SNAPSHOT_SOURCE,
            PlayerImportSessionRow.content_hash == content_hash,
            PlayerImportSessionRow.status == "committed",
        )
    )
    if existing_import is not None:
        return BundledSeedResult(
            snapshot_count=len(candidates),
            created_count=0,
            matched_count=existing_import.matched_count,
            skipped_count=existing_import.ignored_count,
            already_seeded=True,
        )

    created_count = 0
    matched_count = 0
    skipped_count = 0
    try:
        for candidate in candidates:
            mapping = get_external_mapping(
                session,
                candidate.provider or "",
                candidate.external_id or "",
            )
            if mapping is not None:
                player = get_player_row(session, mapping.player_id)
                if player is None:
                    raise RuntimeError("A saved nflverse player mapping is damaged.")
                ensure_relevance(session, player.id, RELEVANCE_REASON)
                matched_count += 1
                continue

            if find_name_candidates(
                session,
                candidate.search_name,
                candidate.primary_position,
            ):
                skipped_count += 1
                continue

            player = create_player(session, candidate)
            ensure_external_mapping(
                session,
                player.id,
                candidate.provider,
                candidate.external_id,
                manual=False,
            )
            ensure_relevance(session, player.id, RELEVANCE_REASON)
            created_count += 1

        import_session = create_import_session(
            session,
            source=SNAPSHOT_SOURCE,
            filename=snapshot_path.name,
            content_hash=content_hash,
        )
        import_session.status = "committed"
        import_session.new_count = created_count
        import_session.matched_count = matched_count
        import_session.ignored_count = skipped_count
        import_session.committed_at = utc_now_text()
        session.commit()
    except Exception:
        session.rollback()
        raise

    return BundledSeedResult(
        snapshot_count=len(candidates),
        created_count=created_count,
        matched_count=matched_count,
        skipped_count=skipped_count,
        already_seeded=False,
    )
