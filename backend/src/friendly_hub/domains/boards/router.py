from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from friendly_hub.db.engine import get_session
from friendly_hub.domains.boards.schemas import (
    BoardCreate,
    BoardEntryCreate,
    BoardEntryPatch,
    BoardListResponse,
    BoardOrderUpdate,
    BoardPatch,
    BoardRead,
    BoardTierCreate,
    BoardTierPatch,
)
from friendly_hub.domains.boards.service import (
    add_board_entry,
    add_tier,
    create_board,
    export_board_csv,
    list_boards,
    patch_board,
    patch_board_entry,
    patch_tier,
    read_board,
    remove_board_entry,
    remove_tier,
    reorder_board,
)

router = APIRouter(tags=["boards"])
SessionDependency = Annotated[Session, Depends(get_session)]


@router.get("/boards", response_model=BoardListResponse)
def list_personal_boards(
    session: SessionDependency,
    include_archived: bool = False,
) -> BoardListResponse:
    return list_boards(session, include_archived=include_archived)


@router.post("/boards", response_model=BoardRead, status_code=201)
def create_personal_board(
    payload: BoardCreate,
    session: SessionDependency,
) -> BoardRead:
    return create_board(session, payload)


@router.get("/boards/{board_id}", response_model=BoardRead)
def get_personal_board(board_id: str, session: SessionDependency) -> BoardRead:
    return read_board(session, board_id)


@router.patch("/boards/{board_id}", response_model=BoardRead)
def update_personal_board(
    board_id: str,
    payload: BoardPatch,
    session: SessionDependency,
) -> BoardRead:
    return patch_board(session, board_id, payload)


@router.get("/boards/{board_id}/export.csv")
def download_personal_board(board_id: str, session: SessionDependency) -> Response:
    return Response(
        export_board_csv(session, board_id),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="friendly-hub-board.csv"'
        },
    )


@router.post("/boards/{board_id}/tiers", response_model=BoardRead)
def create_board_tier(
    board_id: str,
    payload: BoardTierCreate,
    session: SessionDependency,
) -> BoardRead:
    return add_tier(session, board_id, payload)


@router.patch("/boards/{board_id}/tiers/{tier_id}", response_model=BoardRead)
def update_board_tier(
    board_id: str,
    tier_id: str,
    payload: BoardTierPatch,
    session: SessionDependency,
) -> BoardRead:
    return patch_tier(session, board_id, tier_id, payload)


@router.delete("/boards/{board_id}/tiers/{tier_id}", response_model=BoardRead)
def delete_board_tier(
    board_id: str,
    tier_id: str,
    session: SessionDependency,
) -> BoardRead:
    return remove_tier(session, board_id, tier_id)


@router.post("/boards/{board_id}/entries", response_model=BoardRead)
def create_board_entry(
    board_id: str,
    payload: BoardEntryCreate,
    session: SessionDependency,
) -> BoardRead:
    return add_board_entry(session, board_id, payload)


@router.patch("/boards/{board_id}/entries/{entry_id}", response_model=BoardRead)
def update_board_entry(
    board_id: str,
    entry_id: str,
    payload: BoardEntryPatch,
    session: SessionDependency,
) -> BoardRead:
    return patch_board_entry(session, board_id, entry_id, payload)


@router.delete("/boards/{board_id}/entries/{entry_id}", response_model=BoardRead)
def delete_board_entry(
    board_id: str,
    entry_id: str,
    session: SessionDependency,
) -> BoardRead:
    return remove_board_entry(session, board_id, entry_id)


@router.put("/boards/{board_id}/order", response_model=BoardRead)
def save_board_order(
    board_id: str,
    payload: BoardOrderUpdate,
    session: SessionDependency,
) -> BoardRead:
    return reorder_board(session, board_id, payload)
