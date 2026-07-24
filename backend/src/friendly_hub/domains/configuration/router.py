from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from friendly_hub.db.engine import get_session
from friendly_hub.domains.configuration.repository import get_configuration
from friendly_hub.domains.configuration.schemas import AppConfiguration
from friendly_hub.domains.configuration.service import (
    ensure_default_configuration,
    update_configuration,
)

router = APIRouter(prefix="/config", tags=["configuration"])
SessionDependency = Annotated[Session, Depends(get_session)]


@router.get("", response_model=AppConfiguration)
def read_configuration(session: SessionDependency) -> AppConfiguration:
    return get_configuration(session) or ensure_default_configuration(session)


@router.put("", response_model=AppConfiguration)
def write_configuration(
    configuration: AppConfiguration,
    session: SessionDependency,
) -> AppConfiguration:
    return update_configuration(session, configuration)
