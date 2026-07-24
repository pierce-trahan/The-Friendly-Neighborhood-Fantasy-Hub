from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from friendly_hub.core.errors import HubError
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.players.models import PlayerImportRow, PlayerRow
from friendly_hub.domains.players.normalization import (
    normalize_position,
    normalize_search_name,
    normalize_status,
    normalize_team,
    split_name,
)
from friendly_hub.domains.players.repository import (
    add_import_row,
    candidate_differs,
    create_import_session,
    create_player,
    ensure_external_mapping,
    ensure_relevance,
    find_name_candidates,
    get_external_mapping,
    get_import_row,
    get_import_session,
    get_player_row,
    list_import_rows,
    list_players,
    player_to_read,
    refresh_session_counts,
    save_decision,
    update_player,
)
from friendly_hub.domains.players.schemas import (
    MappingDecisionRequest,
    PlayerCandidate,
    PlayerImportCommitResponse,
    PlayerImportRowRead,
    PlayerImportSessionRead,
    PlayerListResponse,
    PlayerPatch,
    PlayerRead,
)


def _hub_error(
    code: str,
    message: str,
    action: str,
    status_code: int,
) -> HubError:
    return HubError(code=code, message=message, action=action, status_code=status_code)


def _parse_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    return str(value).strip().casefold() in {"1", "true", "yes", "y"}


def _candidate_from_source(
    payload: dict[str, object],
    *,
    default_provider: str | None,
) -> PlayerCandidate:
    raw_name = str(payload.get("name") or "").strip()
    raw_position = str(payload.get("position") or "").strip()
    if not raw_name:
        raise ValueError("A player name is required.")
    position = normalize_position(raw_position)
    if not raw_position or position == "UNKNOWN":
        raise ValueError("A supported position is required.")

    first_name, last_name, suffix, display_name = split_name(raw_name)
    raw_positions = payload.get("fantasy_positions")
    if isinstance(raw_positions, list):
        fantasy_positions = [
            normalized
            for item in raw_positions
            if (normalized := normalize_position(str(item))) != "UNKNOWN"
        ]
    else:
        fantasy_positions = [position]
    fantasy_positions = list(dict.fromkeys(fantasy_positions)) or [position]

    rookie_value = payload.get("rookie_class")
    try:
        rookie_class = int(str(rookie_value)) if rookie_value not in (None, "") else None
    except ValueError as exc:
        raise ValueError("Rookie class must be a four-digit year.") from exc
    provider_value = str(payload.get("provider") or default_provider or "").strip().casefold()
    external_id_value = str(payload.get("external_id") or "").strip()

    return PlayerCandidate(
        display_name=display_name,
        first_name=first_name,
        last_name=last_name,
        suffix=suffix,
        search_name=normalize_search_name(display_name),
        team=normalize_team(str(payload.get("team") or "")),
        primary_position=position,
        fantasy_positions=fantasy_positions,
        status=normalize_status(str(payload.get("status") or "unknown")),
        rookie_class=rookie_class,
        is_rookie=_parse_bool(payload.get("is_rookie"), rookie_class is not None),
        provider=provider_value or None,
        external_id=external_id_value or None,
        include=_parse_bool(payload.get("include"), True),
    )


def _evaluate_candidate(
    session: Session,
    candidate: PlayerCandidate,
    provided_fields: set[str],
) -> tuple[str, str | None, list[str], str, str]:
    if candidate.provider and candidate.external_id:
        mapping = get_external_mapping(session, candidate.provider, candidate.external_id)
        if mapping is not None:
            existing = get_player_row(session, mapping.player_id)
            if existing is None:
                return (
                    "invalid",
                    None,
                    [],
                    "IMPORT.PLAYER.MAPPING_ORPHANED",
                    "A saved source mapping is damaged and must be repaired before import.",
                )
            outcome = (
                "changed"
                if candidate_differs(existing, candidate, provided_fields)
                else "matched"
            )
            explanation = (
                "The source ID matches an existing player and some fields changed."
                if outcome == "changed"
                else "The source ID matches an existing canonical player."
            )
            return (
                outcome,
                existing.id,
                [existing.id],
                f"IMPORT.PLAYER.{outcome.upper()}",
                explanation,
            )

    candidates = find_name_candidates(
        session,
        candidate.search_name,
        candidate.primary_position,
    )
    if candidates:
        return (
            "ambiguous",
            candidates[0].id if len(candidates) == 1 else None,
            [row.id for row in candidates],
            "IMPORT.PLAYER.CONFIRM_NAME_MATCH",
            "The name and position suggest a match, but identity must be confirmed.",
        )
    return (
        "new",
        None,
        [],
        "IMPORT.PLAYER.NEW",
        "No canonical player matches this valid source row.",
    )


