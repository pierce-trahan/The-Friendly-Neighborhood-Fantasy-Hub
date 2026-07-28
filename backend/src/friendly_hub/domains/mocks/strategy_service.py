from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.drafts.models import DraftPickRow
from friendly_hub.domains.drafts.service import DraftPickMutation
from friendly_hub.domains.mocks.definitions import (
    STRATEGY_DEFINITION_VERSION,
)
from friendly_hub.domains.mocks.models import (
    MockConfigurationRow,
    MockGuidanceEventRow,
    MockStrategyRevisionRow,
)
from friendly_hub.domains.mocks.schemas import (
    MockGuidanceListResponse,
    MockGuidanceStatusPatch,
    MockSessionRead,
    MockStrategyPivotCreate,
)
from friendly_hub.domains.mocks.service import (
    _error,
    _guidance_read,
    _json,
    _require_cpu_mock,
    _user_roster,
    _validate_strategy_compatibility,
    read_mock_session,
)
from friendly_hub.domains.mocks.strategy import (
    StrategyEvaluation,
    evaluate_strategy,
    user_roster_counts,
)


def _latest_strategy_revision(
    session: Session,
    configuration_id: str,
) -> MockStrategyRevisionRow:
    row = session.scalar(
        select(MockStrategyRevisionRow)
        .where(MockStrategyRevisionRow.mock_configuration_id == configuration_id)
        .order_by(MockStrategyRevisionRow.sequence_number.desc())
        .limit(1)
    )
    if row is None:
        raise _error(
            "MOCK.STRATEGY_NOT_FOUND",
            "The mock is missing its current strategy revision.",
            "Keep the session for audit and create a fresh mock.",
            404,
        )
    return row


def _add_guidance_event(
    session: Session,
    *,
    configuration: MockConfigurationRow,
    strategy_revision: MockStrategyRevisionRow,
    effective_overall_pick: int,
    evaluation: StrategyEvaluation,
    event_kind: str,
    now: str,
) -> MockGuidanceEventRow:
    event_key = (
        f"{configuration.strategy_definition_version}:"
        f"{strategy_revision.sequence_number}:{effective_overall_pick}:{event_kind}"
    )
    existing = session.scalar(
        select(MockGuidanceEventRow).where(
            MockGuidanceEventRow.mock_configuration_id == configuration.id,
            MockGuidanceEventRow.deterministic_event_key == event_key,
        )
    )
    if existing is not None:
        return existing
    row = MockGuidanceEventRow(
        id=str(uuid4()),
        mock_configuration_id=configuration.id,
        strategy_revision_id=strategy_revision.id,
        deterministic_event_key=event_key,
        effective_overall_pick=effective_overall_pick,
        state=evaluation.state,
        confidence=evaluation.confidence,
        observed_counts_json=_json(evaluation.observed_counts),
        target_ranges_json=_json(evaluation.target_ranges),
        reason_codes_json=_json(evaluation.reason_codes),
        limitation_codes_json=_json(evaluation.limitation_codes),
        explanation_template_key=evaluation.explanation_template_key,
        pivot_template_key=evaluation.pivot_template_key,
        status="open",
        created_at=now,
        resolved_at=None,
    )
    session.add(row)
    return row


