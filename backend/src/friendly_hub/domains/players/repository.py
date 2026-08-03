from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.orm import Session

from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.players.models import (
    PlayerExternalIdRow,
    PlayerImportRow,
    PlayerImportSessionRow,
    PlayerMappingDecisionRow,
    PlayerRelevanceRow,
    PlayerRow,
)
from friendly_hub.domains.players.schemas import PlayerCandidate, PlayerRead


def player_to_read(
    session: Session,
    row: PlayerRow,
    *,
    relevant: bool | None = None,
) -> PlayerRead:
    if relevant is None:
        relevant = (
            session.scalar(
                select(func.count())
                .select_from(PlayerRelevanceRow)
                .where(
                    PlayerRelevanceRow.player_id == row.id,
                    PlayerRelevanceRow.active.is_(True),
                )
            )
            or 0
        ) > 0
    return PlayerRead(
        id=row.id,
        display_name=row.display_name,
        first_name=row.first_name,
        last_name=row.last_name,
        suffix=row.suffix,
        team=row.team,
        primary_position=row.primary_position,
        fantasy_positions=json.loads(row.fantasy_positions_json),
        status=row.status,
        rookie_class=row.rookie_class,
        is_rookie=row.is_rookie,
        relevant=relevant,
        updated_at=row.updated_at,
    )


def list_players(
    session: Session,
    *,
    search: str | None,
    position: str | None,
    status: str | None,
    rookie_class: int | None,
    relevant_only: bool,
    limit: int,
    offset: int,
) -> tuple[list[PlayerRead], int]:
    filters = []
    if search:
        tokens = [token for token in search.split() if token]
        filters.extend(PlayerRow.search_name.like(f"%{token}%") for token in tokens)
    if position:
        filters.append(PlayerRow.primary_position == position)
    if status:
        filters.append(PlayerRow.status == status)
    if rookie_class is not None:
        filters.append(PlayerRow.rookie_class == rookie_class)
    if relevant_only:
        filters.append(
            PlayerRow.id.in_(
                select(PlayerRelevanceRow.player_id).where(
                    PlayerRelevanceRow.active.is_(True)
                )
            )
        )

    count = session.scalar(select(func.count()).select_from(PlayerRow).where(*filters)) or 0
    rows = session.scalars(
        select(PlayerRow)
        .where(*filters)
        .order_by(
            case(
                (PlayerRow.primary_position == "QB", 0),
                (PlayerRow.primary_position == "RB", 1),
                (PlayerRow.primary_position == "WR", 2),
                (PlayerRow.primary_position == "TE", 3),
                (PlayerRow.primary_position == "K", 4),
                (PlayerRow.primary_position == "DEF", 5),
                else_=6,
            ),
            PlayerRow.search_name,
            PlayerRow.id,
        )
        .limit(limit)
        .offset(offset)
    ).all()
    player_ids = [row.id for row in rows]
    relevant_ids = (
        set(
            session.scalars(
                select(PlayerRelevanceRow.player_id).where(
                    PlayerRelevanceRow.player_id.in_(player_ids),
                    PlayerRelevanceRow.active.is_(True),
                )
            )
        )
        if player_ids
        else set()
    )
    return [
        player_to_read(session, row, relevant=row.id in relevant_ids) for row in rows
    ], count


def get_player_row(session: Session, player_id: str) -> PlayerRow | None:
    return session.get(PlayerRow, player_id)


def get_external_mapping(
    session: Session,
    provider: str,
    external_id: str,
) -> PlayerExternalIdRow | None:
    return session.scalar(
        select(PlayerExternalIdRow).where(
            PlayerExternalIdRow.provider == provider,
            PlayerExternalIdRow.external_id == external_id,
        )
    )


def find_name_candidates(
    session: Session,
    search_name: str,
    primary_position: str,
) -> list[PlayerRow]:
    return list(
        session.scalars(
            select(PlayerRow).where(
                PlayerRow.search_name == search_name,
                or_(
                    PlayerRow.primary_position == primary_position,
                    PlayerRow.primary_position == "UNKNOWN",
                    primary_position == "UNKNOWN",
                ),
            )
        )
    )


