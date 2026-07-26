from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from friendly_hub.core.errors import HubError
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.boards.models import BoardEntryRow, PersonalBoardRow
from friendly_hub.domains.boards.repository import (
    get_board_row,
    get_tier_row,
    list_active_entry_rows,
    list_tier_rows,
)
from friendly_hub.domains.gut_elo.engine import (
    ActionInput,
    ParticipantInput,
    default_target,
    replay,
    select_next_pair,
)
from friendly_hub.domains.gut_elo.models import (
    GutEloActionRow,
    GutEloParticipantRow,
    GutEloSessionRow,
)
from friendly_hub.domains.gut_elo.schemas import (
    GutEloActionCreate,
    GutEloActionRead,
    GutEloPairRead,
    GutEloParticipantRead,
    GutEloProgressRead,
    GutEloSessionCreate,
    GutEloSessionListResponse,
    GutEloSessionPatch,
    GutEloSessionRead,
    GutEloSessionSummary,
)
from friendly_hub.domains.players.models import PlayerRow
from friendly_hub.domains.players.repository import player_to_read

MAX_PARTICIPANTS = 500


def _hub_error(code: str, message: str, action: str, status_code: int) -> HubError:
    return HubError(
        code=code,
        message=message,
        action=action,
        status_code=status_code,
    )


def _commit(session: Session) -> None:
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise


def _require_session(session: Session, session_id: str) -> GutEloSessionRow:
    row = session.get(GutEloSessionRow, session_id)
    if row is None:
        raise _hub_error(
            "GUT_ELO.NOT_FOUND",
            "That Gut ELO session could not be found.",
            "Return to the Personal Board and choose an available session.",
            404,
        )
    return row


def _participant_rows(
    session: Session,
    session_id: str,
) -> list[GutEloParticipantRow]:
    return list(
        session.scalars(
            select(GutEloParticipantRow)
            .where(GutEloParticipantRow.session_id == session_id)
            .order_by(
                GutEloParticipantRow.starting_manual_rank,
                GutEloParticipantRow.player_id,
            )
        )
    )


def _active_action_rows(
    session: Session,
    session_id: str,
) -> list[GutEloActionRow]:
    return list(
        session.scalars(
            select(GutEloActionRow)
            .where(
                GutEloActionRow.session_id == session_id,
                GutEloActionRow.undone_at.is_(None),
            )
            .order_by(GutEloActionRow.sequence_number)
        )
    )


def _participant_inputs(
    rows: list[GutEloParticipantRow],
) -> list[ParticipantInput]:
    return [
        ParticipantInput(
            player_id=row.player_id,
            starting_manual_rank=row.starting_manual_rank,
        )
        for row in rows
    ]


def _action_inputs(rows: list[GutEloActionRow]) -> list[ActionInput]:
    return [
        ActionInput(
            player_a_id=row.player_a_id,
            player_b_id=row.player_b_id,
            outcome=row.outcome,
        )
        for row in rows
    ]


def _progress(
    *,
    target_count: int,
    participant_count: int,
    actions: list[GutEloActionRow],
    decisive_counts: dict[str, int],
    top_order_change_count: int,
) -> GutEloProgressRead:
    decisive_count = sum(
        action.outcome in {"a_win", "b_win"} for action in actions
    )
    insufficient_count = sum(
        action.outcome == "insufficient" for action in actions
    )
    skip_count = sum(action.outcome == "skip" for action in actions)
    resolved_count = decisive_count + insufficient_count
    progress_percent = min(100, round(resolved_count * 100 / target_count))
    participants_with_decision = sum(count > 0 for count in decisive_counts.values())
    coverage_percent = (
        round(participants_with_decision * 100 / participant_count)
        if participant_count
        else 0
    )
    if progress_percent < 25:
        label = "starting"
        explanation = (
            "This is an early read; more resolved comparisons are needed "
            "before the session has broad coverage."
        )
    elif progress_percent < 75:
        label = "developing"
        explanation = (
            "The preference signal is developing, but the session has not "
            "reached three quarters of its bounded target."
        )
    elif top_order_change_count < 2:
        label = "useful_signal"
        explanation = (
            "The session has broad progress and fewer than two of the latest "
            "five decisive choices changed the leading order."
        )
    else:
        label = "still_moving"
        explanation = (
            "The session has broad progress, but at least two of the latest "
            "five decisive choices still changed the leading order."
        )
    return GutEloProgressRead(
        resolved_count=resolved_count,
        decisive_count=decisive_count,
        insufficient_count=insufficient_count,
        skip_count=skip_count,
        target_count=target_count,
        progress_percent=progress_percent,
        participants_with_decision=participants_with_decision,
        participant_count=participant_count,
        coverage_percent=coverage_percent,
        stability_label=label,
        stability_explanation=explanation,
    )


