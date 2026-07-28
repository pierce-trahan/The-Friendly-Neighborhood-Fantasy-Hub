from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from friendly_hub.core.errors import HubError
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.boards.models import BoardEntryRow, PersonalBoardRow
from friendly_hub.domains.boards.repository import (
    get_board_row,
    list_active_entry_rows,
    list_tier_rows,
)
from friendly_hub.domains.drafts.engine import build_draft_order, picks_until_slot
from friendly_hub.domains.drafts.models import (
    DraftCandidateRow,
    DraftPickRevisionRow,
    DraftPickRow,
    DraftSessionRow,
    DraftTeamRow,
)
from friendly_hub.domains.drafts.schemas import (
    DraftBlindCandidateListResponse,
    DraftBlindCandidateRead,
    DraftCandidateListResponse,
    DraftContextCandidateListResponse,
    DraftContextCandidateRead,
    DraftCurrentPickRead,
    DraftPickCorrection,
    DraftPickCreate,
    DraftPickRead,
    DraftResetCreate,
    DraftRevisionGuard,
    DraftSessionCreate,
    DraftSessionListResponse,
    DraftSessionPatch,
    DraftSessionRead,
    DraftSessionSummary,
    DraftTeamRead,
    DraftView,
)
from friendly_hub.domains.leagues.models import LeagueProfileRow
from friendly_hub.domains.players.models import PlayerRelevanceRow, PlayerRow

MAX_CANDIDATES = 2_000


@dataclass(frozen=True)
class DraftPickMutation:
    draft_session: DraftSessionRow
    pick: DraftPickRow
    pick_revision: DraftPickRevisionRow
    candidate: DraftCandidateRow


def _error(code: str, message: str, action: str, status_code: int) -> HubError:
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


def _require_session(session: Session, session_id: str) -> DraftSessionRow:
    row = session.get(DraftSessionRow, session_id)
    if row is None:
        raise _error(
            "DRAFT.NOT_FOUND",
            "That draft session could not be found.",
            "Return to the draft-session list and choose an available session.",
            404,
        )
    return row


def _require_revision(row: DraftSessionRow, revision: int) -> None:
    if revision != row.revision:
        raise _error(
            "DRAFT.STALE_REVISION",
            "The draft changed before that action could be saved.",
            "Refresh the draft room and retry from the current pick.",
            409,
        )


def _advance_revision(
    session: Session,
    row: DraftSessionRow,
    expected_revision: int,
) -> None:
    result = session.execute(
        update(DraftSessionRow)
        .where(
            DraftSessionRow.id == row.id,
            DraftSessionRow.revision == expected_revision,
        )
        .values(revision=expected_revision + 1)
    )
    if result.rowcount != 1:
        session.rollback()
        raise _error(
            "DRAFT.STALE_REVISION",
            "The draft changed before that action could be saved.",
            "Refresh the draft room and retry from the current pick.",
            409,
        )
    session.refresh(row)


def _team_rows(session: Session, session_id: str) -> list[DraftTeamRow]:
    return list(
        session.scalars(
            select(DraftTeamRow)
            .where(DraftTeamRow.session_id == session_id)
            .order_by(DraftTeamRow.draft_slot)
        )
    )


def _pick_rows(session: Session, session_id: str) -> list[DraftPickRow]:
    return list(
        session.scalars(
            select(DraftPickRow)
            .where(DraftPickRow.session_id == session_id)
            .order_by(DraftPickRow.overall_pick)
        )
    )


def _candidate_rows(session: Session, session_id: str) -> list[DraftCandidateRow]:
    return list(
        session.scalars(
            select(DraftCandidateRow).where(DraftCandidateRow.session_id == session_id)
        )
    )