def candidate_differs(
    row: PlayerRow,
    candidate: PlayerCandidate,
    provided_fields: set[str] | None = None,
) -> bool:
    fields = provided_fields or {
        "name",
        "team",
        "position",
        "fantasy_positions",
        "status",
        "rookie_class",
        "is_rookie",
    }
    comparisons = {
        "name": row.display_name != candidate.display_name,
        "team": row.team != candidate.team,
        "position": row.primary_position != candidate.primary_position,
        "fantasy_positions": (
            json.loads(row.fantasy_positions_json) != candidate.fantasy_positions
        ),
        "status": row.status != candidate.status,
        "rookie_class": row.rookie_class != candidate.rookie_class,
        "is_rookie": row.is_rookie != candidate.is_rookie,
    }
    return any(changed for field, changed in comparisons.items() if field in fields)


def create_player(session: Session, candidate: PlayerCandidate) -> PlayerRow:
    now = utc_now_text()
    row = PlayerRow(
        id=str(uuid4()),
        display_name=candidate.display_name,
        first_name=candidate.first_name,
        last_name=candidate.last_name,
        suffix=candidate.suffix,
        search_name=candidate.search_name,
        team=candidate.team,
        primary_position=candidate.primary_position,
        fantasy_positions_json=json.dumps(candidate.fantasy_positions),
        status=candidate.status,
        rookie_class=candidate.rookie_class,
        is_rookie=candidate.is_rookie,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    return row


def update_player(
    row: PlayerRow,
    candidate: PlayerCandidate,
    provided_fields: set[str] | None = None,
) -> None:
    fields = provided_fields or {
        "name",
        "team",
        "position",
        "fantasy_positions",
        "status",
        "rookie_class",
        "is_rookie",
    }
    if "name" in fields:
        row.display_name = candidate.display_name
        row.first_name = candidate.first_name
        row.last_name = candidate.last_name
        row.suffix = candidate.suffix
        row.search_name = candidate.search_name
    if "team" in fields:
        row.team = candidate.team
    if "position" in fields:
        row.primary_position = candidate.primary_position
    if "fantasy_positions" in fields:
        row.fantasy_positions_json = json.dumps(candidate.fantasy_positions)
    if "status" in fields:
        row.status = candidate.status
    if "rookie_class" in fields:
        row.rookie_class = candidate.rookie_class
    if "is_rookie" in fields:
        row.is_rookie = candidate.is_rookie
    row.updated_at = utc_now_text()


def ensure_external_mapping(
    session: Session,
    player_id: str,
    provider: str | None,
    external_id: str | None,
    *,
    manual: bool,
) -> None:
    if not provider or not external_id:
        return
    now = utc_now_text()
    mapping = get_external_mapping(session, provider, external_id)
    if mapping is None:
        session.add(
            PlayerExternalIdRow(
                id=str(uuid4()),
                player_id=player_id,
                provider=provider,
                external_id=external_id,
                is_manual_override=manual,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        return
    mapping.player_id = player_id
    mapping.is_manual_override = mapping.is_manual_override or manual
    mapping.last_seen_at = now


def ensure_relevance(
    session: Session,
    player_id: str,
    reason: str,
    reference_id: str | None = None,
) -> None:
    row = session.scalar(
        select(PlayerRelevanceRow).where(
            PlayerRelevanceRow.player_id == player_id,
            PlayerRelevanceRow.reason == reason,
            PlayerRelevanceRow.reference_id == reference_id,
        )
    )
    now = utc_now_text()
    if row is None:
        session.add(
            PlayerRelevanceRow(
                id=str(uuid4()),
                player_id=player_id,
                reason=reason,
                reference_id=reference_id,
                active=True,
                created_at=now,
                updated_at=now,
            )
        )
    else:
        row.active = True
        row.updated_at = now


def create_import_session(
    session: Session,
    *,
    source: str,
    filename: str | None,
    content_hash: str,
) -> PlayerImportSessionRow:
    row = PlayerImportSessionRow(
        id=str(uuid4()),
        source=source,
        status="preview",
        filename=filename,
        content_hash=content_hash,
        new_count=0,
        matched_count=0,
        changed_count=0,
        ambiguous_count=0,
        invalid_count=0,
        ignored_count=0,
        created_at=utc_now_text(),
        committed_at=None,
    )
    session.add(row)
    session.flush()
    return row


def add_import_row(
    session: Session,
    *,
    import_session_id: str,
    row_number: int,
    source_payload: dict[str, object],
    candidate: PlayerCandidate | None,
    outcome: str,
    proposed_player_id: str | None,
    candidate_player_ids: list[str],
    reason_code: str,
    explanation: str,
) -> PlayerImportRow:
    row = PlayerImportRow(
        id=str(uuid4()),
        session_id=import_session_id,
        row_number=row_number,
        source_payload_json=json.dumps(source_payload, sort_keys=True),
        normalized_candidate_json=candidate.model_dump_json() if candidate else None,
        outcome=outcome,
        proposed_player_id=proposed_player_id,
        resolved_player_id=proposed_player_id if outcome in {"matched", "changed"} else None,
        candidate_player_ids_json=json.dumps(candidate_player_ids),
        reason_code=reason_code,
        explanation=explanation,
    )
    session.add(row)
    return row


def refresh_session_counts(session: Session, import_session: PlayerImportSessionRow) -> None:
    counts = dict(
        session.execute(
            select(PlayerImportRow.outcome, func.count())
            .where(PlayerImportRow.session_id == import_session.id)
            .group_by(PlayerImportRow.outcome)
        ).all()
    )
    for outcome in ("new", "matched", "changed", "ambiguous", "invalid", "ignored"):
        setattr(import_session, f"{outcome}_count", counts.get(outcome, 0))


def get_import_session(
    session: Session,
    import_session_id: str,
) -> PlayerImportSessionRow | None:
    return session.get(PlayerImportSessionRow, import_session_id)


def list_import_rows(session: Session, import_session_id: str) -> list[PlayerImportRow]:
    return list(
        session.scalars(
            select(PlayerImportRow)
            .where(PlayerImportRow.session_id == import_session_id)
            .order_by(PlayerImportRow.row_number)
        )
    )


def get_import_row(
    session: Session,
    import_session_id: str,
    row_id: str,
) -> PlayerImportRow | None:
    return session.scalar(
        select(PlayerImportRow).where(
            PlayerImportRow.id == row_id,
            PlayerImportRow.session_id == import_session_id,
        )
    )


def save_decision(
    session: Session,
    row: PlayerImportRow,
    *,
    decision: str,
    player_id: str | None,
    note: str | None,
) -> None:
    existing = session.scalar(
        select(PlayerMappingDecisionRow).where(
            PlayerMappingDecisionRow.import_row_id == row.id
        )
    )
    if decision == "clear":
        if existing is not None:
            session.execute(
                delete(PlayerMappingDecisionRow).where(
                    PlayerMappingDecisionRow.id == existing.id
                )
            )
        row.resolved_player_id = None
        candidate_ids = json.loads(row.candidate_player_ids_json)
        if row.normalized_candidate_json is None:
            row.outcome = "invalid"
            row.reason_code = "IMPORT.PLAYER.ROW_INVALID"
            row.explanation = "This source row is invalid and needs review."
        else:
            row.outcome = "ambiguous"
            row.reason_code = "IMPORT.PLAYER.CONFIRM_NAME_MATCH"
            row.explanation = (
                "The suggested identity is unconfirmed and still needs review."
                if candidate_ids
                else "This row still needs a create-new or ignore decision."
            )
        return
    if existing is None:
        existing = PlayerMappingDecisionRow(
            id=str(uuid4()),
            import_row_id=row.id,
            player_id=player_id,
            decision=decision,
            note=note,
            created_at=utc_now_text(),
        )
        session.add(existing)
    else:
        existing.player_id = player_id
        existing.decision = decision
        existing.note = note
        existing.created_at = utc_now_text()

    if decision == "match_existing":
        row.outcome = "matched"
        row.resolved_player_id = player_id
        row.reason_code = "IMPORT.PLAYER.MANUAL_MATCH"
        row.explanation = "You confirmed the canonical player for this source row."
    elif decision == "create_new":
        row.outcome = "new"
        row.resolved_player_id = None
        row.reason_code = "IMPORT.PLAYER.MANUAL_NEW"
        row.explanation = "You confirmed that this row represents a new player."
    else:
        row.outcome = "ignored"
        row.resolved_player_id = None
        row.reason_code = "IMPORT.PLAYER.MANUAL_IGNORE"
        row.explanation = "This row will be skipped when the import is committed."