def _create_preview(
    session: Session,
    *,
    source: str,
    filename: str | None,
    payloads: list[dict[str, object]],
    content: bytes,
) -> PlayerImportSessionRead:
    import_session = create_import_session(
        session,
        source=source,
        filename=filename,
        content_hash=hashlib.sha256(content).hexdigest(),
    )
    seen_external_ids: set[tuple[str, str]] = set()
    seen_name_positions: set[tuple[str, str]] = set()
    for row_number, payload in enumerate(payloads, start=1):
        try:
            candidate = _candidate_from_source(payload, default_provider=source)
            if not candidate.include:
                add_import_row(
                    session,
                    import_session_id=import_session.id,
                    row_number=row_number,
                    source_payload=payload,
                    candidate=candidate,
                    outcome="ignored",
                    proposed_player_id=None,
                    candidate_player_ids=[],
                    reason_code="IMPORT.PLAYER.EXCLUDED",
                    explanation="The source row is marked for exclusion.",
                )
                continue
            external_key = (
                (candidate.provider, candidate.external_id)
                if candidate.provider and candidate.external_id
                else None
            )
            if external_key and external_key in seen_external_ids:
                add_import_row(
                    session,
                    import_session_id=import_session.id,
                    row_number=row_number,
                    source_payload=payload,
                    candidate=candidate,
                    outcome="invalid",
                    proposed_player_id=None,
                    candidate_player_ids=[],
                    reason_code="IMPORT.PLAYER.DUPLICATE_EXTERNAL_ID",
                    explanation="This source ID appears more than once in the import.",
                )
                continue
            if external_key:
                seen_external_ids.add(external_key)

            name_position_key = (candidate.search_name, candidate.primary_position)
            if name_position_key in seen_name_positions:
                add_import_row(
                    session,
                    import_session_id=import_session.id,
                    row_number=row_number,
                    source_payload=payload,
                    candidate=candidate,
                    outcome="ambiguous",
                    proposed_player_id=None,
                    candidate_player_ids=[],
                    reason_code="IMPORT.PLAYER.DUPLICATE_NAME_POSITION",
                    explanation=(
                        "Another row in this import has the same normalized name and position."
                    ),
                )
                continue
            seen_name_positions.add(name_position_key)
            provided_fields = {str(key).strip().casefold() for key in payload}
            outcome, proposed_id, candidate_ids, reason_code, explanation = (
                _evaluate_candidate(session, candidate, provided_fields)
            )
            add_import_row(
                session,
                import_session_id=import_session.id,
                row_number=row_number,
                source_payload=payload,
                candidate=candidate,
                outcome=outcome,
                proposed_player_id=proposed_id,
                candidate_player_ids=candidate_ids,
                reason_code=reason_code,
                explanation=explanation,
            )
        except (TypeError, ValueError, ValidationError) as exc:
            add_import_row(
                session,
                import_session_id=import_session.id,
                row_number=row_number,
                source_payload=payload,
                candidate=None,
                outcome="invalid",
                proposed_player_id=None,
                candidate_player_ids=[],
                reason_code="IMPORT.PLAYER.ROW_INVALID",
                explanation=str(exc)[:500],
            )
    refresh_session_counts(session, import_session)
    session.commit()
    return read_import_session(session, import_session.id)