def _candidate_from_player(
    *,
    session_id: str,
    player: PlayerRow,
    now: str,
    source: str,
    entry: BoardEntryRow | None = None,
    tier_name: str | None = None,
    tier_color: str | None = None,
    tier_order: int | None = None,
) -> DraftCandidateRow:
    return DraftCandidateRow(
        id=str(uuid4()),
        session_id=session_id,
        player_id=player.id,
        display_name=player.display_name,
        search_name=player.search_name,
        primary_position=player.primary_position,
        fantasy_positions_json=player.fantasy_positions_json,
        team=player.team,
        player_status=player.status,
        is_rookie=player.is_rookie,
        rookie_class=player.rookie_class,
        snapshot_source=source,
        manual_rank=entry.manual_order if entry else None,
        tier_name=tier_name,
        tier_color=tier_color,
        tier_order=tier_order,
        favorite=entry.favorite if entry else False,
        board_note=entry.note if entry else None,
        created_at=now,
    )


def _snapshot_candidates(
    session: Session,
    draft_session: DraftSessionRow,
    board: PersonalBoardRow,
    now: str,
) -> int:
    entries = list_active_entry_rows(session, board.id)
    entry_by_player = {entry.player_id: entry for entry in entries}
    relevant_ids = set(
        session.scalars(
            select(PlayerRelevanceRow.player_id).where(
                PlayerRelevanceRow.active.is_(True)
            )
        )
    )
    player_ids = relevant_ids | set(entry_by_player)
    if len(player_ids) < 2:
        raise _error(
            "DRAFT.NOT_ENOUGH_CANDIDATES",
            "A draft session needs at least two available candidates.",
            "Import or mark more players relevant, then try again.",
            409,
        )
    if len(player_ids) > MAX_CANDIDATES:
        raise _error(
            "DRAFT.TOO_MANY_CANDIDATES",
            "That player pool exceeds the 2,000-candidate session limit.",
            "Reduce the active relevant player universe and try again.",
            409,
        )
    players = {
        row.id: row
        for row in session.scalars(
            select(PlayerRow).where(PlayerRow.id.in_(player_ids))
        )
    }
    tiers = {tier.id: tier for tier in list_tier_rows(session, board.id)}
    for player_id in sorted(player_ids):
        player = players.get(player_id)
        if player is None:
            continue
        entry = entry_by_player.get(player_id)
        tier = tiers.get(entry.tier_id) if entry and entry.tier_id else None
        session.add(
            _candidate_from_player(
                session_id=draft_session.id,
                player=player,
                now=now,
                source="personal_board" if entry else "relevant_pool",
                entry=entry,
                tier_name=tier.name if tier else None,
                tier_color=tier.color if tier else None,
                tier_order=tier.tier_order if tier else None,
            )
        )
    return len(players)


def _create_session_rows(
    session: Session,
    board: PersonalBoardRow,
    payload: DraftSessionCreate,
    *,
    reset_from_session_id: str | None = None,
) -> DraftSessionRow:
    if board.archived:
        raise _error(
            "DRAFT.BOARD_ARCHIVED",
            "An archived Personal Board cannot start a draft session.",
            "Restore the board before creating the session.",
            409,
        )
    if payload.league_profile_id and session.get(
        LeagueProfileRow, payload.league_profile_id
    ) is None:
        raise _error(
            "DRAFT.LEAGUE_PROFILE_NOT_FOUND",
            "That league profile could not be found.",
            "Choose an available local league profile or clear the selection.",
            404,
        )
    now = utc_now_text()
    row = DraftSessionRow(
        id=str(uuid4()),
        name=payload.name.strip(),
        board_id=board.id,
        league_profile_id=payload.league_profile_id,
        mode=payload.mode,
        draft_format=payload.draft_format,
        third_round_reversal=payload.third_round_reversal,
        team_count=payload.team_count,
        round_count=payload.round_count,
        user_slot=payload.user_slot,
        pick_timer_seconds=payload.pick_timer_seconds,
        status="active",
        revision=0,
        reset_from_session_id=reset_from_session_id,
        created_at=now,
        updated_at=now,
        completed_at=None,
        reset_at=None,
    )
    session.add(row)
    session.flush()
    team_names = payload.team_names or [
        "Your Team" if slot == payload.user_slot else f"Team {slot}"
        for slot in range(1, payload.team_count + 1)
    ]
    for slot, display_name in enumerate(team_names, start=1):
        cleaned_name = display_name.strip()
        if not cleaned_name:
            raise _error(
                "DRAFT.INVALID_TEAM_NAME",
                "Every draft slot needs a display name.",
                "Enter a name for each team and try again.",
                422,
            )
        session.add(
            DraftTeamRow(
                id=str(uuid4()),
                session_id=row.id,
                draft_slot=slot,
                display_name=cleaned_name,
                is_user=slot == payload.user_slot,
            )
        )
    for pick in build_draft_order(
        payload.draft_format,
        payload.third_round_reversal,
        payload.team_count,
        payload.round_count,
    ):
        session.add(
            DraftPickRow(
                id=str(uuid4()),
                session_id=row.id,
                overall_pick=pick.overall_pick,
                round_number=pick.round_number,
                pick_in_round=pick.pick_in_round,
                selecting_slot=pick.selecting_slot,
                player_id=None,
                recorded_at=None,
                client_entered_at=None,
                correction_count=0,
            )
        )
    _snapshot_candidates(session, row, board, now)
    session.flush()
    return row


