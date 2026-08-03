from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.leagues.models import LeagueProfileRow
from friendly_hub.domains.leagues.schemas import (
    LeagueProfileDocument,
    LeagueProfileSummary,
)


def upsert_profile(
    session: Session,
    document: LeagueProfileDocument,
) -> LeagueProfileRow:
    row = session.scalar(
        select(LeagueProfileRow).where(LeagueProfileRow.profile_key == document.profile_id)
    )
    if row is None:
        row = LeagueProfileRow(
            id=str(uuid4()),
            profile_key=document.profile_id,
            name=document.league.name,
            season=document.league.season,
            payload_json=document.model_dump_json(),
            imported_at=utc_now_text(),
        )
        session.add(row)
    else:
        row.name = document.league.name
        row.season = document.league.season
        row.payload_json = document.model_dump_json()
        row.imported_at = utc_now_text()
    return row


def list_profiles(session: Session) -> list[LeagueProfileSummary]:
    rows = session.scalars(
        select(LeagueProfileRow).order_by(LeagueProfileRow.season.desc(), LeagueProfileRow.name)
    )
    summaries: list[LeagueProfileSummary] = []
    for row in rows:
        document = LeagueProfileDocument.model_validate_json(row.payload_json)
        summaries.append(
            LeagueProfileSummary(
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
        )
    return summaries
