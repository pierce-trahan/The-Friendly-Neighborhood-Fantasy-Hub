from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from friendly_hub.db.engine import get_session
from friendly_hub.domains.mocks.history_service import (
    list_mock_history,
    update_learning_consent,
)
from friendly_hub.domains.mocks.schemas import (
    MockCpuPickCreate,
    MockGuidanceListResponse,
    MockGuidanceStatusPatch,
    MockHistoryListResponse,
    MockLearningPatch,
    MockPickDecisionAudit,
    MockSessionCreate,
    MockSessionRead,
    MockStrategyPivotCreate,
)
from friendly_hub.domains.mocks.service import (
    advance_cpu_pick,
    create_mock_session,
    read_mock_decision,
    read_mock_session,
)
from friendly_hub.domains.mocks.strategy_service import (
    list_guidance,
    pivot_strategy,
    update_guidance_status,
)

router = APIRouter(tags=["mocks"])
SessionDependency = Annotated[Session, Depends(get_session)]


@router.post(
    "/boards/{board_id}/mock-sessions",
    response_model=MockSessionRead,
    status_code=201,
)
def create_board_mock_session(
    board_id: str,
    payload: MockSessionCreate,
    session: SessionDependency,
) -> MockSessionRead:
    return create_mock_session(session, board_id, payload)


@router.get(
    "/boards/{board_id}/mock-sessions",
    response_model=MockHistoryListResponse,
)
def list_board_mock_sessions(
    board_id: str,
    session: SessionDependency,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> MockHistoryListResponse:
    return list_mock_history(
        session,
        board_id,
        limit=limit,
        offset=offset,
    )


@router.get("/mock-sessions/{session_id}", response_model=MockSessionRead)
def get_mock_session(
    session_id: str,
    session: SessionDependency,
) -> MockSessionRead:
    return read_mock_session(session, session_id)


@router.post(
    "/mock-sessions/{session_id}/cpu-pick",
    response_model=MockSessionRead,
)
def create_cpu_pick(
    session_id: str,
    payload: MockCpuPickCreate,
    session: SessionDependency,
) -> MockSessionRead:
    return advance_cpu_pick(session, session_id, payload)


@router.get(
    "/mock-sessions/{session_id}/decisions/{overall_pick}",
    response_model=MockPickDecisionAudit,
)
def get_cpu_decision(
    session_id: str,
    overall_pick: Annotated[int, Path(ge=1)],
    session: SessionDependency,
) -> MockPickDecisionAudit:
    return read_mock_decision(session, session_id, overall_pick)


@router.patch(
    "/mock-sessions/{session_id}/strategy",
    response_model=MockSessionRead,
)
def update_mock_strategy(
    session_id: str,
    payload: MockStrategyPivotCreate,
    session: SessionDependency,
) -> MockSessionRead:
    return pivot_strategy(session, session_id, payload)


@router.get(
    "/mock-sessions/{session_id}/guidance",
    response_model=MockGuidanceListResponse,
)
def get_mock_guidance(
    session_id: str,
    session: SessionDependency,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> MockGuidanceListResponse:
    return list_guidance(
        session,
        session_id,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/mock-sessions/{session_id}/guidance/{event_id}",
    response_model=MockSessionRead,
)
def update_mock_guidance(
    session_id: str,
    event_id: str,
    payload: MockGuidanceStatusPatch,
    session: SessionDependency,
) -> MockSessionRead:
    return update_guidance_status(session, session_id, event_id, payload)


@router.patch(
    "/mock-sessions/{session_id}/learning",
    response_model=MockSessionRead,
)
def update_mock_learning(
    session_id: str,
    payload: MockLearningPatch,
    session: SessionDependency,
) -> MockSessionRead:
    return update_learning_consent(session, session_id, payload)
