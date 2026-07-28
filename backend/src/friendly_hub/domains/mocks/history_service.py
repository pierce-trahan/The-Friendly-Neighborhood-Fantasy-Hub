from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.boards.repository import get_board_row
from friendly_hub.domains.drafts.models import DraftSessionRow
from friendly_hub.domains.mocks.models import (
    MockConfigurationRow,
    MockStrategyRevisionRow,
)
from friendly_hub.domains.mocks.schemas import (
    MockHistoryListResponse,
    MockHistorySummaryRead,
    MockLearningPatch,
    MockSessionRead,
)
from friendly_hub.domains.mocks.service import (
    _error,
    _require_cpu_mock,
    read_mock_session,
)
from friendly_hub.domains.mocks.strategy_service import _update_mock_strategy


def update_learning_consent(
    session: Session,
    session_id: str,
    payload: MockLearningPatch,
) -> MockSessionRead:
    _, configuration = _require_cpu_mock(session, session_id)
    if configuration.revision != payload.mock_revision:
        raise _error(
            "MOCK.STALE_REVISION",
            "The mock changed before that learning choice could be saved.",
            "Refresh the practice history and retry from its current state.",
            409,
        )
    if configuration.include_in_learning == payload.include_in_learning:
        raise _error(
            "MOCK.LEARNING_UNCHANGED",
            "That mock already has the requested learning setting.",
            "Keep its current setting or choose the other option.",
            409,
        )

    now = utc_now_text()
    try:
        configuration.include_in_learning = payload.include_in_learning
        if payload.include_in_learning:
            configuration.learning_opted_in_at = now
        else:
            configuration.learning_withdrawn_at = now
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


def _completion_state(status: str) -> str:
    if status == "completed":
        return "completed"
    if status == "reset":
        return "reset"
    return "incomplete"


def list_mock_history(
    session: Session,
    board_id: str,
    *,
    limit: int,
    offset: int,
) -> MockHistoryListResponse:
    if get_board_row(session, board_id) is None:
        raise _error(
            "MOCK.BOARD_NOT_FOUND",
            "That Personal Board could not be found.",
            "Return to the board list and choose an available board.",
            404,
        )

    board_filter = (
        DraftSessionRow.board_id == board_id,
        DraftSessionRow.mode == "mock",
    )
    total = (
        session.scalar(
            select(func.count())
            .select_from(MockConfigurationRow)
            .join(
                DraftSessionRow,
                DraftSessionRow.id
                == MockConfigurationRow.draft_session_id,
            )
            .where(*board_filter)
        )
        or 0
    )
    rows = list(
        session.execute(
            select(DraftSessionRow, MockConfigurationRow)
            .join(
                MockConfigurationRow,
                MockConfigurationRow.draft_session_id
                == DraftSessionRow.id,
            )
            .where(*board_filter)
            .order_by(
                DraftSessionRow.created_at.desc(),
                DraftSessionRow.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    )
    configuration_ids = [configuration.id for _, configuration in rows]
    revision_counts: dict[str, int] = {}
    if configuration_ids:
        revision_counts = {
            configuration_id: count
            for configuration_id, count in session.execute(
                select(
                    MockStrategyRevisionRow.mock_configuration_id,
                    func.count(),
                )
                .where(
                    MockStrategyRevisionRow.mock_configuration_id.in_(
                        configuration_ids
                    )
                )
                .group_by(MockStrategyRevisionRow.mock_configuration_id)
            )
        }

    return MockHistoryListResponse(
        items=[
            MockHistorySummaryRead(
                session_id=draft.id,
                name=draft.name,
                status=draft.status,
                completion_state=_completion_state(draft.status),
                seed=configuration.seed,
                randomness=configuration.randomness,
                current_strategy_key=configuration.current_strategy_key,
                pivot_count=max(
                    revision_counts.get(configuration.id, 1) - 1,
                    0,
                ),
                mock_revision=configuration.revision,
                draft_format=draft.draft_format,
                third_round_reversal=draft.third_round_reversal,
                team_count=draft.team_count,
                round_count=draft.round_count,
                user_slot=draft.user_slot,
                include_in_learning=configuration.include_in_learning,
                learning_opted_in_at=configuration.learning_opted_in_at,
                learning_withdrawn_at=(
                    configuration.learning_withdrawn_at
                ),
                rng_version=configuration.rng_version,
                cpu_engine_version=configuration.cpu_engine_version,
                strategy_definition_version=(
                    configuration.strategy_definition_version
                ),
                created_at=draft.created_at,
                updated_at=max(
                    draft.updated_at,
                    configuration.updated_at,
                ),
                completed_at=draft.completed_at,
                reset_at=draft.reset_at,
            )
            for draft, configuration in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
