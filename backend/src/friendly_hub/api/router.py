from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from friendly_hub import __version__
from friendly_hub.api.security import require_local_write_guard
from friendly_hub.db.engine import get_session
from friendly_hub.domains.boards.router import router as boards_router
from friendly_hub.domains.configuration.router import router as configuration_router
from friendly_hub.domains.drafts.router import router as drafts_router
from friendly_hub.domains.gut_elo.router import router as gut_elo_router
from friendly_hub.domains.leagues.router import router as league_profiles_router
from friendly_hub.domains.mocks.router import router as mocks_router
from friendly_hub.domains.players.router import router as players_router

router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_local_write_guard)],
)
SessionDependency = Annotated[Session, Depends(get_session)]


class HealthResponse(BaseModel):
    status: str
    app_version: str
    database_schema_version: str


@router.get("/health", tags=["system"], response_model=HealthResponse)
def health(session: SessionDependency) -> HealthResponse:
    session.execute(text("SELECT 1"))
    schema_version = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    return HealthResponse(
        status="ok",
        app_version=__version__,
        database_schema_version=schema_version,
    )


router.include_router(configuration_router)
router.include_router(league_profiles_router)
router.include_router(players_router)
router.include_router(boards_router)
router.include_router(gut_elo_router)
router.include_router(drafts_router)
router.include_router(mocks_router)