def preview_sanitized_fixture(session: Session, fixture_path: Path) -> PlayerImportSessionRead:
    if not fixture_path.is_file():
        raise _hub_error(
            "IMPORT.PLAYER.FIXTURE_NOT_FOUND",
            "The offline player sample could not be found.",
            "Reinstall the application files and try again.",
            500,
        )
    content = fixture_path.read_bytes()
    try:
        document = json.loads(content)
    except json.JSONDecodeError as exc:
        raise _hub_error(
            "IMPORT.PLAYER.FIXTURE_INVALID",
            "The offline player sample is not valid.",
            "The sample was not imported. Reinstall the application files.",
            500,
        ) from exc
    if (
        not isinstance(document, dict)
        or document.get("sanitized") is not True
        or not isinstance(document.get("players"), list)
    ):
        raise _hub_error(
            "IMPORT.PLAYER.FIXTURE_NOT_SANITIZED",
            "The player sample is not marked as safe demonstration data.",
            "Use only a deliberately sanitized player fixture.",
            422,
        )
    if not all(isinstance(row, dict) for row in document["players"]):
        raise _hub_error(
            "IMPORT.PLAYER.FIXTURE_INVALID",
            "The offline player sample contains an invalid row.",
            "Reinstall the application files and try again.",
            500,
        )
    payloads = list(document["players"])
    return _create_preview(
        session,
        source="sanitized_fixture",
        filename=fixture_path.name,
        payloads=payloads,
        content=content,
    )


def preview_csv(
    session: Session,
    *,
    filename: str,
    csv_text: str,
) -> PlayerImportSessionRead:
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        headers = {header.strip().casefold() for header in (reader.fieldnames or [])}
        if not {"name", "position"}.issubset(headers):
            raise ValueError("CSV headers must include name and position.")
        payloads = [
            {str(key).strip().casefold(): value for key, value in row.items() if key is not None}
            for row in reader
        ]
    except (csv.Error, ValueError) as exc:
        raise _hub_error(
            "IMPORT.PLAYER.CSV_INVALID",
            "The CSV could not be previewed.",
            str(exc),
            422,
        ) from exc
    return _create_preview(
        session,
        source="csv",
        filename=Path(filename).name,
        payloads=payloads,
        content=csv_text.encode("utf-8"),
    )


def _row_to_read(session: Session, row: PlayerImportRow) -> PlayerImportRowRead:
    candidate = (
        PlayerCandidate.model_validate_json(row.normalized_candidate_json)
        if row.normalized_candidate_json
        else None
    )
    candidate_players = []
    for player_id in json.loads(row.candidate_player_ids_json):
        player = get_player_row(session, player_id)
        if player is not None:
            candidate_players.append(player_to_read(session, player))
    source_name = None
    try:
        source_name = str(json.loads(row.source_payload_json).get("name") or "") or None
    except json.JSONDecodeError:
        pass
    return PlayerImportRowRead(
        id=row.id,
        row_number=row.row_number,
        source_name=source_name,
        candidate=candidate,
        outcome=row.outcome,
        proposed_player_id=row.proposed_player_id,
        resolved_player_id=row.resolved_player_id,
        candidate_players=candidate_players,
        reason_code=row.reason_code,
        explanation=row.explanation,
    )


def read_import_session(
    session: Session,
    import_session_id: str,
) -> PlayerImportSessionRead:
    row = get_import_session(session, import_session_id)
    if row is None:
        raise _hub_error(
            "IMPORT.PLAYER.SESSION_NOT_FOUND",
            "That player import preview no longer exists.",
            "Start a new import preview.",
            404,
        )
    return PlayerImportSessionRead(
        id=row.id,
        source=row.source,
        status=row.status,
        filename=row.filename,
        new_count=row.new_count,
        matched_count=row.matched_count,
        changed_count=row.changed_count,
        ambiguous_count=row.ambiguous_count,
        invalid_count=row.invalid_count,
        ignored_count=row.ignored_count,
        created_at=row.created_at,
        committed_at=row.committed_at,
        rows=[_row_to_read(session, item) for item in list_import_rows(session, row.id)],
    )


