from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.drafts.engine import build_draft_order, picks_until_slot
from friendly_hub.domains.drafts.models import DraftPickRevisionRow
from friendly_hub.domains.players.models import PlayerRow
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}
PRIVATE_CANDIDATE_KEYS = {
    "personal_rank",
    "tier_name",
    "tier_color",
    "favorite",
    "board_note",
    "gut_elo",
    "provider",
    "adp",
    "market_value",
}


def _seed_players(client: TestClient) -> list[dict[str, object]]:
    preview = client.post("/api/v1/player-imports/fixture/preview")
    assert preview.status_code == 201
    committed = client.post(
        f"/api/v1/player-imports/{preview.json()['id']}/commit"
    )
    assert committed.status_code == 200
    response = client.get("/api/v1/players", params={"limit": 100})
    assert response.status_code == 200
    return response.json()["items"]


def _board(
    client: TestClient,
    *,
    board_player_count: int = 3,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    players = _seed_players(client)
    response = client.post(
        "/api/v1/boards",
        json={"name": "Draft Board", "scope": "overall"},
    )
    assert response.status_code == 201
    board = response.json()
    for player in players[:board_player_count]:
        response = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": player["id"]},
        )
        assert response.status_code == 200
        board = response.json()
    return board, players


def _start(
    client: TestClient,
    board_id: str,
    **overrides: object,
) -> dict[str, object]:
    payload = {
        "name": "Entropy Draft",
        "mode": "live",
        "draft_format": "snake",
        "third_round_reversal": False,
        "team_count": 2,
        "round_count": 2,
        "user_slot": 2,
        "team_names": ["Alpha", "Your Team"],
        **overrides,
    }
    response = client.post(
        f"/api/v1/boards/{board_id}/draft-sessions",
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _pick(
    client: TestClient,
    draft: dict[str, object],
    player_id: str,
):
    current = draft["current_pick"]
    assert isinstance(current, dict)
    return client.post(
        f"/api/v1/draft-sessions/{draft['id']}/picks",
        json={
            "revision": draft["revision"],
            "expected_overall_pick": current["overall_pick"],
            "player_id": player_id,
        },
    )


def test_draft_order_fixtures_and_user_distance() -> None:
    linear = build_draft_order("linear", False, 4, 5)
    snake = build_draft_order("snake", False, 4, 5)
    reversal = build_draft_order("snake", True, 4, 5)

    def rounds(order: object) -> list[list[int]]:
        slots = [pick.selecting_slot for pick in order]
        return [slots[index : index + 4] for index in range(0, len(slots), 4)]

    assert rounds(linear) == [[1, 2, 3, 4]] * 5
    assert rounds(snake) == [
        [1, 2, 3, 4],
        [4, 3, 2, 1],
        [1, 2, 3, 4],
        [4, 3, 2, 1],
        [1, 2, 3, 4],
    ]
    assert rounds(reversal) == [
        [1, 2, 3, 4],
        [4, 3, 2, 1],
        [4, 3, 2, 1],
        [1, 2, 3, 4],
        [4, 3, 2, 1],
    ]
    assert picks_until_slot(snake, 1, 3) == 2
    assert picks_until_slot(snake, 3, 3) == 0
    assert picks_until_slot(snake, None, 3) is None


def test_session_snapshot_is_deduplicated_and_survives_restart(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, players = _board(client)
        draft = _start(client, board["id"])

        assert draft["candidate_total"] == len(players)
        assert draft["available_count"] == len(players)
        assert draft["active_pick_count"] == 0
        assert draft["current_pick"] == {
            "overall_pick": 1,
            "round_number": 1,
            "pick_in_round": 1,
            "selecting_slot": 1,
            "selecting_team": "Alpha",
        }
        assert draft["picks_until_user"] == 1
        assert draft["blind_data_hidden"] is True
        session_id = draft["id"]

    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        restored = client.get(f"/api/v1/draft-sessions/{session_id}")
        assert restored.status_code == 200
        assert restored.json() == draft


def test_invalid_and_archived_session_configuration_is_rejected(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, _ = _board(client)
        invalid = client.post(
            f"/api/v1/boards/{board['id']}/draft-sessions",
            json={
                "name": "Invalid",
                "draft_format": "linear",
                "third_round_reversal": True,
                "team_count": 2,
                "round_count": 2,
                "user_slot": 1,
            },
        )
        assert invalid.status_code == 422

        whitespace_name = client.post(
            f"/api/v1/boards/{board['id']}/draft-sessions",
            json={
                "name": "   ",
                "team_count": 2,
                "round_count": 2,
                "user_slot": 1,
            },
        )
        assert whitespace_name.status_code == 422

        invalid_team_names = client.post(
            f"/api/v1/boards/{board['id']}/draft-sessions",
            json={
                "name": "Invalid team names",
                "team_count": 2,
                "round_count": 2,
                "user_slot": 1,
                "team_names": ["Alpha", "x" * 201],
            },
        )
        assert invalid_team_names.status_code == 422

        blank_team_name = client.post(
            f"/api/v1/boards/{board['id']}/draft-sessions",
            json={
                "name": "Blank team name",
                "team_count": 2,
                "round_count": 2,
                "user_slot": 1,
                "team_names": ["Alpha", "   "],
            },
        )
        assert blank_team_name.status_code == 422

        archived = client.patch(
            f"/api/v1/boards/{board['id']}",
            json={"archived": True},
        )
        assert archived.status_code == 200
        rejected = client.post(
            f"/api/v1/boards/{board['id']}/draft-sessions",
            json={
                "name": "Archived",
                "team_count": 2,
                "round_count": 2,
                "user_slot": 1,
            },
        )
        assert rejected.status_code == 409


def test_pick_guards_candidate_views_correction_and_undo(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board, players = _board(client)
        first_entry = board["entries"][0]
        tiered = client.post(
            f"/api/v1/boards/{board['id']}/tiers",
            json={"name": "Priority", "color": "orange"},
        )
        assert tiered.status_code == 200
        tier_id = tiered.json()["tiers"][0]["id"]
        updated = client.patch(
            f"/api/v1/boards/{board['id']}/entries/{first_entry['id']}",
            json={
                "tier_id": tier_id,
                "favorite": True,
                "note": "Private draft note",
            },
        )
        assert updated.status_code == 200
        draft = _start(client, board["id"])

        blind = client.get(
            f"/api/v1/draft-sessions/{draft['id']}/candidates",
            params={"view": "blind", "limit": 100},
        )
        assert blind.status_code == 200
        assert blind.json()["total"] == len(players)
        for item in blind.json()["items"]:
            assert PRIVATE_CANDIDATE_KEYS.isdisjoint(item)
        default_page = client.get(
            f"/api/v1/draft-sessions/{draft['id']}/candidates",
            params={"view": "blind"},
        )
        assert default_page.status_code == 200
        assert default_page.json()["limit"] == 75
        oversized_page = client.get(
            f"/api/v1/draft-sessions/{draft['id']}/candidates",
            params={"view": "blind", "limit": 251},
        )
        assert oversized_page.status_code == 422

        personal = client.get(
            f"/api/v1/draft-sessions/{draft['id']}/candidates",
            params={"view": "personal", "limit": 100},
        )
        assert personal.status_code == 200
        assert personal.json()["items"][0]["personal_rank"] == 1
        assert personal.json()["items"][0]["tier_name"] == "Priority"
        assert personal.json()["items"][0]["favorite"] is True
        assert personal.json()["items"][0]["board_note"] == "Private draft note"

        first = _pick(client, draft, players[0]["id"])
        assert first.status_code == 200
        after_first = first.json()
        assert after_first["revision"] == 1
        assert after_first["current_pick"]["overall_pick"] == 2
        assert after_first["user_on_the_clock"] is True
        available = client.get(
            f"/api/v1/draft-sessions/{draft['id']}/candidates",
            params={"view": "blind", "limit": 100},
        ).json()
        assert players[0]["id"] not in {
            item["player_id"] for item in available["items"]
        }

        repeated = _pick(client, draft, players[0]["id"])
        assert repeated.status_code == 409
        unchanged = client.get(f"/api/v1/draft-sessions/{draft['id']}").json()
        assert unchanged["revision"] == 1
        assert unchanged["active_pick_count"] == 1

        duplicate = _pick(client, after_first, players[0]["id"])
        assert duplicate.status_code == 409

        corrected = client.patch(
            f"/api/v1/draft-sessions/{draft['id']}/picks/1",
            json={
                "revision": after_first["revision"],
                "expected_current_player_id": players[0]["id"],
                "replacement_player_id": players[1]["id"],
            },
        )
        assert corrected.status_code == 200
        corrected_body = corrected.json()
        assert corrected_body["revision"] == 2
        assert corrected_body["picks"][0]["overall_pick"] == 1
        assert corrected_body["picks"][0]["player_id"] == players[1]["id"]
        assert corrected_body["picks"][0]["correction_count"] == 1

        stale_correction = client.patch(
            f"/api/v1/draft-sessions/{draft['id']}/picks/1",
            json={
                "revision": 1,
                "expected_current_player_id": players[0]["id"],
                "replacement_player_id": players[2]["id"],
            },
        )
        assert stale_correction.status_code == 409

        undone = client.post(
            f"/api/v1/draft-sessions/{draft['id']}/undo",
            json={"revision": corrected_body["revision"]},
        )
        assert undone.status_code == 200
        assert undone.json()["current_pick"]["overall_pick"] == 1
        assert undone.json()["active_pick_count"] == 0
        with app.state.session_factory() as database:
            action_kinds = list(
                database.scalars(
                    select(DraftPickRevisionRow.action_kind)
                    .where(DraftPickRevisionRow.session_id == draft["id"])
                    .order_by(DraftPickRevisionRow.session_revision)
                )
            )
        assert action_kinds == ["made", "corrected", "undone"]


def test_late_addition_pause_completion_reset_and_safe_export(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board, players = _board(client)
        with app.state.session_factory() as database:
            now = utc_now_text()
            late_player = PlayerRow(
                id=str(uuid4()),
                display_name="Late Arrival",
                first_name="Late",
                last_name="Arrival",
                suffix=None,
                search_name="late arrival",
                team="FA",
                primary_position="RB",
                fantasy_positions_json='["RB"]',
                status="active",
                rookie_class=2026,
                is_rookie=True,
                created_at=now,
                updated_at=now,
            )
            database.add(late_player)
            database.commit()

        draft = _start(
            client,
            board["id"],
            team_count=2,
            round_count=1,
            user_slot=1,
            team_names=["Your Team", "Beta"],
        )
        assert draft["candidate_total"] == len(players)
        paused = client.patch(
            f"/api/v1/draft-sessions/{draft['id']}",
            json={"revision": draft["revision"], "status": "paused"},
        )
        assert paused.status_code == 200
        paused_body = paused.json()
        assert paused_body["current_pick"] == draft["current_pick"]
        blocked = _pick(client, paused_body, late_player.id)
        assert blocked.status_code == 409

        resumed = client.patch(
            f"/api/v1/draft-sessions/{draft['id']}",
            json={"revision": paused_body["revision"], "status": "active"},
        )
        assert resumed.status_code == 200
        resumed_body = resumed.json()
        assert resumed_body["current_pick"] == draft["current_pick"]

        late_pick = _pick(client, resumed_body, late_player.id)
        assert late_pick.status_code == 200
        after_late = late_pick.json()
        assert after_late["candidate_total"] == len(players) + 1
        assert after_late["picks"][0]["player_display_name"] == "Late Arrival"

        paused_after_pick = client.patch(
            f"/api/v1/draft-sessions/{draft['id']}",
            json={"revision": after_late["revision"], "status": "paused"},
        )
        assert paused_after_pick.status_code == 200
        undone_while_paused = client.post(
            f"/api/v1/draft-sessions/{draft['id']}/undo",
            json={"revision": paused_after_pick.json()["revision"]},
        )
        assert undone_while_paused.status_code == 200
        assert undone_while_paused.json()["status"] == "paused"
        assert undone_while_paused.json()["current_pick"]["overall_pick"] == 1
        resumed_after_undo = client.patch(
            f"/api/v1/draft-sessions/{draft['id']}",
            json={
                "revision": undone_while_paused.json()["revision"],
                "status": "active",
            },
        )
        assert resumed_after_undo.status_code == 200
        late_pick_again = _pick(client, resumed_after_undo.json(), late_player.id)
        assert late_pick_again.status_code == 200
        after_late = late_pick_again.json()

        completed = _pick(client, after_late, players[0]["id"])
        assert completed.status_code == 200
        completed_body = completed.json()
        assert completed_body["status"] == "completed"
        assert completed_body["current_pick"] is None
        assert completed_body["picks_until_user"] is None

        reopened = client.post(
            f"/api/v1/draft-sessions/{draft['id']}/undo",
            json={"revision": completed_body["revision"]},
        )
        assert reopened.status_code == 200
        assert reopened.json()["status"] == "active"
        assert reopened.json()["current_pick"]["overall_pick"] == 2

        exported = client.get(
            f"/api/v1/draft-sessions/{draft['id']}/export.csv"
        )
        assert exported.status_code == 200
        assert "Late Arrival" in exported.text
        assert "Private draft note" not in exported.text
        assert "provider" not in exported.text

        replacement = client.post(
            f"/api/v1/draft-sessions/{draft['id']}/reset",
            json={"revision": reopened.json()["revision"]},
        )
        assert replacement.status_code == 201
        replacement_body = replacement.json()
        assert replacement_body["reset_from_session_id"] == draft["id"]
        assert replacement_body["active_pick_count"] == 0
        assert replacement_body["revision"] == 0

        old = client.get(f"/api/v1/draft-sessions/{draft['id']}")
        assert old.status_code == 200
        assert old.json()["status"] == "reset"
        assert old.json()["active_pick_count"] == 1
        assert old.json()["reset_at"] is not None