def create_session(
    session: Session,
    board_id: str,
    payload: DraftSessionCreate,
) -> DraftSessionRead:
    row = create_session_in_transaction(session, board_id, payload)
    _commit(session)
    return read_session(session, row.id)


def create_session_in_transaction(
    session: Session,
    board_id: str,
    payload: DraftSessionCreate,
) -> DraftSessionRow:
    """Create Phase 3 rows without committing so another domain can join the unit."""
    board = get_board_row(session, board_id)
    if board is None:
        raise _error(
            "BOARD.NOT_FOUND",
            "That Personal Board could not be found.",
            "Return to the board list and choose an available board.",
            404,
        )
    return _create_session_rows(session, board, payload)


def _summary(
    session: Session,
    row: DraftSessionRow,
    *,
    board: PersonalBoardRow | None = None,
    active_pick_count: int | None = None,
) -> DraftSessionSummary:
    board = board or get_board_row(session, row.board_id)
    if board is None:
        raise _error(
            "DRAFT.BOARD_NOT_FOUND",
            "The Personal Board for that draft is unavailable.",
            "Return to the board list and choose an available board.",
            404,
        )
    if active_pick_count is None:
        active_pick_count = (
            session.scalar(
                select(func.count())
                .select_from(DraftPickRow)
                .where(
                    DraftPickRow.session_id == row.id,
                    DraftPickRow.player_id.is_not(None),
                )
            )
            or 0
        )
    return DraftSessionSummary(
        id=row.id,
        name=row.name,
        board_id=row.board_id,
        board_name=board.name,
        mode=row.mode,
        draft_format=row.draft_format,
        third_round_reversal=row.third_round_reversal,
        team_count=row.team_count,
        round_count=row.round_count,
        user_slot=row.user_slot,
        status=row.status,
        revision=row.revision,
        active_pick_count=active_pick_count,
        total_picks=row.team_count * row.round_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_sessions(session: Session, board_id: str) -> DraftSessionListResponse:
    board = get_board_row(session, board_id)
    if board is None:
        raise _error(
            "BOARD.NOT_FOUND",
            "That Personal Board could not be found.",
            "Return to the board list and choose an available board.",
            404,
        )
    rows = list(
        session.scalars(
            select(DraftSessionRow)
            .where(DraftSessionRow.board_id == board_id)
            .order_by(DraftSessionRow.updated_at.desc(), DraftSessionRow.id)
        )
    )
    session_ids = [row.id for row in rows]
    pick_counts = (
        dict(
            session.execute(
                select(DraftPickRow.session_id, func.count())
                .where(
                    DraftPickRow.session_id.in_(session_ids),
                    DraftPickRow.player_id.is_not(None),
                )
                .group_by(DraftPickRow.session_id)
            ).all()
        )
        if session_ids
        else {}
    )
    return DraftSessionListResponse(
        items=[
            _summary(
                session,
                row,
                board=board,
                active_pick_count=pick_counts.get(row.id, 0),
            )
            for row in rows
        ]
    )


def read_session(session: Session, session_id: str) -> DraftSessionRead:
    row = _require_session(session, session_id)
    teams = _team_rows(session, row.id)
    team_by_slot = {team.draft_slot: team for team in teams}
    picks = _pick_rows(session, row.id)
    completed_picks = [pick for pick in picks if pick.player_id is not None]
    candidate_by_player = {
        candidate.player_id: candidate for candidate in _candidate_rows(session, row.id)
    }
    current = next((pick for pick in picks if pick.player_id is None), None)
    if row.status in {"completed", "reset"}:
        current = None
    current_read = (
        DraftCurrentPickRead(
            overall_pick=current.overall_pick,
            round_number=current.round_number,
            pick_in_round=current.pick_in_round,
            selecting_slot=current.selecting_slot,
            selecting_team=team_by_slot[current.selecting_slot].display_name,
        )
        if current
        else None
    )
    order = build_draft_order(
        row.draft_format,
        row.third_round_reversal,
        row.team_count,
        row.round_count,
    )
    if row.status == "paused":
        guidance = "Resume this session to continue from the preserved current pick."
    elif row.status == "completed":
        guidance = "Review or export the completed draft, or create a new session."
    elif row.status == "reset":
        guidance = "This reset session remains available for audit and export."
    else:
        guidance = None
    return DraftSessionRead(
        **_summary(
            session, row, active_pick_count=len(completed_picks)
        ).model_dump(),
        league_profile_id=row.league_profile_id,
        pick_timer_seconds=row.pick_timer_seconds,
        reset_from_session_id=row.reset_from_session_id,
        teams=[
            DraftTeamRead(
                draft_slot=team.draft_slot,
                display_name=team.display_name,
                is_user=team.is_user,
            )
            for team in teams
        ],
        current_pick=current_read,
        user_on_the_clock=bool(
            current and current.selecting_slot == row.user_slot and row.status == "active"
        ),
        picks_until_user=picks_until_slot(
            order, current.overall_pick if current else None, row.user_slot
        ),
        picks=[
            DraftPickRead(
                overall_pick=pick.overall_pick,
                round_number=pick.round_number,
                pick_in_round=pick.pick_in_round,
                selecting_slot=pick.selecting_slot,
                selecting_team=team_by_slot[pick.selecting_slot].display_name,
                player_id=pick.player_id,
                player_display_name=candidate_by_player[pick.player_id].display_name,
                player_position=candidate_by_player[pick.player_id].primary_position,
                player_team=candidate_by_player[pick.player_id].team,
                recorded_at=pick.recorded_at,
                correction_count=pick.correction_count,
            )
            for pick in reversed(completed_picks)
        ],
        candidate_total=len(candidate_by_player),
        available_count=len(candidate_by_player) - len(completed_picks),
        completed_at=row.completed_at,
        reset_at=row.reset_at,
        recovery_guidance=guidance,
    )


def patch_session(
    session: Session,
    session_id: str,
    payload: DraftSessionPatch,
) -> DraftSessionRead:
    row = _require_session(session, session_id)
    _require_revision(row, payload.revision)
    if row.status in {"completed", "reset"}:
        raise _error(
            "DRAFT.STATUS_LOCKED",
            "A completed or reset session cannot be paused or resumed.",
            "Review the session or start a new draft.",
            409,
        )
    if row.status == payload.status:
        raise _error(
            "DRAFT.STATUS_UNCHANGED",
            "The draft session already has that status.",
            "Refresh the draft room before sending another status change.",
            409,
        )
    _advance_revision(session, row, payload.revision)
    row.status = payload.status
    row.updated_at = utc_now_text()
    _commit(session)
    return read_session(session, row.id)


def _ensure_candidate(
    session: Session,
    row: DraftSessionRow,
    player_id: str,
    now: str,
) -> DraftCandidateRow:
    existing = session.scalar(
        select(DraftCandidateRow).where(
            DraftCandidateRow.session_id == row.id,
            DraftCandidateRow.player_id == player_id,
        )
    )
    if existing is not None:
        return existing
    player = session.get(PlayerRow, player_id)
    if player is None:
        raise _error(
            "DRAFT.PLAYER_NOT_FOUND",
            "That player could not be found.",
            "Choose a player from the local player universe.",
            404,
        )
    count = (
        session.scalar(
            select(func.count())
            .select_from(DraftCandidateRow)
            .where(DraftCandidateRow.session_id == row.id)
        )
        or 0
    )
    if count >= MAX_CANDIDATES:
        raise _error(
            "DRAFT.TOO_MANY_CANDIDATES",
            "The draft has reached its 2,000-candidate limit.",
            "Use a player already available in this draft snapshot.",
            409,
        )
    candidate = _candidate_from_player(
        session_id=row.id,
        player=player,
        now=now,
        source="late_addition",
    )
    session.add(candidate)
    session.flush()
    return candidate


def _drafted_pick(
    session: Session,
    session_id: str,
    player_id: str,
) -> DraftPickRow | None:
    return session.scalar(
        select(DraftPickRow).where(
            DraftPickRow.session_id == session_id,
            DraftPickRow.player_id == player_id,
        )
    )


def record_pick_in_transaction(
    session: Session,
    session_id: str,
    *,
    revision: int,
    expected_overall_pick: int,
    player_id: str,
    client_entered_at: str | None = None,
    expected_selecting_slot: int | None = None,
) -> DraftPickMutation:
    """Apply one guarded pick without committing the caller-owned transaction."""
    row = _require_session(session, session_id)
    _require_revision(row, revision)
    if row.status != "active":
        raise _error(
            "DRAFT.NOT_ACTIVE",
            "Picks can be recorded only while the draft is active.",
            "Resume the session or start a new draft.",
            409,
        )
    current = session.scalar(
        select(DraftPickRow)
        .where(
            DraftPickRow.session_id == row.id,
            DraftPickRow.player_id.is_(None),
        )
        .order_by(DraftPickRow.overall_pick)
        .limit(1)
    )
    if current is None:
        raise _error(
            "DRAFT.COMPLETE",
            "Every pick in this draft is already filled.",
            "Review or export the completed draft.",
            409,
        )
    if current.overall_pick != expected_overall_pick:
        raise _error(
            "DRAFT.STALE_CURRENT_PICK",
            "The draft advanced before that pick could be saved.",
            "Refresh the draft room and use the current overall pick.",
            409,
        )
    if (
        expected_selecting_slot is not None
        and current.selecting_slot != expected_selecting_slot
    ):
        raise _error(
            "DRAFT.STALE_CURRENT_SLOT",
            "The draft order changed before that pick could be saved.",
            "Refresh the draft room and verify the team on the clock.",
            409,
        )
    duplicate = _drafted_pick(session, row.id, player_id)
    if duplicate is not None:
        raise _error(
            "DRAFT.PLAYER_ALREADY_DRAFTED",
            f"That player is already assigned to overall pick {duplicate.overall_pick}.",
            "Choose an available player or correct the existing pick.",
            409,
        )
    now = utc_now_text()
    candidate = _ensure_candidate(session, row, player_id, now)
    _advance_revision(session, row, revision)
    current.player_id = player_id
    current.recorded_at = now
    current.client_entered_at = client_entered_at
    pick_revision = DraftPickRevisionRow(
        id=str(uuid4()),
        session_id=row.id,
        pick_id=current.id,
        session_revision=row.revision,
        action_kind="made",
        previous_player_id=None,
        next_player_id=player_id,
        created_at=now,
    )
    session.add(pick_revision)
    row.updated_at = now
    if current.overall_pick == row.team_count * row.round_count:
        row.status = "completed"
        row.completed_at = now
    return DraftPickMutation(
        draft_session=row,
        pick=current,
        pick_revision=pick_revision,
        candidate=candidate,
    )


def make_pick(
    session: Session,
    session_id: str,
    payload: DraftPickCreate,
) -> DraftSessionRead:
    mutation = record_pick_in_transaction(
        session,
        session_id,
        revision=payload.revision,
        expected_overall_pick=payload.expected_overall_pick,
        player_id=payload.player_id,
        client_entered_at=payload.client_entered_at,
    )
    if (
        mutation.draft_session.mode == "mock"
        and mutation.pick.selecting_slot == mutation.draft_session.user_slot
    ):
        from friendly_hub.domains.mocks.strategy_service import (
            record_guidance_after_user_pick_in_transaction,
        )

        record_guidance_after_user_pick_in_transaction(session, mutation)
    _commit(session)
    return read_session(session, mutation.draft_session.id)


def correct_pick(
    session: Session,
    session_id: str,
    overall_pick: int,
    payload: DraftPickCorrection,
) -> DraftSessionRead:
    row = _require_session(session, session_id)
    _require_revision(row, payload.revision)
    if row.status == "reset":
        raise _error(
            "DRAFT.RESET_LOCKED",
            "A reset session cannot be changed.",
            "Open the replacement session to continue drafting.",
            409,
        )
    pick = session.scalar(
        select(DraftPickRow).where(
            DraftPickRow.session_id == row.id,
            DraftPickRow.overall_pick == overall_pick,
        )
    )
    if pick is None or pick.player_id is None:
        raise _error(
            "DRAFT.PICK_NOT_FOUND",
            "That completed pick could not be found.",
            "Choose a filled pick from the draft rail.",
            404,
        )
    if pick.player_id != payload.expected_current_player_id:
        raise _error(
            "DRAFT.STALE_CORRECTION",
            "That pick changed before the correction could be saved.",
            "Refresh the draft room and verify the current player.",
            409,
        )
    if pick.player_id == payload.replacement_player_id:
        raise _error(
            "DRAFT.SAME_PLAYER",
            "A correction must select a different player.",
            "Choose the intended replacement player.",
            422,
        )
    duplicate = _drafted_pick(session, row.id, payload.replacement_player_id)
    if duplicate is not None:
        raise _error(
            "DRAFT.PLAYER_ALREADY_DRAFTED",
            f"That player is already assigned to overall pick {duplicate.overall_pick}.",
            "Choose an available player or correct that existing pick first.",
            409,
        )
    now = utc_now_text()
    previous_player_id = pick.player_id
    try:
        _ensure_candidate(session, row, payload.replacement_player_id, now)
        _advance_revision(session, row, payload.revision)
        pick.player_id = payload.replacement_player_id
        pick.recorded_at = now
        pick.correction_count += 1
        pick_revision = DraftPickRevisionRow(
            id=str(uuid4()),
            session_id=row.id,
            pick_id=pick.id,
            session_revision=row.revision,
            action_kind="corrected",
            previous_player_id=previous_player_id,
            next_player_id=payload.replacement_player_id,
            created_at=now,
        )
        session.add(pick_revision)
        row.updated_at = now
        if row.mode == "mock":
            from friendly_hub.domains.mocks.lifecycle_service import (
                record_mock_correction_in_transaction,
            )

            record_mock_correction_in_transaction(
                session,
                draft_row=row,
                pick=pick,
                pick_revision=pick_revision,
            )
        _commit(session)
    except Exception:
        session.rollback()
        raise
    return read_session(session, row.id)


def undo_latest_pick(
    session: Session,
    session_id: str,
    payload: DraftRevisionGuard,
) -> DraftSessionRead:
    row = _require_session(session, session_id)
    _require_revision(row, payload.revision)
    if row.status == "reset":
        raise _error(
            "DRAFT.RESET_LOCKED",
            "A reset session cannot be changed.",
            "Open the replacement session to continue drafting.",
            409,
        )
    pick = session.scalar(
        select(DraftPickRow)
        .where(
            DraftPickRow.session_id == row.id,
            DraftPickRow.player_id.is_not(None),
        )
        .order_by(DraftPickRow.overall_pick.desc())
        .limit(1)
    )
    if pick is None:
        raise _error(
            "DRAFT.NOTHING_TO_UNDO",
            "There are no recorded picks to undo.",
            "Record a pick before using undo.",
            409,
        )
    now = utc_now_text()
    previous_player_id = pick.player_id
    try:
        _advance_revision(session, row, payload.revision)
        pick_revision = DraftPickRevisionRow(
            id=str(uuid4()),
            session_id=row.id,
            pick_id=pick.id,
            session_revision=row.revision,
            action_kind="undone",
            previous_player_id=previous_player_id,
            next_player_id=None,
            created_at=now,
        )
        session.add(pick_revision)
        pick.player_id = None
        pick.recorded_at = None
        pick.client_entered_at = None
        if row.status == "completed":
            row.status = "active"
        row.completed_at = None
        row.updated_at = now
        if row.mode == "mock":
            from friendly_hub.domains.mocks.lifecycle_service import (
                record_mock_undo_in_transaction,
            )

            record_mock_undo_in_transaction(
                session,
                draft_row=row,
                pick=pick,
                pick_revision=pick_revision,
            )
        _commit(session)
    except Exception:
        session.rollback()
        raise
    return read_session(session, row.id)


def reset_session(
    session: Session,
    session_id: str,
    payload: DraftResetCreate,
) -> DraftSessionRead:
    row = _require_session(session, session_id)
    _require_revision(row, payload.revision)
    if row.status == "reset":
        raise _error(
            "DRAFT.ALREADY_RESET",
            "That draft session has already been reset.",
            "Open its linked replacement session.",
            409,
        )
    if payload.seed is not None and row.mode != "mock":
        raise _error(
            "DRAFT.SEED_NOT_APPLICABLE",
            "A replacement seed is available only for practice simulations.",
            "Remove the seed or reset a mock draft instead.",
            422,
        )
    board = get_board_row(session, row.board_id)
    if board is None:
        raise _error(
            "DRAFT.BOARD_NOT_FOUND",
            "The Personal Board for that draft is unavailable.",
            "Return to the board list and choose an available board.",
            404,
        )
    team_names = [team.display_name for team in _team_rows(session, row.id)]
    new_payload = DraftSessionCreate(
        name=row.name,
        mode=row.mode,
        league_profile_id=row.league_profile_id,
        draft_format=row.draft_format,
        third_round_reversal=row.third_round_reversal,
        team_count=row.team_count,
        round_count=row.round_count,
        user_slot=row.user_slot,
        pick_timer_seconds=row.pick_timer_seconds,
        team_names=team_names,
    )
    now = utc_now_text()
    try:
        _advance_revision(session, row, payload.revision)
        row.status = "reset"
        row.updated_at = now
        row.reset_at = now
        replacement = _create_session_rows(
            session,
            board,
            new_payload,
            reset_from_session_id=row.id,
        )
        if row.mode == "mock":
            from friendly_hub.domains.mocks.lifecycle_service import (
                reset_mock_in_transaction,
            )

            reset_mock_in_transaction(
                session,
                source_draft=row,
                replacement_draft=replacement,
                replacement_seed=payload.seed,
            )
        _commit(session)
    except Exception:
        session.rollback()
        raise
    return read_session(session, replacement.id)


def list_candidates(
    session: Session,
    session_id: str,
    *,
    view: DraftView,
    search: str | None,
    positions: list[str],
    include_drafted: bool,
    limit: int,
    offset: int,
) -> DraftCandidateListResponse:
    _require_session(session, session_id)
    rows = _candidate_rows(session, session_id)
    drafted = {
        pick.player_id: pick.overall_pick
        for pick in _pick_rows(session, session_id)
        if pick.player_id is not None
    }
    if search:
        tokens = [token.casefold() for token in search.split() if token]
        rows = [
            row
            for row in rows
            if all(token in row.search_name.casefold() for token in tokens)
        ]
    if positions:
        position_set = set(positions)
        rows = [row for row in rows if row.primary_position in position_set]
    if not include_drafted:
        rows = [row for row in rows if row.player_id not in drafted]
    if view == "tier":
        rows = [row for row in rows if row.snapshot_source == "personal_board"]
        rows.sort(
            key=lambda row: (
                row.tier_order is None,
                row.tier_order or 0,
                row.manual_rank is None,
                row.manual_rank or 0,
                row.search_name,
                row.primary_position,
                row.player_id,
            )
        )
    elif view in {"personal", "position"}:
        rows.sort(
            key=lambda row: (
                row.manual_rank is None,
                row.manual_rank or 0,
                row.search_name,
                row.primary_position,
                row.player_id,
            )
        )
    else:
        rows.sort(key=lambda row: (row.search_name, row.primary_position, row.player_id))
    total = len(rows)
    page = rows[offset : offset + limit]
    if view == "blind":
        items = [
            DraftBlindCandidateRead(
                player_id=row.player_id,
                display_name=row.display_name,
                primary_position=row.primary_position,
                fantasy_positions=json.loads(row.fantasy_positions_json),
                team=row.team,
                player_status=row.player_status,
                is_rookie=row.is_rookie,
                rookie_class=row.rookie_class,
                drafted_overall_pick=drafted.get(row.player_id),
            )
            for row in page
        ]
    else:
        items = [
            DraftContextCandidateRead(
                player_id=row.player_id,
                display_name=row.display_name,
                primary_position=row.primary_position,
                fantasy_positions=json.loads(row.fantasy_positions_json),
                team=row.team,
                player_status=row.player_status,
                is_rookie=row.is_rookie,
                rookie_class=row.rookie_class,
                drafted_overall_pick=drafted.get(row.player_id),
                snapshot_source=row.snapshot_source,
                personal_rank=row.manual_rank,
                tier_name=row.tier_name,
                tier_color=row.tier_color,
                favorite=row.favorite,
                board_note=row.board_note,
            )
            for row in page
        ]
    response_values = {
        "view": view,
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
    if view == "blind":
        return DraftBlindCandidateListResponse(**response_values)
    return DraftContextCandidateListResponse(**response_values)


def export_session_csv(session: Session, session_id: str) -> str:
    row = _require_session(session, session_id)
    teams = {team.draft_slot: team for team in _team_rows(session, row.id)}
    candidates = {
        candidate.player_id: candidate
        for candidate in _candidate_rows(session, row.id)
    }
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "session_name",
            "mode",
            "format",
            "third_round_reversal",
            "overall_pick",
            "round",
            "pick_in_round",
            "selecting_slot",
            "selecting_team",
            "player_display_name",
            "player_position",
            "player_team",
            "pick_recorded_at",
            "correction_count",
        ]
    )

    def safe_text(value: str | None) -> str:
        text = value or ""
        return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text

    for pick in _pick_rows(session, row.id):
        if pick.player_id is None:
            continue
        candidate = candidates[pick.player_id]
        writer.writerow(
            [
                safe_text(row.name),
                row.mode,
                row.draft_format,
                str(row.third_round_reversal).lower(),
                pick.overall_pick,
                pick.round_number,
                pick.pick_in_round,
                pick.selecting_slot,
                safe_text(teams[pick.selecting_slot].display_name),
                safe_text(candidate.display_name),
                candidate.primary_position,
                safe_text(candidate.team),
                pick.recorded_at,
                pick.correction_count,
            ]
        )
    return output.getvalue()