def decide_import_row(
    session: Session,
    import_session_id: str,
    row_id: str,
    request: MappingDecisionRequest,
) -> PlayerImportSessionRead:
    import_session = get_import_session(session, import_session_id)
    row = get_import_row(session, import_session_id, row_id)
    if import_session is None or row is None:
        raise _hub_error(
            "IMPORT.PLAYER.ROW_NOT_FOUND",
            "That import row could not be found.",
            "Reload the import preview and try again.",
            404,
        )
    if import_session.status != "preview":
        raise _hub_error(
            "IMPORT.PLAYER.SESSION_CLOSED",
            "That import preview is already closed.",
            "Start a new preview to make different mapping decisions.",
            409,
        )
    if row.normalized_candidate_json is None and request.decision != "ignore":
        raise _hub_error(
            "IMPORT.PLAYER.INVALID_ROW_CANNOT_MATCH",
            "That invalid row cannot create or match a player.",
            "Ignore the row or correct the source file and start a new preview.",
            422,
        )
    if request.decision == "match_existing":
        selected = get_player_row(session, request.player_id or "")
        if selected is None:
            raise _hub_error(
                "IMPORT.PLAYER.MATCH_NOT_FOUND",
                "The selected canonical player could not be found.",
                "Choose another player and try again.",
                404,
            )
        candidate = (
            PlayerCandidate.model_validate_json(row.normalized_candidate_json)
            if row.normalized_candidate_json
            else None
        )
        if candidate and candidate.provider and candidate.external_id:
            existing = get_external_mapping(
                session,
                candidate.provider,
                candidate.external_id,
            )
            if existing is not None and existing.player_id != selected.id:
                raise _hub_error(
                    "IMPORT.PLAYER.EXTERNAL_ID_CONFLICT",
                    "That source ID is already assigned to another player.",
                    "Keep the existing mapping or review the source data.",
                    409,
                )

    save_decision(
        session,
        row,
        decision=request.decision,
        player_id=request.player_id,
        note=request.note,
    )
    refresh_session_counts(session, import_session)
    session.commit()
    return read_import_session(session, import_session.id)


def commit_import(
    session: Session,
    import_session_id: str,
) -> PlayerImportCommitResponse:
    import_session = get_import_session(session, import_session_id)
    if import_session is None:
        raise _hub_error(
            "IMPORT.PLAYER.SESSION_NOT_FOUND",
            "That player import preview no longer exists.",
            "Start a new import preview.",
            404,
        )
    if import_session.status == "committed":
        return PlayerImportCommitResponse(
            session=read_import_session(session, import_session.id),
            created_players=0,
            updated_players=0,
            ignored_rows=import_session.ignored_count,
        )
    if import_session.status != "preview":
        raise _hub_error(
            "IMPORT.PLAYER.SESSION_CLOSED",
            "That import preview is already closed.",
            "Start a new preview.",
            409,
        )

    rows = list_import_rows(session, import_session.id)
    unresolved = [row for row in rows if row.outcome in {"ambiguous", "invalid"}]
    if unresolved:
        raise _hub_error(
            "IMPORT.PLAYER.REVIEW_REQUIRED",
            "Some player rows still need review.",
            "Resolve or ignore every ambiguous and invalid row before committing.",
            409,
        )

    created = 0
    updated = 0
    try:
        for row in rows:
            if row.outcome == "ignored":
                continue
            if not row.normalized_candidate_json:
                raise RuntimeError("A commit-ready row has no normalized candidate.")
            candidate = PlayerCandidate.model_validate_json(row.normalized_candidate_json)
            source_payload = json.loads(row.source_payload_json)
            provided_fields = {str(key).strip().casefold() for key in source_payload}
            player: PlayerRow | None = None
            if row.resolved_player_id:
                player = get_player_row(session, row.resolved_player_id)
            if player is None:
                player = create_player(session, candidate)
                row.resolved_player_id = player.id
                created += 1
            elif candidate_differs(player, candidate, provided_fields):
                update_player(player, candidate, provided_fields)
                updated += 1
            ensure_external_mapping(
                session,
                player.id,
                candidate.provider,
                candidate.external_id,
                manual=row.reason_code == "IMPORT.PLAYER.MANUAL_MATCH",
            )
            relevance_reason = (
                "sanitized_fixture" if import_session.source == "sanitized_fixture" else "manual"
            )
            ensure_relevance(session, player.id, relevance_reason)
        import_session.status = "committed"
        import_session.committed_at = utc_now_text()
        session.commit()
    except Exception:
        session.rollback()
        raise

    return PlayerImportCommitResponse(
        session=read_import_session(session, import_session.id),
        created_players=created,
        updated_players=updated,
        ignored_rows=import_session.ignored_count,
    )


