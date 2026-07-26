from fastapi.testclient import TestClient

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}


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


def _board_with_players(
    client: TestClient,
    *,
    count: int = 4,
    scope: str = "overall",
) -> tuple[dict[str, object], list[dict[str, object]]]:
    players = _seed_players(client)
    created = client.post(
        "/api/v1/boards",
        json={"name": "Gut Board", "scope": scope},
    )
    assert created.status_code == 201
    board = created.json()
    for player in players[:count]:
        response = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": player["id"]},
        )
        assert response.status_code == 200
        board = response.json()
    return board, players


def _start_session(
    client: TestClient,
    board_id: str,
    **payload: object,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/boards/{board_id}/gut-elo-sessions",
        json={"queue_mode": "board", **payload},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _answer(
    client: TestClient,
    gut_session: dict[str, object],
    outcome: str,
):
    pair = gut_session["next_pair"]
    assert isinstance(pair, dict)
    return client.post(
        f"/api/v1/gut-elo-sessions/{gut_session['id']}/actions",
        json={
            "revision": gut_session["revision"],
            "player_a_id": pair["player_a"]["id"],
            "player_b_id": pair["player_b"]["id"],
            "outcome": outcome,
        },
    )


def test_session_snapshot_is_persistent_and_manual_board_is_unchanged(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, _ = _board_with_players(client, count=4)
        original_order = [
            entry["player"]["id"] for entry in board["entries"]
        ]
        gut_session = _start_session(client, board["id"], target_count=3)
        first_pair = gut_session["next_pair"]

        assert gut_session["participant_count"] == 4
        assert gut_session["target_count"] == 3
        assert gut_session["manual_board_unchanged"] is True
        assert {item["rating"] for item in gut_session["participants"]} == {1000.0}
        assert [item["starting_manual_rank"] for item in gut_session["participants"]] == [
            1,
            2,
            3,
            4,
        ]

        reversed_order = list(reversed(original_order))
        moved = client.put(
            f"/api/v1/boards/{board['id']}/order",
            json={"player_ids": reversed_order},
        )
        assert moved.status_code == 200
        unchanged_session = client.get(
            f"/api/v1/gut-elo-sessions/{gut_session['id']}"
        )
        assert unchanged_session.status_code == 200
        assert unchanged_session.json()["next_pair"] == first_pair
        assert [
            item["starting_manual_rank"]
            for item in unchanged_session.json()["participants"]
        ] == [1, 2, 3, 4]

    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        restored = client.get(f"/api/v1/gut-elo-sessions/{gut_session['id']}")
        assert restored.status_code == 200
        assert restored.json()["next_pair"] == first_pair
        board_after_restart = client.get(f"/api/v1/boards/{board['id']}").json()
        assert [
            entry["player"]["id"] for entry in board_after_restart["entries"]
        ] == reversed_order


def test_decisive_rating_is_deterministic_and_stale_submit_is_atomic(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, _ = _board_with_players(client, count=3)
        gut_session = _start_session(client, board["id"], target_count=2)
        original_pair = gut_session["next_pair"]
        decided = _answer(client, gut_session, "a_win")
        assert decided.status_code == 200
        updated = decided.json()
        ratings = {
            item["player"]["id"]: item["rating"]
            for item in updated["participants"]
        }
        assert ratings[original_pair["player_a"]["id"]] == 1016.0
        assert ratings[original_pair["player_b"]["id"]] == 984.0
        assert updated["revision"] == 1
        assert updated["progress"]["decisive_count"] == 1

        repeated = _answer(client, gut_session, "a_win")
        assert repeated.status_code == 409
        after_rejection = client.get(
            f"/api/v1/gut-elo-sessions/{gut_session['id']}"
        ).json()
        assert after_rejection["revision"] == 1
        assert after_rejection["participants"] == updated["participants"]


def test_skip_insufficient_and_undo_have_distinct_reversible_behavior(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, _ = _board_with_players(client, count=3)
        gut_session = _start_session(client, board["id"], target_count=2)
        first_pair = gut_session["next_pair"]

        skipped = _answer(client, gut_session, "skip")
        assert skipped.status_code == 200
        skipped_body = skipped.json()
        assert skipped_body["progress"]["resolved_count"] == 0
        assert skipped_body["progress"]["skip_count"] == 1
        assert {item["rating"] for item in skipped_body["participants"]} == {
            1000.0
        }
        assert skipped_body["next_pair"] != first_pair

        undone = client.post(
            f"/api/v1/gut-elo-sessions/{gut_session['id']}/undo"
        )
        assert undone.status_code == 200
        assert undone.json()["revision"] == 0
        assert undone.json()["next_pair"] == first_pair

        insufficient = _answer(client, undone.json(), "insufficient")
        assert insufficient.status_code == 200
        insufficient_body = insufficient.json()
        assert insufficient_body["progress"]["resolved_count"] == 1
        assert insufficient_body["progress"]["insufficient_count"] == 1
        assert {item["rating"] for item in insufficient_body["participants"]} == {
            1000.0
        }
        history = client.get(
            f"/api/v1/boards/{board['id']}/gut-elo-sessions"
        )
        assert history.status_code == 200
        assert history.json()["items"][0]["resolved_count"] == 1


def test_pause_completion_and_undo_survive_state_transitions(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, _ = _board_with_players(client, count=2)
        gut_session = _start_session(client, board["id"])
        offered_pair = gut_session["next_pair"]

        paused = client.patch(
            f"/api/v1/gut-elo-sessions/{gut_session['id']}",
            json={"status": "paused"},
        )
        assert paused.status_code == 200
        assert paused.json()["status"] == "paused"
        assert paused.json()["next_pair"] is None
        blocked = _answer(client, gut_session, "b_win")
        assert blocked.status_code == 409

    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        restored = client.get(f"/api/v1/gut-elo-sessions/{gut_session['id']}")
        assert restored.json()["status"] == "paused"
        resumed = client.patch(
            f"/api/v1/gut-elo-sessions/{gut_session['id']}",
            json={"status": "active"},
        )
        assert resumed.status_code == 200
        assert resumed.json()["next_pair"] == offered_pair

        completed = _answer(client, resumed.json(), "b_win")
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        assert completed.json()["completed_at"] is not None
        assert completed.json()["next_pair"] is None

        reopened = client.post(
            f"/api/v1/gut-elo-sessions/{gut_session['id']}/undo"
        )
        assert reopened.status_code == 200
        assert reopened.json()["status"] == "active"
        assert reopened.json()["completed_at"] is None
        assert reopened.json()["revision"] == 0
        assert reopened.json()["next_pair"] == offered_pair


def test_filtered_queues_and_invalid_session_boundaries(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, players = _board_with_players(client, count=6, scope="rookie")
        by_position: dict[str, list[str]] = {}
        for player in players[:6]:
            by_position.setdefault(player["primary_position"], []).append(player["id"])

        rb_session = _start_session(
            client,
            board["id"],
            queue_mode="position",
            position="RB",
        )
        assert {
            item["player"]["id"] for item in rb_session["participants"]
        } == set(by_position["RB"])
        assert rb_session["board_scope"] == "rookie"

        tier_response = client.post(
            f"/api/v1/boards/{board['id']}/tiers",
            json={"name": "Decision Tier"},
        )
        tier_id = tier_response.json()["tiers"][0]["id"]
        board = tier_response.json()
        for entry in board["entries"][:2]:
            board = client.patch(
                f"/api/v1/boards/{board['id']}/entries/{entry['id']}",
                json={"tier_id": tier_id},
            ).json()
        tier_session = _start_session(
            client,
            board["id"],
            queue_mode="tier",
            tier_id=tier_id,
        )
        assert tier_session["participant_count"] == 2
        assert {
            item["starting_tier_name"] for item in tier_session["participants"]
        } == {"Decision Tier"}

        uncertainty = _start_session(
            client,
            board["id"],
            queue_mode="uncertainty",
            target_count=2,
        )
        assert uncertainty["participant_count"] == 6

        invalid = client.post(
            f"/api/v1/boards/{board['id']}/gut-elo-sessions",
            json={"queue_mode": "board", "position": "QB"},
        )
        assert invalid.status_code == 422

        board = client.patch(
            f"/api/v1/boards/{board['id']}",
            json={"archived": True},
        ).json()
        archived = client.post(
            f"/api/v1/boards/{board['id']}/gut-elo-sessions",
            json={"queue_mode": "board"},
        )
        assert archived.status_code == 409


def test_session_responses_and_errors_do_not_leak_board_notes(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, _ = _board_with_players(client, count=2)
        private_note = "private evaluation that must not enter Gut ELO"
        entry = board["entries"][0]
        client.patch(
            f"/api/v1/boards/{board['id']}/entries/{entry['id']}",
            json={"note": private_note, "favorite": True},
        )
        gut_session = _start_session(client, board["id"])
        assert private_note not in str(gut_session)
        assert "provider" not in str(gut_session).casefold()

        stale = client.post(
            f"/api/v1/gut-elo-sessions/{gut_session['id']}/actions",
            json={
                "revision": 99,
                "player_a_id": gut_session["next_pair"]["player_a"]["id"],
                "player_b_id": gut_session["next_pair"]["player_b"]["id"],
                "outcome": "a_win",
            },
        )
        assert stale.status_code == 409
        assert private_note not in stale.text
