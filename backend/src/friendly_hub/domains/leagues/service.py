from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from friendly_hub.core.errors import HubError
from friendly_hub.domains.leagues.repository import upsert_profile
from friendly_hub.domains.leagues.schemas import (
    LeagueProfileDocument,
    LeagueProfileSummary,
)


def load_sanitized_sample(session: Session, fixture_path: Path) -> LeagueProfileSummary:
    if not fixture_path.is_file():
        raise HubError(
            code="IMPORT.SAMPLE.NOT_FOUND",
            message="The offline Entropy sample could not be found.",
            action="Reinstall the application files, then try loading the sample again.",
            status_code=500,
        )

    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        document = LeagueProfileDocument.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HubError(
            code="IMPORT.SAMPLE.INVALID",
            message="The offline Entropy sample is not valid.",
            action="The sample was not imported. Reinstall the application files before retrying.",
            status_code=500,
        ) from exc

    if not document.provenance.sanitized:
        raise HubError(
            code="IMPORT.SAMPLE.NOT_SANITIZED",
            message="The sample is not marked as safe demonstration data.",
            action="The sample was not imported. Use a deliberately sanitized fixture.",
            status_code=422,
        )

    try:
        row = upsert_profile(session, document)
        session.commit()
    except Exception:
        session.rollback()
        raise

    return LeagueProfileSummary(
        id=row.id,
        profile_id=row.profile_key,
        name=row.name,
        season=row.season,
        league_type=document.league.league_type,
        team_count=document.league.team_count,
        sanitized=document.provenance.sanitized,
        imported_at=row.imported_at,
        source_as_of=document.provenance.source_as_of,
    )
