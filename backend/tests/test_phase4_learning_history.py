from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.domains.drafts.models import DraftPickRow
from friendly_hub.domains.mocks.models import (
    MockConfigurationRow,
    MockGuidanceEventRow,
    MockPickDecisionRow,
    MockStrategyRevisionRow,
)
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}
PRIVATE_BOARD_NOTE = "Private board note outside mock history"
PRIVATE_PIVOT_NOTE = "Private pivot note outside mock history"


def _seed_board(
    client: TestClient,
    *,
    name: str = "Learning History Board",
) -> dict[str, object]:
    preview = client.post("/api/v1/player-imports/fixture/preview")
    assert preview.status_code == 201
    assert client.post(
        f"/api/v1/player-imports/{preview.json()['id']}/commit"
    ).status_code == 200
    players = client.get(
        "/api/v1/players",
        params={"limit": 100},
    ).json()["items"]
    board = client.post(
        "/api/v1/boards",
        json={"name": name, "scope": "overall"},
    ).json()
    for player in players[:3]:
        board = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": player["id"]},
        ).json()
    first_entry = board["entries"][0]
    response = client.patch(
        f"/api/v1/boards/{board['id']}/entries/{first_entry['id']}",
        json={"note": PRIVATE_BOARD_NOTE},
    )
    assert response.status_code == 200
    return response.json()


