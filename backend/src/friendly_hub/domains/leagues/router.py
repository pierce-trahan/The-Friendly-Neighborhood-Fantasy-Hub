from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from friendly_hub.db.engine import get_session
from friendly_hub.domains.leagues.repository import list_profiles
from friendly_hub.domains.leagues.schemas import LeagueProfileSummary
from friendly_hub.domains.leagues.service import load_sanitized_sample

router = APIRouter(prefix="/league-profiles", tags=["league profiles"])
SessionDependency = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[LeagueProfileSummary])
def read_profiles(session: SessionDependency) -> list[LeagueProfileSummary]:
    return list_profiles(session)


@router.post(
    "/samples/entropy",
    response_model=LeagueProfileSummary,
    status_code=201,
)
def import_entropy_sample(
    request: Request,
    session: SessionDependency,
) -> LeagueProfileSummary:
    return load_sanitized_sample(session, request.app.state.runtime.sample_fixture_path)