def _update_mock_strategy(
    session: Session,
    configuration: MockConfigurationRow,
    *,
    expected_revision: int,
    strategy_key: str | None,
    now: str,
) -> None:
    values: dict[str, object] = {
        "revision": expected_revision + 1,
        "updated_at": now,
    }
    if strategy_key is not None:
        values["current_strategy_key"] = strategy_key
    result = session.execute(
        update(MockConfigurationRow)
        .where(
            MockConfigurationRow.id == configuration.id,
            MockConfigurationRow.revision == expected_revision,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        session.rollback()
        raise _error(
            "MOCK.STALE_REVISION",
            "The mock changed before that strategy action could be saved.",
            "Refresh the practice room and retry from its current state.",
            409,
        )
    session.refresh(configuration)


def _current_pick(
    session: Session,
    session_id: str,
) -> DraftPickRow | None:
    return session.scalar(
        select(DraftPickRow)
        .where(
            DraftPickRow.session_id == session_id,
            DraftPickRow.player_id.is_(None),
        )
        .order_by(DraftPickRow.overall_pick)
        .limit(1)
    )


def pivot_strategy(
    session: Session,
    session_id: str,
    payload: MockStrategyPivotCreate,
) -> MockSessionRead:
    draft_row, configuration = _require_cpu_mock(session, session_id)
    if draft_row.status not in {"active", "paused"}:
        raise _error(
            "MOCK.STRATEGY_LOCKED",
            "A completed or reset mock cannot change strategy.",
            "Review the saved strategy history or create a new mock.",
            409,
        )
    if configuration.revision != payload.mock_revision:
        raise _error(
            "MOCK.STALE_REVISION",
            "The mock changed before that strategy pivot could be saved.",
            "Refresh the practice room and retry from its current state.",
            409,
        )
    if configuration.strategy_definition_version != STRATEGY_DEFINITION_VERSION:
        raise _error(
            "MOCK.STRATEGY_VERSION_UNSUPPORTED",
            "This mock uses an unsupported strategy-definition version.",
            "Keep it for audit and create a new mock with the current guide.",
            409,
        )
    current = _current_pick(session, session_id)
    if current is None:
        raise _error(
            "MOCK.COMPLETE",
            "A completed mock cannot change strategy.",
            "Review the saved strategy history or create a new mock.",
            409,
        )
    if current.overall_pick != payload.expected_current_overall_pick:
        raise _error(
            "MOCK.STALE_CURRENT_PICK",
            "The mock advanced before that strategy pivot could be saved.",
            "Refresh the practice room and verify the current overall pick.",
            409,
        )
    if payload.strategy_key == configuration.current_strategy_key:
        raise _error(
            "MOCK.STRATEGY_UNCHANGED",
            "The mock already uses that strategy guide.",
            "Choose a different guide or keep the current strategy.",
            409,
        )
    league_shape = json.loads(configuration.league_shape_json)
    _validate_strategy_compatibility(payload.strategy_key, league_shape)
    previous = _latest_strategy_revision(session, configuration.id)
    roster = _user_roster(session, draft_row)
    counts = user_roster_counts(roster)
    now = utc_now_text()
    try:
        revision = MockStrategyRevisionRow(
            id=str(uuid4()),
            mock_configuration_id=configuration.id,
            sequence_number=previous.sequence_number + 1,
            previous_strategy_key=configuration.current_strategy_key,
            next_strategy_key=payload.strategy_key,
            effective_overall_pick=current.overall_pick,
            user_roster_counts_json=_json(counts),
            private_user_note=payload.private_user_note,
            created_at=now,
        )
        session.add(revision)
        session.flush()
        evaluation = evaluate_strategy(
            strategy_key=payload.strategy_key,
            round_count=draft_row.round_count,
            team_count=draft_row.team_count,
            effective_overall_pick=current.overall_pick,
            roster=roster,
            league_shape=league_shape,
        )
        _add_guidance_event(
            session,
            configuration=configuration,
            strategy_revision=revision,
            effective_overall_pick=current.overall_pick,
            evaluation=evaluation,
            event_kind="user-pivot",
            now=now,
        )
        _update_mock_strategy(
            session,
            configuration,
            expected_revision=payload.mock_revision,
            strategy_key=payload.strategy_key,
            now=now,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return read_mock_session(session, session_id)


def record_guidance_after_user_pick_in_transaction(
    session: Session,
    mutation: DraftPickMutation,
) -> None:
    draft_row = mutation.draft_session
    if (
        draft_row.mode != "mock"
        or mutation.pick.selecting_slot != draft_row.user_slot
    ):
        return
    configuration = session.scalar(
        select(MockConfigurationRow).where(
            MockConfigurationRow.draft_session_id == draft_row.id
        )
    )
    if configuration is None:
        return
    strategy_revision = _latest_strategy_revision(session, configuration.id)
    current = _current_pick(session, draft_row.id)
    effective_pick = (
        current.overall_pick if current is not None else mutation.pick.overall_pick
    )
    roster = _user_roster(session, draft_row)
    league_shape = json.loads(configuration.league_shape_json)
    evaluation = evaluate_strategy(
        strategy_key=configuration.current_strategy_key,
        round_count=draft_row.round_count,
        team_count=draft_row.team_count,
        effective_overall_pick=effective_pick,
        roster=roster,
        league_shape=league_shape,
    )
    now = utc_now_text()
    _add_guidance_event(
        session,
        configuration=configuration,
        strategy_revision=strategy_revision,
        effective_overall_pick=effective_pick,
        evaluation=evaluation,
        event_kind=(
            f"user-pick-revision-{mutation.pick_revision.session_revision}"
        ),
        now=now,
    )
    _update_mock_strategy(
        session,
        configuration,
        expected_revision=configuration.revision,
        strategy_key=None,
        now=now,
    )


def list_guidance(
    session: Session,
    session_id: str,
    *,
    limit: int,
    offset: int,
) -> MockGuidanceListResponse:
    _, configuration = _require_cpu_mock(session, session_id)
    total = (
        session.scalar(
            select(func.count())
            .select_from(MockGuidanceEventRow)
            .where(
                MockGuidanceEventRow.mock_configuration_id == configuration.id
            )
        )
        or 0
    )
    rows = list(
        session.scalars(
            select(MockGuidanceEventRow)
            .where(MockGuidanceEventRow.mock_configuration_id == configuration.id)
            .order_by(
                MockGuidanceEventRow.created_at.desc(),
                MockGuidanceEventRow.id.desc(),
                MockGuidanceEventRow.effective_overall_pick.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    )
    revision_ids = {row.strategy_revision_id for row in rows}
    revisions = {
        row.id: row
        for row in session.scalars(
            select(MockStrategyRevisionRow).where(
                MockStrategyRevisionRow.id.in_(revision_ids)
            )
        )
    }
    return MockGuidanceListResponse(
        items=[
            _guidance_read(
                row,
                revisions[row.strategy_revision_id],
                configuration.strategy_definition_version,
            )
            for row in rows
            if row.strategy_revision_id in revisions
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


def update_guidance_status(
    session: Session,
    session_id: str,
    event_id: str,
    payload: MockGuidanceStatusPatch,
) -> MockSessionRead:
    _, configuration = _require_cpu_mock(session, session_id)
    if configuration.revision != payload.mock_revision:
        raise _error(
            "MOCK.STALE_REVISION",
            "The mock changed before that guidance action could be saved.",
            "Refresh the practice room and retry from its current state.",
            409,
        )
    row = session.scalar(
        select(MockGuidanceEventRow).where(
            MockGuidanceEventRow.id == event_id,
            MockGuidanceEventRow.mock_configuration_id == configuration.id,
        )
    )
    if row is None:
        raise _error(
            "MOCK.GUIDANCE_NOT_FOUND",
            "That guidance event could not be found.",
            "Refresh the strategy guide and choose an available event.",
            404,
        )
    if row.status == payload.status:
        raise _error(
            "MOCK.GUIDANCE_STATUS_UNCHANGED",
            "That guidance event already has the requested status.",
            "Keep its current status or choose a different action.",
            409,
        )
    now = utc_now_text()
    row.status = payload.status
    row.resolved_at = None if payload.status == "open" else now
    try:
        _update_mock_strategy(
            session,
            configuration,
            expected_revision=payload.mock_revision,
            strategy_key=None,
            now=now,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return read_mock_session(session, session_id)