def _player_map(session: Session, player_ids: list[str]) -> dict[str, PlayerRow]:
    return {
        row.id: row
        for row in session.scalars(
            select(PlayerRow).where(PlayerRow.id.in_(player_ids))
        )
    }


def _summary(
    session: Session,
    row: GutEloSessionRow,
    *,
    board: PersonalBoardRow | None = None,
    participant_count: int | None = None,
    resolved_count: int | None = None,
) -> GutEloSessionSummary:
    board = board or get_board_row(session, row.board_id)
    if board is None:
        raise _hub_error(
            "GUT_ELO.BOARD_NOT_FOUND",
            "The Personal Board for that session is unavailable.",
            "Return to the board list and choose an available board.",
            404,
        )
    if participant_count is None:
        participant_count = (
            session.scalar(
                select(func.count())
                .select_from(GutEloParticipantRow)
                .where(GutEloParticipantRow.session_id == row.id)
            )
            or 0
        )
    if resolved_count is None:
        resolved_count = (
            session.scalar(
                select(func.count())
                .select_from(GutEloActionRow)
                .where(
                    GutEloActionRow.session_id == row.id,
                    GutEloActionRow.undone_at.is_(None),
                    GutEloActionRow.outcome.in_(
                        ("a_win", "b_win", "insufficient")
                    ),
                )
            )
            or 0
        )
    return GutEloSessionSummary(
        id=row.id,
        board_id=row.board_id,
        board_name=board.name,
        board_scope=board.scope,
        queue_mode=row.queue_mode,
        position=row.position,
        tier_id=row.tier_id,
        status=row.status,
        participant_count=participant_count,
        resolved_count=resolved_count,
        target_count=row.target_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
    )


def list_sessions(
    session: Session,
    board_id: str,
) -> GutEloSessionListResponse:
    board = get_board_row(session, board_id)
    if board is None:
        raise _hub_error(
            "BOARD.NOT_FOUND",
            "That personal board could not be found.",
            "Return to the board list and choose an available board.",
            404,
        )
    rows = list(
        session.scalars(
            select(GutEloSessionRow)
            .where(GutEloSessionRow.board_id == board_id)
            .order_by(GutEloSessionRow.updated_at.desc(), GutEloSessionRow.id)
        )
    )
    if not rows:
        return GutEloSessionListResponse(items=[])
    session_ids = [row.id for row in rows]
    participant_counts = dict(
        session.execute(
            select(
                GutEloParticipantRow.session_id,
                func.count(),
            )
            .where(GutEloParticipantRow.session_id.in_(session_ids))
            .group_by(GutEloParticipantRow.session_id)
        ).all()
    )
    resolved_counts = dict(
        session.execute(
            select(
                GutEloActionRow.session_id,
                func.count(),
            )
            .where(
                GutEloActionRow.session_id.in_(session_ids),
                GutEloActionRow.undone_at.is_(None),
                GutEloActionRow.outcome.in_(
                    ("a_win", "b_win", "insufficient")
                ),
            )
            .group_by(GutEloActionRow.session_id)
        ).all()
    )
    return GutEloSessionListResponse(
        items=[
            _summary(
                session,
                row,
                board=board,
                participant_count=participant_counts.get(row.id, 0),
                resolved_count=resolved_counts.get(row.id, 0),
            )
            for row in rows
        ]
    )


