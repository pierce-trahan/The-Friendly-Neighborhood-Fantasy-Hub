from __future__ import annotations

from sqlalchemy.orm import Session

from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.configuration.models import AppConfigurationRow
from friendly_hub.domains.configuration.schemas import AppConfiguration

CONFIGURATION_ROW_ID = 1


def get_configuration(session: Session) -> AppConfiguration | None:
    row = session.get(AppConfigurationRow, CONFIGURATION_ROW_ID)
    if row is None:
        return None
    return AppConfiguration.model_validate_json(row.payload_json)


def save_configuration(session: Session, configuration: AppConfiguration) -> None:
    row = session.get(AppConfigurationRow, CONFIGURATION_ROW_ID)
    payload_json = configuration.model_dump_json()
    if row is None:
        row = AppConfigurationRow(
            id=CONFIGURATION_ROW_ID,
            payload_json=payload_json,
            updated_at=utc_now_text(),
        )
        session.add(row)
    else:
        row.payload_json = payload_json
        row.updated_at = utc_now_text()
