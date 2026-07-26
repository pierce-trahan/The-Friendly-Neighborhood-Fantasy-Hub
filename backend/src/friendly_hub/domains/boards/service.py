from __future__ import annotations

import csv
import io

from sqlalchemy.orm import Session

from friendly_hub.core.errors import HubError
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.boards.models import PersonalBoardRow
from friendly_hub.domains.boards.repository import (
    apply_entry_order,
    archive_entry,
    board_to_read,
    board_to_summary,
    create_board_row,
    create_or_restore_entry,
    create_tier_row,
    delete_tier_row,
    get_board_row,
    get_entry_for_player,
    get_entry_row,
    get_tier_row,
    list_active_entry_rows,
    list_board_rows,
    list_tier_rows,
    move_tier,
    touch_board,
)
from friendly_hub.domains.boards.schemas import (
    BoardCreate,
    BoardEntryCreate,
    BoardEntryPatch,
    BoardListResponse,
    BoardOrderUpdate,
    BoardPatch,
    BoardRead,
    BoardTierCreate,
    BoardTierPatch,
)
from friendly_hub.domains.leagues.models import LeagueProfileRow
from friendly_hub.domains.players.repository import ensure_relevance, get_player_row


def _hub_error(
    code: str,
    message: str,
    action: str,
    status_code: int,
) -> HubError:
    return HubError(
        code=code,
        message=message,
        action=action,
        status_code=status_code,
    )


def _require_board(session: Session, board_id: str) -> PersonalBoardRow:
    board = get_board_row(session, board_id)
    if board is None:
        raise _hub_error(
            "BOARD.NOT_FOUND",
            "That personal board could not be found.",
            "Return to the board list and choose an available board.",
            404,
        )
    return board


def _require_mutable_board(session: Session, board_id: str) -> PersonalBoardRow:
    board = _require_board(session, board_id)
    if board.archived:
        raise _hub_error(
            "BOARD.ARCHIVED",
            "That personal board is archived.",
            "Restore the board before changing its tiers or players.",
            409,
        )
    return board


def _validate_league_profile(session: Session, league_profile_id: str | None) -> None:
    if league_profile_id is None:
        return
    if session.get(LeagueProfileRow, league_profile_id) is None:
        raise _hub_error(
            "BOARD.LEAGUE_NOT_FOUND",
            "The selected league profile is unavailable.",
            "Choose a league profile that is stored in this Hub.",
            404,
        )


def _required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if normalized:
        return normalized
    raise _hub_error(
        "BOARD.INVALID_TEXT",
        f"{field_name} cannot be blank.",
        f"Enter a {field_name.casefold()} and try again.",
        422,
    )


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _commit(session: Session) -> None:
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise


def list_boards(
    session: Session,
    *,
    include_archived: bool,
) -> BoardListResponse:
    return BoardListResponse(
        items=[
            board_to_summary(session, row)
            for row in list_board_rows(
                session,
                include_archived=include_archived,
            )
        ]
    )


def create_board(session: Session, payload: BoardCreate) -> BoardRead:
    _validate_league_profile(session, payload.league_profile_id)
    row = create_board_row(
        session,
        name=_required_text(payload.name, field_name="Board name"),
        description=_optional_text(payload.description),
        league_profile_id=payload.league_profile_id,
        scope=payload.scope,
    )
    _commit(session)
    return board_to_read(session, row)


def read_board(session: Session, board_id: str) -> BoardRead:
    return board_to_read(session, _require_board(session, board_id))


def patch_board(
    session: Session,
    board_id: str,
    payload: BoardPatch,
) -> BoardRead:
    board = _require_board(session, board_id)
    fields = payload.model_fields_set
    if "name" in fields:
        if payload.name is None:
            raise _hub_error(
                "BOARD.INVALID_TEXT",
                "Board name cannot be removed.",
                "Enter a board name and try again.",
                422,
            )
        board.name = _required_text(payload.name, field_name="Board name")
    if "description" in fields:
        board.description = _optional_text(payload.description)
    if "league_profile_id" in fields:
        _validate_league_profile(session, payload.league_profile_id)
        board.league_profile_id = payload.league_profile_id
    if payload.scope is not None:
        board.scope = payload.scope
    if payload.archived is not None:
        board.archived = payload.archived
    touch_board(board)
    _commit(session)
    return board_to_read(session, board)


def _ensure_unique_tier_name(
    session: Session,
    board_id: str,
    name: str,
    *,
    excluding_tier_id: str | None = None,
) -> None:
    normalized = name.casefold()
    if any(
        tier.name.casefold() == normalized and tier.id != excluding_tier_id
        for tier in list_tier_rows(session, board_id)
    ):
        raise _hub_error(
            "BOARD.TIER_DUPLICATE",
            "That tier name is already used on this board.",
            "Choose a distinct tier name.",
            409,
        )


def add_tier(
    session: Session,
    board_id: str,
    payload: BoardTierCreate,
) -> BoardRead:
    board = _require_mutable_board(session, board_id)
    name = _required_text(payload.name, field_name="Tier name")
    _ensure_unique_tier_name(session, board.id, name)
    create_tier_row(
        session,
        board,
        name=name,
        color=_optional_text(payload.color),
        tier_order=payload.tier_order,
    )
    _commit(session)
    return board_to_read(session, board)