def _validate_queue(
    session: Session,
    board_id: str,
    payload: GutEloSessionCreate,
) -> tuple[list[BoardEntryRow], dict[str, str | None]]:
    if payload.queue_mode == "position":
        if payload.position is None or payload.tier_id is not None:
            raise _hub_error(
                "GUT_ELO.INVALID_QUEUE",
                "A position queue requires one position and no tier.",
                "Choose a position-only comparison queue.",
                422,
            )
    elif payload.queue_mode == "tier":
        if payload.tier_id is None or payload.position is not None:
            raise _hub_error(
                "GUT_ELO.INVALID_QUEUE",
                "A tier queue requires one tier and no position.",
                "Choose a tier from this Personal Board.",
                422,
            )
        if get_tier_row(session, board_id, payload.tier_id) is None:
            raise _hub_error(
                "GUT_ELO.TIER_NOT_FOUND",
                "That tier could not be found on this Personal Board.",
                "Choose an available tier from this board.",
                404,
            )
    elif payload.position is not None or payload.tier_id is not None:
        raise _hub_error(
            "GUT_ELO.INVALID_QUEUE",
            "That comparison queue does not use a position or tier filter.",
            "Clear the extra filter and try again.",
            422,
        )

    entries = list_active_entry_rows(session, board_id)
    player_rows = _player_map(session, [entry.player_id for entry in entries])
    if payload.queue_mode == "position":
        entries = [
            entry
            for entry in entries
            if player_rows[entry.player_id].primary_position == payload.position
        ]
    elif payload.queue_mode == "tier":
        entries = [entry for entry in entries if entry.tier_id == payload.tier_id]
    tier_names = {tier.id: tier.name for tier in list_tier_rows(session, board_id)}
    return entries, {
        entry.id: tier_names.get(entry.tier_id) for entry in entries
    }


def create_session(
    session: Session,
    board_id: str,
    payload: GutEloSessionCreate,
) -> GutEloSessionRead:
    board = get_board_row(session, board_id)
    if board is None:
        raise _hub_error(
            "BOARD.NOT_FOUND",
            "That personal board could not be found.",
            "Return to the board list and choose an available board.",
            404,
        )
    if board.archived:
        raise _hub_error(
            "GUT_ELO.BOARD_ARCHIVED",
            "An archived board cannot start a new Gut ELO session.",
            "Restore the board before starting comparisons.",
            409,
        )
    entries, tier_name_by_entry = _validate_queue(
        session,
        board_id,
        payload,
    )
    if len(entries) < 2:
        raise _hub_error(
            "GUT_ELO.NOT_ENOUGH_PLAYERS",
            "That queue needs at least two active board players.",
            "Add another eligible player or choose a broader queue.",
            409,
        )
    if len(entries) > MAX_PARTICIPANTS:
        raise _hub_error(
            "GUT_ELO.TOO_MANY_PLAYERS",
            "That queue exceeds the 500-player Gut ELO session limit.",
            "Choose a position or tier queue with 500 players or fewer.",
            409,
        )
    calculated_target = default_target(len(entries))
    if (
        payload.target_count is not None
        and payload.target_count > calculated_target
    ):
        raise _hub_error(
            "GUT_ELO.TARGET_TOO_LARGE",
            "That comparison target exceeds this queue's bounded limit.",
            f"Choose a target from 1 through {calculated_target}.",
            422,
        )
    now = utc_now_text()
    row = GutEloSessionRow(
        id=str(uuid4()),
        board_id=board_id,
        queue_mode=payload.queue_mode,
        position=payload.position,
        tier_id=payload.tier_id,
        status="active",
        target_count=payload.target_count or calculated_target,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )
    session.add(row)
    session.flush()
    for entry in entries:
        session.add(
            GutEloParticipantRow(
                id=str(uuid4()),
                session_id=row.id,
                player_id=entry.player_id,
                starting_manual_rank=entry.manual_order,
                starting_tier_name=tier_name_by_entry[entry.id],
                created_at=now,
            )
        )
    _commit(session)
    return read_session(session, row.id)


def read_session(session: Session, session_id: str) -> GutEloSessionRead:
    row = _require_session(session, session_id)
    participants = _participant_rows(session, row.id)
    actions = _active_action_rows(session, row.id)
    participant_inputs = _participant_inputs(participants)
    action_inputs = _action_inputs(actions)
    replay_result = replay(participant_inputs, action_inputs)
    progress = _progress(
        target_count=row.target_count,
        participant_count=len(participants),
        actions=actions,
        decisive_counts=replay_result.decisive_counts,
        top_order_change_count=replay_result.top_order_change_count,
    )
    players = _player_map(
        session,
        [participant.player_id for participant in participants],
    )
    participant_by_id = {
        participant.player_id: participant for participant in participants
    }
    results = [
        GutEloParticipantRead(
            player=player_to_read(session, players[player_id], relevant=True),
            starting_manual_rank=participant_by_id[
                player_id
            ].starting_manual_rank,
            starting_tier_name=participant_by_id[
                player_id
            ].starting_tier_name,
            gut_rank=rank,
            rating=replay_result.ratings[player_id],
            decisive_count=replay_result.decisive_counts[player_id],
        )
        for rank, player_id in enumerate(replay_result.order, start=1)
    ]
    revision = len(actions)
    next_pair = None
    if row.status == "active" and progress.resolved_count < row.target_count:
        pair = select_next_pair(
            participant_inputs,
            action_inputs,
            queue_mode=row.queue_mode,
            replay_result=replay_result,
        )
        if pair is not None:
            next_pair = GutEloPairRead(
                revision=revision,
                player_a=player_to_read(session, players[pair[0]], relevant=True),
                player_b=player_to_read(session, players[pair[1]], relevant=True),
            )
    return GutEloSessionRead(
        **_summary(
            session,
            row,
            participant_count=len(participants),
            resolved_count=progress.resolved_count,
        ).model_dump(),
        revision=revision,
        participants=results,
        progress=progress,
        actions=[
            GutEloActionRead(
                id=action.id,
                sequence_number=action.sequence_number,
                player_a_id=action.player_a_id,
                player_b_id=action.player_b_id,
                outcome=action.outcome,
                created_at=action.created_at,
            )
            for action in reversed(actions)
        ],
        next_pair=next_pair,
        manual_board_unchanged=True,
    )


