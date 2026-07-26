from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.boards.models import (
    BoardEntryRow,
    BoardTierRow,
    PersonalBoardRow,
)
from friendly_hub.domains.boards.schemas import (
    BoardEntryRead,
    BoardRead,
    BoardSummary,
    BoardTierRead,
)
from friendly_hub.domains.players.models import PlayerRow
from friendly_hub.domains.players.repository import player_to_read


def get_board_row(session: Session, board_id: str) -> PersonalBoardRow | None:
    return session.get(PersonalBoardRow, board_id)


def list_board_rows(
    session: Session,
    *,
    include_archived: bool,
) -> list[PersonalBoardRow]:
    statement = select(PersonalBoardRow)
    if not include_archived:
        statement = statement.where(PersonalBoardRow.archived.is_(False))
    return list(
        session.scalars(
            statement.order_by(
                PersonalBoardRow.archived,
                PersonalBoardRow.updated_at.desc(),
                PersonalBoardRow.name,
                PersonalBoardRow.id,
            )
        )
    )


def board_to_summary(session: Session, row: PersonalBoardRow) -> BoardSummary:
    entry_count = (
        session.scalar(
            select(func.count())
            .select_from(BoardEntryRow)
            .where(
                BoardEntryRow.board_id == row.id,
                BoardEntryRow.active.is_(True),
            )
        )
        or 0
    )
    return BoardSummary(
        id=row.id,
        name=row.name,
        description=row.description,
        league_profile_id=row.league_profile_id,
        scope=row.scope,
        archived=row.archived,
        entry_count=entry_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_tier_rows(session: Session, board_id: str) -> list[BoardTierRow]:
    return list(
        session.scalars(
            select(BoardTierRow)
            .where(BoardTierRow.board_id == board_id)
            .order_by(BoardTierRow.tier_order, BoardTierRow.id)
        )
    )


def get_tier_row(
    session: Session,
    board_id: str,
    tier_id: str,
) -> BoardTierRow | None:
    return session.scalar(
        select(BoardTierRow).where(
            BoardTierRow.id == tier_id,
            BoardTierRow.board_id == board_id,
        )
    )


def tier_to_read(row: BoardTierRow) -> BoardTierRead:
    return BoardTierRead(
        id=row.id,
        name=row.name,
        color=row.color,
        tier_order=row.tier_order,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_active_entry_rows(
    session: Session,
    board_id: str,
) -> list[BoardEntryRow]:
    return list(
        session.scalars(
            select(BoardEntryRow)
            .where(
                BoardEntryRow.board_id == board_id,
                BoardEntryRow.active.is_(True),
            )
            .order_by(BoardEntryRow.manual_order, BoardEntryRow.player_id)
        )
    )


def get_entry_row(
    session: Session,
    board_id: str,
    entry_id: str,
) -> BoardEntryRow | None:
    return session.scalar(
        select(BoardEntryRow).where(
            BoardEntryRow.id == entry_id,
            BoardEntryRow.board_id == board_id,
        )
    )


def get_entry_for_player(
    session: Session,
    board_id: str,
    player_id: str,
) -> BoardEntryRow | None:
    return session.scalar(
        select(BoardEntryRow).where(
            BoardEntryRow.board_id == board_id,
            BoardEntryRow.player_id == player_id,
        )
    )


def board_to_read(session: Session, row: PersonalBoardRow) -> BoardRead:
    summary = board_to_summary(session, row)
    tiers = [tier_to_read(tier) for tier in list_tier_rows(session, row.id)]
    joined_entries = session.execute(
        select(BoardEntryRow, PlayerRow)
        .join(PlayerRow, PlayerRow.id == BoardEntryRow.player_id)
        .where(
            BoardEntryRow.board_id == row.id,
            BoardEntryRow.active.is_(True),
        )
        .order_by(BoardEntryRow.manual_order, BoardEntryRow.player_id)
    ).all()
    entries = [
        BoardEntryRead(
            id=entry.id,
            player=player_to_read(session, player, relevant=True),
            tier_id=entry.tier_id,
            rank=entry.manual_order,
            note=entry.note,
            favorite=entry.favorite,
            updated_at=entry.updated_at,
        )
        for entry, player in joined_entries
    ]
    return BoardRead(
        **summary.model_dump(),
        tiers=tiers,
        entries=entries,
    )


def create_board_row(
    session: Session,
    *,
    name: str,
    description: str | None,
    league_profile_id: str | None,
    scope: str,
) -> PersonalBoardRow:
    now = utc_now_text()
    row = PersonalBoardRow(
        id=str(uuid4()),
        name=name,
        description=description,
        league_profile_id=league_profile_id,
        scope=scope,
        archived=False,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    return row


def touch_board(row: PersonalBoardRow) -> None:
    row.updated_at = utc_now_text()


def create_tier_row(
    session: Session,
    board: PersonalBoardRow,
    *,
    name: str,
    color: str | None,
    tier_order: int | None,
) -> BoardTierRow:
    now = utc_now_text()
    row = BoardTierRow(
        id=str(uuid4()),
        board_id=board.id,
        name=name,
        color=color,
        tier_order=len(list_tier_rows(session, board.id)) + 1,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    if tier_order is not None:
        move_tier(session, board.id, row, tier_order)
    touch_board(board)
    return row


def move_tier(
    session: Session,
    board_id: str,
    tier: BoardTierRow,
    requested_order: int,
) -> None:
    rows = [row for row in list_tier_rows(session, board_id) if row.id != tier.id]
    insertion_index = min(max(requested_order - 1, 0), len(rows))
    rows.insert(insertion_index, tier)
    now = utc_now_text()
    for order, row in enumerate(rows, start=1):
        row.tier_order = order
        row.updated_at = now


def delete_tier_row(
    session: Session,
    board: PersonalBoardRow,
    tier: BoardTierRow,
) -> None:
    session.execute(
        update(BoardEntryRow)
        .where(
            BoardEntryRow.board_id == board.id,
            BoardEntryRow.tier_id == tier.id,
        )
        .values(tier_id=None, updated_at=utc_now_text())
    )
    session.delete(tier)
    session.flush()
    remaining = list_tier_rows(session, board.id)
    now = utc_now_text()
    for order, row in enumerate(remaining, start=1):
        row.tier_order = order
        row.updated_at = now
    touch_board(board)


def next_entry_order(session: Session, board_id: str) -> int:
    active_count = session.scalar(
        select(func.count())
        .select_from(BoardEntryRow)
        .where(
            BoardEntryRow.board_id == board_id,
            BoardEntryRow.active.is_(True),
        )
    )
    return (active_count or 0) + 1


def create_or_restore_entry(
    session: Session,
    board: PersonalBoardRow,
    *,
    player_id: str,
) -> BoardEntryRow:
    existing = get_entry_for_player(session, board.id, player_id)
    now = utc_now_text()
    if existing is not None:
        if not existing.active:
            restored_order = next_entry_order(session, board.id)
            existing.active = True
            existing.manual_order = restored_order
            existing.updated_at = now
            touch_board(board)
        return existing

    row = BoardEntryRow(
        id=str(uuid4()),
        board_id=board.id,
        player_id=player_id,
        tier_id=None,
        manual_order=next_entry_order(session, board.id),
        note=None,
        favorite=False,
        active=True,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    touch_board(board)
    return row


def compact_entry_order(session: Session, board_id: str) -> None:
    now = utc_now_text()
    for order, row in enumerate(list_active_entry_rows(session, board_id), start=1):
        row.manual_order = order
        row.updated_at = now


def archive_entry(
    session: Session,
    board: PersonalBoardRow,
    entry: BoardEntryRow,
) -> None:
    if entry.active:
        entry.active = False
        entry.updated_at = utc_now_text()
        session.flush()
        compact_entry_order(session, board.id)
        touch_board(board)


def apply_entry_order(
    session: Session,
    board: PersonalBoardRow,
    player_ids: list[str],
) -> None:
    entries = {
        entry.player_id: entry for entry in list_active_entry_rows(session, board.id)
    }
    now = utc_now_text()
    for order, player_id in enumerate(player_ids, start=1):
        entry = entries[player_id]
        entry.manual_order = order
        entry.updated_at = now
    touch_board(board)
