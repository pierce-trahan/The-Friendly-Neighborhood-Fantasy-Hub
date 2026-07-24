from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from friendly_hub.db.engine import get_session
from friendly_hub.domains.players.schemas import (
    CsvPreviewRequest,
    MappingDecisionRequest,
    PlayerImportCommitResponse,
    PlayerImportSessionRead,
    PlayerListResponse,
    PlayerPatch,
    PlayerPosition,
    PlayerRead,
    PlayerStatus,
)
from friendly_hub.domains.players.service import (
    cancel_import,
    commit_import,
    decide_import_row,
    export_players_csv,
    patch_player,
    preview_csv,
    preview_sanitized_fixture,
    query_players,
    read_import_session,
    read_player,
)

router = APIRouter(tags=["players"])
SessionDependency = Annotated[Session, Depends(get_session)]


@router.get("/players", response_model=PlayerListResponse)
def list_canonical_players(
    session: SessionDependency,
    search: str | None = None,
    position: PlayerPosition | None = None,
    status: PlayerStatus | None = None,
    rookie_class: int | None = Query(default=None, ge=1900, le=2200),
    relevant_only: bool = True,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> PlayerListResponse:
    return query_players(
        session,
        search=search,
        position=position,
        status=status,
        rookie_class=rookie_class,
        relevant_only=relevant_only,
        limit=limit,
        offset=offset,
    )


@router.get("/players/export.csv")
def download_players_csv(session: SessionDependency) -> Response:
    return Response(
        export_players_csv(session),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="friendly-hub-players.csv"'},
    )


@router.get("/players/{player_id}", response_model=PlayerRead)
def get_canonical_player(player_id: str, session: SessionDependency) -> PlayerRead:
    return read_player(session, player_id)


@router.patch("/players/{player_id}", response_model=PlayerRead)
def update_canonical_player(
    player_id: str,
    patch: PlayerPatch,
    session: SessionDependency,
) -> PlayerRead:
    return patch_player(session, player_id, patch)


@router.post(
    "/player-imports/fixture/preview",
    response_model=PlayerImportSessionRead,
    status_code=201,
)
def preview_fixture(
    request: Request,
    session: SessionDependency,
) -> PlayerImportSessionRead:
    return preview_sanitized_fixture(
        session,
        request.app.state.runtime.player_fixture_path,
    )


@router.post(
    "/player-imports/csv/preview",
    response_model=PlayerImportSessionRead,
    status_code=201,
)
def preview_player_csv(
    preview: CsvPreviewRequest,
    session: SessionDependency,
) -> PlayerImportSessionRead:
    return preview_csv(
        session,
        filename=preview.filename,
        csv_text=preview.csv_text,
    )


@router.get(
    "/player-imports/{session_id}",
    response_model=PlayerImportSessionRead,
)
def get_player_import(
    session_id: str,
    session: SessionDependency,
) -> PlayerImportSessionRead:
    return read_import_session(session, session_id)


@router.put(
    "/player-imports/{session_id}/rows/{row_id}/decision",
    response_model=PlayerImportSessionRead,
)
def save_player_import_decision(
    session_id: str,
    row_id: str,
    decision: MappingDecisionRequest,
    session: SessionDependency,
) -> PlayerImportSessionRead:
    return decide_import_row(session, session_id, row_id, decision)


@router.post(
    "/player-imports/{session_id}/commit",
    response_model=PlayerImportCommitResponse,
)
def commit_player_import(
    session_id: str,
    session: SessionDependency,
) -> PlayerImportCommitResponse:
    return commit_import(session, session_id)


@router.post(
    "/player-imports/{session_id}/cancel",
    response_model=PlayerImportSessionRead,
)
def cancel_player_import(
    session_id: str,
    session: SessionDependency,
) -> PlayerImportSessionRead:
    return cancel_import(session, session_id)