def patch_session(
    session: Session,
    session_id: str,
    payload: GutEloSessionPatch,
) -> GutEloSessionRead:
    row = _require_session(session, session_id)
    if row.status == "completed":
        raise _hub_error(
            "GUT_ELO.ALREADY_COMPLETED",
            "That Gut ELO session has reached its bounded target.",
            "Review its results or start a new session.",
            409,
        )
    row.status = payload.status
    row.updated_at = utc_now_text()
    _commit(session)
    return read_session(session, row.id)


def add_action(
    session: Session,
    session_id: str,
    payload: GutEloActionCreate,
) -> GutEloSessionRead:
    row = _require_session(session, session_id)
    if row.status != "active":
        raise _hub_error(
            "GUT_ELO.NOT_ACTIVE",
            "That Gut ELO session is not active.",
            "Resume the session before recording a comparison.",
            409,
        )
    current = read_session(session, row.id)
    if current.next_pair is None:
        raise _hub_error(
            "GUT_ELO.NO_PAIR",
            "That Gut ELO session has no available comparison.",
            "Review the session results or start a new session.",
            409,
        )
    expected = current.next_pair
    if (
        payload.revision != current.revision
        or payload.player_a_id != expected.player_a.id
        or payload.player_b_id != expected.player_b.id
    ):
        raise _hub_error(
            "GUT_ELO.STALE_PAIR",
            "The comparison session changed before that choice was saved.",
            "Refresh the session and answer the currently offered pair.",
            409,
        )
    max_sequence = (
        session.scalar(
            select(func.max(GutEloActionRow.sequence_number)).where(
                GutEloActionRow.session_id == row.id
            )
        )
        or 0
    )
    now = utc_now_text()
    session.add(
        GutEloActionRow(
            id=str(uuid4()),
            session_id=row.id,
            sequence_number=max_sequence + 1,
            player_a_id=payload.player_a_id,
            player_b_id=payload.player_b_id,
            outcome=payload.outcome,
            created_at=now,
            undone_at=None,
        )
    )
    session.flush()
    active_actions = _active_action_rows(session, row.id)
    resolved_count = sum(
        action.outcome in {"a_win", "b_win", "insufficient"}
        for action in active_actions
    )
    row.updated_at = now
    if resolved_count >= row.target_count:
        row.status = "completed"
        row.completed_at = now
    _commit(session)
    return read_session(session, row.id)


def undo_latest_action(session: Session, session_id: str) -> GutEloSessionRead:
    row = _require_session(session, session_id)
    latest = session.scalar(
        select(GutEloActionRow)
        .where(
            GutEloActionRow.session_id == row.id,
            GutEloActionRow.undone_at.is_(None),
        )
        .order_by(GutEloActionRow.sequence_number.desc())
        .limit(1)
    )
    if latest is None:
        raise _hub_error(
            "GUT_ELO.NOTHING_TO_UNDO",
            "There is no comparison action to undo.",
            "Record a comparison before using undo.",
            409,
        )
    now = utc_now_text()
    latest.undone_at = now
    row.updated_at = now
    remaining = [
        action
        for action in _active_action_rows(session, row.id)
        if action.id != latest.id
    ]
    resolved_count = sum(
        action.outcome in {"a_win", "b_win", "insufficient"}
        for action in remaining
    )
    if row.status == "completed" and resolved_count < row.target_count:
        row.status = "active"
        row.completed_at = None
    _commit(session)
    return read_session(session, row.id)
