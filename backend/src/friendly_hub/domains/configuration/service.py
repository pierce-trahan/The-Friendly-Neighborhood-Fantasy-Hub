from sqlalchemy.orm import Session

from friendly_hub.domains.configuration.repository import (
    get_configuration,
    save_configuration,
)
from friendly_hub.domains.configuration.schemas import AppConfiguration, default_configuration


def ensure_default_configuration(session: Session) -> AppConfiguration:
    configuration = get_configuration(session)
    if configuration is not None:
        return configuration

    configuration = default_configuration()
    save_configuration(session, configuration)
    session.commit()
    return configuration


def update_configuration(
    session: Session,
    configuration: AppConfiguration,
) -> AppConfiguration:
    try:
        save_configuration(session, configuration)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return configuration