def cancel_import(session: Session, import_session_id: str) -> PlayerImportSessionRead:
    import_session = get_import_session(session, import_session_id)
    if import_session is None:
        raise _hub_error(
            "IMPORT.PLAYER.SESSION_NOT_FOUND",
            "That player import preview no longer exists.",
            "Start a new import preview.",
            404,
        )
    if import_session.status == "preview":
        import_session.status = "cancelled"
        session.commit()
    return read_import_session(session, import_session.id)


def query_players(
    session: Session,
    *,
    search: str | None,
    position: str | None,
    status: str | None,
    rookie_class: int | None,
    relevant_only: bool,
    limit: int,
    offset: int,
) -> PlayerListResponse:
    normalized_search = normalize_search_name(search) if search else None
    items, total = list_players(
        session,
        search=normalized_search,
        position=position,
        status=status,
        rookie_class=rookie_class,
        relevant_only=relevant_only,
        limit=limit,
        offset=offset,
    )
    return PlayerListResponse(items=items, total=total, limit=limit, offset=offset)


def read_player(session: Session, player_id: str) -> PlayerRead:
    row = get_player_row(session, player_id)
    if row is None:
        raise _hub_error(
            "PLAYER.NOT_FOUND",
            "That player could not be found.",
            "Reload the player universe and try again.",
            404,
        )
    return player_to_read(session, row)


def patch_player(
    session: Session,
    player_id: str,
    patch: PlayerPatch,
) -> PlayerRead:
    row = get_player_row(session, player_id)
    if row is None:
        raise _hub_error(
            "PLAYER.NOT_FOUND",
            "That player could not be found.",
            "Reload the player universe and try again.",
            404,
        )
    values = patch.model_dump(exclude_unset=True)
    if "display_name" in values:
        first_name, last_name, suffix, display_name = split_name(values["display_name"])
        row.display_name = display_name
        row.first_name = first_name
        row.last_name = last_name
        row.suffix = suffix
        row.search_name = normalize_search_name(display_name)
    if "team" in values:
        row.team = normalize_team(values["team"])
    for field in ("primary_position", "status", "rookie_class", "is_rookie"):
        if field in values:
            setattr(row, field, values[field])
    if "fantasy_positions" in values:
        row.fantasy_positions_json = json.dumps(values["fantasy_positions"])
    row.updated_at = utc_now_text()
    session.commit()
    return player_to_read(session, row)


def export_players_csv(session: Session) -> str:
    items, _ = list_players(
        session,
        search=None,
        position=None,
        status=None,
        rookie_class=None,
        relevant_only=False,
        limit=100_000,
        offset=0,
    )
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "canonical_id",
            "name",
            "position",
            "fantasy_positions",
            "team",
            "status",
            "rookie_class",
            "is_rookie",
            "relevant",
        ]
    )
    for player in items:
        writer.writerow(
            [
                player.id,
                player.display_name,
                player.primary_position,
                "|".join(player.fantasy_positions),
                player.team or "",
                player.status,
                player.rookie_class or "",
                str(player.is_rookie).lower(),
                str(player.relevant).lower(),
            ]
        )
    return output.getvalue()
