from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from friendly_hub.db.engine import get_session
from friendly_hub.domains.mocks.schemas import (
    MockCpuPickCreate,
    MockPickDecisionAudit,
    MockSessionCreate,
    MockSessionRead,
)
from friendly_hub.domains.mocks.service import (
    advance_cpu_pick,
    create_mock_session,
    read_mock_decision,
    read_mock_session,
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