def _create_mock(
    client: TestClient,
    board_id: str,
    **overrides: object,
) -> dict[str, object]:
    payload = {
        "name": "Learning Rehearsal",
        "team_count": 3,
        "round_count": 3,
        "user_slot": 3,
        "team_names": ["CPU One", "CPU Two", "Your Team"],
        "seed": "87",
        "randomness": 20,
        "strategy_key": "hero_rb",
        "fallback_archetypes": {"1": "balanced", "2": "qb_priority"},
        **overrides,
    }
    response = client.post(
        f"/api/v1/boards/{board_id}/mock-sessions",
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _mock(client: TestClient, session_id: str) -> dict[str, object]:
    response = client.get(f"/api/v1/mock-sessions/{session_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _learning(
    client: TestClient,
    mock: dict[str, object],
    include: bool,
):
    return client.patch(
        f"/api/v1/mock-sessions/{mock['draft']['id']}/learning",
        json={
            "mock_revision": mock["mock"]["revision"],
            "include_in_learning": include,
        },
    )


def _cpu_pick(
    client: TestClient,
    mock: dict[str, object],
) -> dict[str, object]:
    current = mock["draft"]["current_pick"]
    response = client.post(
        f"/api/v1/mock-sessions/{mock['draft']['id']}/cpu-pick",
        json={
            "draft_revision": mock["draft"]["revision"],
            "mock_revision": mock["mock"]["revision"],
            "expected_overall_pick": current["overall_pick"],
            "expected_selecting_slot": current["selecting_slot"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _first_available_player(
    client: TestClient,
    session_id: str,
) -> str:
    response = client.get(
        f"/api/v1/draft-sessions/{session_id}/candidates",
        params={"view": "blind", "limit": 1},
    )
    assert response.status_code == 200
    return response.json()["items"][0]["player_id"]


def test_learning_consent_is_reversible_restart_safe_and_atomic(
    runtime_settings: RuntimeSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(
        app,
        headers=TRUSTED_HEADERS,
        raise_server_exceptions=False,
    ) as client:
        board = _seed_board(client)
        initial = _create_mock(client, board["id"])
        session_id = initial["draft"]["id"]
        assert initial["mock"]["include_in_learning"] is False

        enabled_response = _learning(client, initial, True)
        assert enabled_response.status_code == 200
        enabled = enabled_response.json()
        first_opt_in = enabled["mock"]["learning_opted_in_at"]
        assert enabled["mock"]["revision"] == 1
        assert enabled["draft"]["revision"] == 0
        assert enabled["mock"]["include_in_learning"] is True
        assert first_opt_in is not None
        assert enabled["mock"]["learning_withdrawn_at"] is None

        unchanged = _learning(client, enabled, True)
        assert unchanged.status_code == 409
        assert unchanged.json()["error"]["code"] == "MOCK.LEARNING_UNCHANGED"
        stale = client.patch(
            f"/api/v1/mock-sessions/{session_id}/learning",
            json={
                "mock_revision": 0,
                "include_in_learning": False,
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "MOCK.STALE_REVISION"

        disabled_response = _learning(client, enabled, False)
        assert disabled_response.status_code == 200
        disabled = disabled_response.json()
        withdrawal = disabled["mock"]["learning_withdrawn_at"]
        assert disabled["mock"]["revision"] == 2
        assert disabled["mock"]["include_in_learning"] is False
        assert disabled["mock"]["learning_opted_in_at"] == first_opt_in
        assert withdrawal is not None

        reenabled_response = _learning(client, disabled, True)
        assert reenabled_response.status_code == 200
        reenabled = reenabled_response.json()
        assert reenabled["mock"]["revision"] == 3
        assert reenabled["mock"]["include_in_learning"] is True
        assert reenabled["mock"]["learning_opted_in_at"] >= first_opt_in
        assert reenabled["mock"]["learning_withdrawn_at"] == withdrawal

        with app.state.session_factory() as database:
            configuration = database.scalar(
                select(MockConfigurationRow).where(
                    MockConfigurationRow.draft_session_id == session_id
                )
            )
            assert configuration is not None
            counts_before = {
                "picks": database.scalar(
                    select(func.count())
                    .select_from(DraftPickRow)
                    .where(
                        DraftPickRow.session_id == session_id,
                        DraftPickRow.player_id.is_not(None),
                    )
                ),
                "decisions": database.scalar(
                    select(func.count())
                    .select_from(MockPickDecisionRow)
                    .where(
                        MockPickDecisionRow.mock_configuration_id
                        == configuration.id
                    )
                ),
                "strategies": database.scalar(
                    select(func.count())
                    .select_from(MockStrategyRevisionRow)
                    .where(
                        MockStrategyRevisionRow.mock_configuration_id
                        == configuration.id
                    )
                ),
                "guidance": database.scalar(
                    select(func.count())
                    .select_from(MockGuidanceEventRow)
                    .where(
                        MockGuidanceEventRow.mock_configuration_id
                        == configuration.id
                    )
                ),
            }

        def fail_mock_revision(*args: object, **kwargs: object) -> None:
            raise RuntimeError("injected consent failure")

        monkeypatch.setattr(
            "friendly_hub.domains.mocks.history_service."
            "_update_mock_strategy",
            fail_mock_revision,
        )
        failed = _learning(client, reenabled, False)
        assert failed.status_code == 500
        after_failure = _mock(client, session_id)
        assert after_failure["mock"]["revision"] == 3
        assert after_failure["mock"]["include_in_learning"] is True
        assert after_failure["mock"]["learning_withdrawn_at"] == withdrawal
        assert PRIVATE_BOARD_NOTE not in enabled_response.text

        with app.state.session_factory() as database:
            configuration = database.scalar(
                select(MockConfigurationRow).where(
                    MockConfigurationRow.draft_session_id == session_id
                )
            )
            assert configuration is not None
            counts_after = {
                "picks": database.scalar(
                    select(func.count())
                    .select_from(DraftPickRow)
                    .where(
                        DraftPickRow.session_id == session_id,
                        DraftPickRow.player_id.is_not(None),
                    )
                ),
                "decisions": database.scalar(
                    select(func.count())
                    .select_from(MockPickDecisionRow)
                    .where(
                        MockPickDecisionRow.mock_configuration_id
                        == configuration.id
                    )
                ),
                "strategies": database.scalar(
                    select(func.count())
                    .select_from(MockStrategyRevisionRow)
                    .where(
                        MockStrategyRevisionRow.mock_configuration_id
                        == configuration.id
                    )
                ),
                "guidance": database.scalar(
                    select(func.count())
                    .select_from(MockGuidanceEventRow)
                    .where(
                        MockGuidanceEventRow.mock_configuration_id
                        == configuration.id
                    )
                ),
            }
        assert counts_after == counts_before

    with TestClient(
        create_app(runtime_settings),
        headers=TRUSTED_HEADERS,
    ) as restarted:
        restored = _mock(restarted, session_id)
        assert restored["mock"]["revision"] == 3
        assert restored["mock"]["include_in_learning"] is True
        assert restored["mock"]["learning_withdrawn_at"] == withdrawal


def test_learning_consent_accepts_paused_completed_and_reset_history(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board = _seed_board(client)

        paused = _create_mock(client, board["id"], name="Paused History")
        paused_draft = client.patch(
            f"/api/v1/draft-sessions/{paused['draft']['id']}",
            json={"revision": 0, "status": "paused"},
        )
        assert paused_draft.status_code == 200
        paused = _mock(client, paused["draft"]["id"])
        paused_enabled = _learning(client, paused, True)
        assert paused_enabled.status_code == 200
        assert paused_enabled.json()["draft"]["status"] == "paused"

        completed = _create_mock(
            client,
            board["id"],
            name="Completed History",
            team_count=2,
            round_count=1,
            user_slot=1,
            team_names=["Your Team", "CPU"],
            fallback_archetypes={"2": "balanced"},
        )
        player_id = _first_available_player(
            client,
            completed["draft"]["id"],
        )
        user_pick = client.post(
            f"/api/v1/draft-sessions/{completed['draft']['id']}/picks",
            json={
                "revision": 0,
                "expected_overall_pick": 1,
                "player_id": player_id,
            },
        )
        assert user_pick.status_code == 200
        completed = _cpu_pick(
            client,
            _mock(client, completed["draft"]["id"]),
        )
        assert completed["draft"]["status"] == "completed"
        completed_enabled = _learning(client, completed, True)
        assert completed_enabled.status_code == 200

        reset_source = _create_mock(client, board["id"], name="Reset History")
        reset = client.post(
            f"/api/v1/draft-sessions/{reset_source['draft']['id']}/reset",
            json={"revision": 0},
        )
        assert reset.status_code == 201
        reset_source = _mock(client, reset_source["draft"]["id"])
        assert reset_source["draft"]["status"] == "reset"
        reset_enabled = _learning(client, reset_source, True)
        assert reset_enabled.status_code == 200
        replacement = _mock(client, reset.json()["id"])
        assert replacement["mock"]["include_in_learning"] is False


def test_mock_history_summaries_are_bounded_scoped_and_private(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board = _seed_board(client)
        other_board = _seed_board(client, name="Other Board")
        _create_mock(client, other_board["id"], name="Hidden Other Mock")

        active = _create_mock(client, board["id"], name="Active Mock")
        paused = _create_mock(client, board["id"], name="Paused Mock")
        assert client.patch(
            f"/api/v1/draft-sessions/{paused['draft']['id']}",
            json={"revision": 0, "status": "paused"},
        ).status_code == 200

        pivoted = _create_mock(client, board["id"], name="Pivoted Reset Mock")
        pivot_response = client.patch(
            f"/api/v1/mock-sessions/{pivoted['draft']['id']}/strategy",
            json={
                "mock_revision": 0,
                "expected_current_overall_pick": 1,
                "strategy_key": "robust_rb",
                "private_user_note": PRIVATE_PIVOT_NOTE,
            },
        )
        assert pivot_response.status_code == 200
        pivoted = pivot_response.json()
        reset = client.post(
            f"/api/v1/draft-sessions/{pivoted['draft']['id']}/reset",
            json={"revision": pivoted["draft"]["revision"]},
        )
        assert reset.status_code == 201
        replacement_id = reset.json()["id"]

        completed = _create_mock(
            client,
            board["id"],
            name="Completed Mock",
            team_count=2,
            round_count=1,
            user_slot=1,
            team_names=["Your Team", "CPU"],
            fallback_archetypes={"2": "balanced"},
        )
        player_id = _first_available_player(
            client,
            completed["draft"]["id"],
        )
        assert client.post(
            f"/api/v1/draft-sessions/{completed['draft']['id']}/picks",
            json={
                "revision": 0,
                "expected_overall_pick": 1,
                "player_id": player_id,
            },
        ).status_code == 200
        completed = _cpu_pick(
            client,
            _mock(client, completed["draft"]["id"]),
        )
        assert completed["draft"]["status"] == "completed"

        response = client.get(
            f"/api/v1/boards/{board['id']}/mock-sessions",
            params={"limit": 100},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 5
        assert len(body["items"]) == 5
        by_name = {item["name"]: item for item in body["items"]}
        assert by_name["Active Mock"]["completion_state"] == "incomplete"
        assert by_name["Paused Mock"]["status"] == "paused"
        assert by_name["Paused Mock"]["completion_state"] == "incomplete"
        assert by_name["Pivoted Reset Mock"]["completion_state"] == "reset"
        assert by_name["Pivoted Reset Mock"]["pivot_count"] == 1
        assert by_name["Pivoted Reset Mock"]["current_strategy_key"] == (
            "robust_rb"
        )
        assert by_name["Completed Mock"]["completion_state"] == "completed"
        replacement = next(
            item
            for item in body["items"]
            if item["session_id"] == replacement_id
        )
        assert replacement["current_strategy_key"] == "robust_rb"
        assert replacement["pivot_count"] == 0
        assert replacement["mock_revision"] == 0
        assert replacement["include_in_learning"] is False
        assert all(
            item["rng_version"]
            and item["cpu_engine_version"]
            and item["strategy_definition_version"]
            for item in body["items"]
        )
        assert {item["session_id"] for item in body["items"]} == {
            active["draft"]["id"],
            paused["draft"]["id"],
            pivoted["draft"]["id"],
            replacement_id,
            completed["draft"]["id"],
        }

        first_page = client.get(
            f"/api/v1/boards/{board['id']}/mock-sessions",
            params={"limit": 1, "offset": 0},
        ).json()
        second_page = client.get(
            f"/api/v1/boards/{board['id']}/mock-sessions",
            params={"limit": 1, "offset": 1},
        ).json()
        assert first_page["total"] == 5
        assert first_page["items"][0]["session_id"] == (
            body["items"][0]["session_id"]
        )
        assert second_page["items"][0]["session_id"] == (
            body["items"][1]["session_id"]
        )
        assert first_page["items"][0]["session_id"] != (
            second_page["items"][0]["session_id"]
        )

        text = response.text
        for forbidden in (
            PRIVATE_BOARD_NOTE,
            PRIVATE_PIVOT_NOTE,
            "player_id",
            "provider",
            "manager_reference",
            "guidance",
            "decision",
        ):
            assert forbidden not in text

        missing = client.get(
            "/api/v1/boards/missing-board/mock-sessions"
        )
        assert missing.status_code == 404
        invalid_page = client.get(
            f"/api/v1/boards/{board['id']}/mock-sessions",
            params={"limit": 101},
        )
        assert invalid_page.status_code == 422