def patch_tier(
    session: Session,
    board_id: str,
    tier_id: str,
    payload: BoardTierPatch,
) -> BoardRead:
    board = _require_mutable_board(session, board_id)
    tier = get_tier_row(session, board.id, tier_id)
    if tier is None:
        raise _hub_error(
            "BOARD.TIER_NOT_FOUND",
            "That tier could not be found on this board.",
            "Refresh the board and choose an available tier.",
            404,
        )
    fields = payload.model_fields_set
    if "name" in fields:
        if payload.name is None:
            raise _hub_error(
                "BOARD.INVALID_TEXT",
                "Tier name cannot be removed.",
                "Enter a tier name and try again.",
                422,
            )
        name = _required_text(payload.name, field_name="Tier name")
        _ensure_unique_tier_name(
            session,
            board.id,
            name,
            excluding_tier_id=tier.id,
        )
        tier.name = name
    if "color" in fields:
        tier.color = _optional_text(payload.color)
    if payload.tier_order is not None:
        move_tier(session, board.id, tier, payload.tier_order)
    tier.updated_at = utc_now_text()
    touch_board(board)
    _commit(session)
    return board_to_read(session, board)


def remove_tier(
    session: Session,
    board_id: str,
    tier_id: str,
) -> BoardRead:
    board = _require_mutable_board(session, board_id)
    tier = get_tier_row(session, board.id, tier_id)
    if tier is None:
        raise _hub_error(
            "BOARD.TIER_NOT_FOUND",
            "That tier could not be found on this board.",
            "Refresh the board and choose an available tier.",
            404,
        )
    delete_tier_row(session, board, tier)
    _commit(session)
    return board_to_read(session, board)


def add_board_entry(
    session: Session,
    board_id: str,
    payload: BoardEntryCreate,
) -> BoardRead:
    board = _require_mutable_board(session, board_id)
    if get_player_row(session, payload.player_id) is None:
        raise _hub_error(
            "BOARD.PLAYER_NOT_FOUND",
            "That canonical player could not be found.",
            "Refresh the player universe before adding the player.",
            404,
        )
    existing = get_entry_for_player(session, board.id, payload.player_id)
    if (
        (existing is None or not existing.active)
        and len(list_active_entry_rows(session, board.id)) >= 500
    ):
        raise _hub_error(
            "BOARD.CAPACITY_REACHED",
            "This board has reached its 500-player working limit.",
            "Remove an active player before adding another one.",
            409,
        )
    create_or_restore_entry(session, board, player_id=payload.player_id)
    ensure_relevance(
        session,
        payload.player_id,
        "saved_board",
        reference_id=board.id,
    )
    _commit(session)
    return board_to_read(session, board)


def patch_board_entry(
    session: Session,
    board_id: str,
    entry_id: str,
    payload: BoardEntryPatch,
) -> BoardRead:
    board = _require_mutable_board(session, board_id)
    entry = get_entry_row(session, board.id, entry_id)
    if entry is None or not entry.active:
        raise _hub_error(
            "BOARD.ENTRY_NOT_FOUND",
            "That player is not active on this board.",
            "Refresh the board and choose an available player.",
            404,
        )
    fields = payload.model_fields_set
    if "tier_id" in fields:
        if payload.tier_id is not None and (
            get_tier_row(session, board.id, payload.tier_id) is None
        ):
            raise _hub_error(
                "BOARD.TIER_NOT_FOUND",
                "That tier could not be found on this board.",
                "Choose a tier from this board.",
                404,
            )
        entry.tier_id = payload.tier_id
    if "note" in fields:
        entry.note = _optional_text(payload.note)
    if payload.favorite is not None:
        entry.favorite = payload.favorite
    entry.updated_at = utc_now_text()
    touch_board(board)
    _commit(session)
    return board_to_read(session, board)


def remove_board_entry(
    session: Session,
    board_id: str,
    entry_id: str,
) -> BoardRead:
    board = _require_mutable_board(session, board_id)
    entry = get_entry_row(session, board.id, entry_id)
    if entry is None:
        raise _hub_error(
            "BOARD.ENTRY_NOT_FOUND",
            "That player could not be found on this board.",
            "Refresh the board and choose an available player.",
            404,
        )
    archive_entry(session, board, entry)
    _commit(session)
    return board_to_read(session, board)


def reorder_board(
    session: Session,
    board_id: str,
    payload: BoardOrderUpdate,
) -> BoardRead:
    board = _require_mutable_board(session, board_id)
    active_player_ids = [
        entry.player_id for entry in list_active_entry_rows(session, board.id)
    ]
    requested_ids = payload.player_ids
    if (
        len(requested_ids) != len(set(requested_ids))
        or len(requested_ids) != len(active_player_ids)
        or set(requested_ids) != set(active_player_ids)
    ):
        raise _hub_error(
            "BOARD.ORDER_CONFLICT",
            "The board changed before that order could be saved.",
            "Refresh the board, then reorder the complete current player list.",
            409,
        )
    apply_entry_order(session, board, requested_ids)
    _commit(session)
    return board_to_read(session, board)


def _csv_safe(value: object) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


def export_board_csv(session: Session, board_id: str) -> str:
    board = _require_board(session, board_id)
    board_read = board_to_read(session, board)
    tier_names = {tier.id: tier.name for tier in board_read.tiers}
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "board_id",
            "board_name",
            "rank",
            "canonical_player_id",
            "name",
            "position",
            "team",
            "tier",
            "favorite",
            "note",
        ]
    )
    for entry in board_read.entries:
        writer.writerow(
            [
                board.id,
                _csv_safe(board.name),
                entry.rank,
                entry.player.id,
                _csv_safe(entry.player.display_name),
                entry.player.primary_position,
                entry.player.team or "",
                _csv_safe(tier_names.get(entry.tier_id, "")),
                "yes" if entry.favorite else "no",
                _csv_safe(entry.note),
            ]
        )
    return output.getvalue()
