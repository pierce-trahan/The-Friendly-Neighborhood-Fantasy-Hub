from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.drafts.models import DraftSessionRow
from friendly_hub.domains.mocks.models import (
    MockConfigurationRow,
    MockGuidanceEventRow,
    MockPickDecisionRow,
)
from friendly_hub.domains.players.models import PlayerRelevanceRow, PlayerRow
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}


def _seed_board(client: TestClient) -> dict[str, object]:
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
        json={"name": "Correction Controls", "scope": "overall"},
    ).json()
    for player in players[:3]:
        board = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": player["id"]},
        ).json()
    return board


def _create_mock(
    client: TestClient,
    board_id: str,
    **overrides: object,
) -> dict[str, object]:
    payload = {
        "name": "Correction Lab",
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


def _available_players(
    client: TestClient,
    session_id: str,
) -> list[dict[str, object]]:
    response = client.get(
        f"/api/v1/draft-sessions/{session_id}/candidates",
        params={"view": "blind", "include_drafted": False, "limit": 100},
    )
    assert response.status_code == 200
    return response.json()["items"]


def test_cpu_correction_undo_replay_and_paused_undo(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board = _seed_board(client)
        initial = _create_mock(client, board["id"])
        advanced = _cpu_pick(client, initial)
        session_id = advanced["draft"]["id"]
        original_decision = advanced["last_cpu_decision"]
        replacement_id = next(
            row["player_id"]
            for row in _available_players(client, session_id)
            if row["player_id"] != original_decision["chosen_player_id"]
        )

        corrected = client.patch(
            f"/api/v1/draft-sessions/{session_id}/picks/1",
            json={
                "revision": advanced["draft"]["revision"],
                "expected_current_player_id": (
                    original_decision["chosen_player_id"]
                ),
                "replacement_player_id": replacement_id,
            },
        )
        assert corrected.status_code == 200, corrected.text
        after_correction = _mock(client, session_id)
        assert after_correction["draft"]["revision"] == 2
        assert after_correction["mock"]["revision"] == 2
        corrected_audit = client.get(
            f"/api/v1/mock-sessions/{session_id}/decisions/1"
        ).json()
        assert corrected_audit["decision_status"] == "historical"
        assert corrected_audit["manually_corrected"] is True

        undone = client.post(
            f"/api/v1/draft-sessions/{session_id}/undo",
            json={"revision": after_correction["draft"]["revision"]},
        )
        assert undone.status_code == 200, undone.text
        after_undo = _mock(client, session_id)
        assert after_undo["draft"]["active_pick_count"] == 0
        assert after_undo["draft"]["revision"] == 3
        assert after_undo["mock"]["revision"] == 3

        replayed = _cpu_pick(client, after_undo)
        replay_decision = replayed["last_cpu_decision"]
        assert replay_decision["id"] != original_decision["id"]
        assert (
            replay_decision["chosen_player_id"]
            == original_decision["chosen_player_id"]
        )
        assert replay_decision["total_score"] == original_decision["total_score"]
        assert replay_decision["component_scores"] == (
            original_decision["component_scores"]
        )
        assert replay_decision["decision_status"] == "active"
        assert replay_decision["manually_corrected"] is False

        paused = client.patch(
            f"/api/v1/draft-sessions/{session_id}",
            json={
                "revision": replayed["draft"]["revision"],
                "status": "paused",
            },
        )
        assert paused.status_code == 200
        paused_undo = client.post(
            f"/api/v1/draft-sessions/{session_id}/undo",
            json={"revision": paused.json()["revision"]},
        )
        assert paused_undo.status_code == 200
        paused_mock = _mock(client, session_id)
        assert paused_mock["draft"]["status"] == "paused"
        assert paused_mock["mock"]["revision"] == 5
        blocked = client.post(
            f"/api/v1/mock-sessions/{session_id}/cpu-pick",
            json={
                "draft_revision": paused_mock["draft"]["revision"],
                "mock_revision": paused_mock["mock"]["revision"],
                "expected_overall_pick": 1,
                "expected_selecting_slot": 1,
            },
        )
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "MOCK.NOT_ACTIVE"

        with app.state.session_factory() as database:
            configuration = database.scalar(
                select(MockConfigurationRow).where(
                    MockConfigurationRow.draft_session_id == session_id
                )
            )
            assert configuration is not None
            assert database.scalar(
                select(func.count())
                .select_from(MockPickDecisionRow)
                .where(
                    MockPickDecisionRow.mock_configuration_id
                    == configuration.id
                )
            ) == 2


def test_user_correction_undo_repick_and_pause_guidance_order(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board = _seed_board(client)
        mock = _create_mock(
            client,
            board["id"],
            user_slot=1,
            team_names=["Your Team", "CPU One", "CPU Two"],
            fallback_archetypes={"2": "balanced", "3": "qb_priority"},
        )
        session_id = mock["draft"]["id"]
        candidates = _available_players(client, session_id)
        rb_id = next(
            row["player_id"]
            for row in candidates
            if row["primary_position"] == "RB"
        )
        wr_id = next(
            row["player_id"]
            for row in candidates
            if row["primary_position"] == "WR"
        )

        picked = client.post(
            f"/api/v1/draft-sessions/{session_id}/picks",
            json={
                "revision": 0,
                "expected_overall_pick": 1,
                "player_id": rb_id,
            },
        )
        assert picked.status_code == 200
        corrected = client.patch(
            f"/api/v1/draft-sessions/{session_id}/picks/1",
            json={
                "revision": picked.json()["revision"],
                "expected_current_player_id": rb_id,
                "replacement_player_id": wr_id,
            },
        )
        assert corrected.status_code == 200
        after_correction = _mock(client, session_id)
        assert after_correction["current_checkpoint"]["observed_counts"]["WR"] == 1
        assert after_correction["current_checkpoint"]["observed_counts"]["RB"] == 0

        undone = client.post(
            f"/api/v1/draft-sessions/{session_id}/undo",
            json={"revision": corrected.json()["revision"]},
        )
        assert undone.status_code == 200
        after_undo = _mock(client, session_id)
        assert after_undo["current_checkpoint"]["observed_counts"]["TOTAL"] == 0

        repicked = client.post(
            f"/api/v1/draft-sessions/{session_id}/picks",
            json={
                "revision": undone.json()["revision"],
                "expected_overall_pick": 1,
                "player_id": rb_id,
            },
        )
        assert repicked.status_code == 200
        after_repick = _mock(client, session_id)
        assert after_repick["draft"]["revision"] == 4
        assert after_repick["mock"]["revision"] == 4
        assert after_repick["current_checkpoint"]["observed_counts"]["RB"] == 1

        history = client.get(
            f"/api/v1/mock-sessions/{session_id}/guidance",
            params={"limit": 100},
        ).json()
        assert history["total"] == 5
        assert len({row["id"] for row in history["items"]}) == 5
        assert history["items"][0]["id"] == after_repick["current_checkpoint"]["id"]
        assert history["items"][0]["observed_counts"]["RB"] == 1
        assert history["items"][1]["observed_counts"]["TOTAL"] == 0
        assert history["items"][2]["observed_counts"]["WR"] == 1

        paused = client.patch(
            f"/api/v1/draft-sessions/{session_id}",
            json={
                "revision": after_repick["draft"]["revision"],
                "status": "paused",
            },
        )
        resumed = client.patch(
            f"/api/v1/draft-sessions/{session_id}",
            json={"revision": paused.json()["revision"], "status": "active"},
        )
        assert resumed.status_code == 200
        unchanged_history = client.get(
            f"/api/v1/mock-sessions/{session_id}/guidance",
            params={"limit": 100},
        ).json()
        assert unchanged_history["total"] == 5
        assert _mock(client, session_id)["mock"]["revision"] == 4


def test_reset_copies_mock_state_and_reports_replay_fidelity(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board = _seed_board(client)
        source = _create_mock(
            client,
            board["id"],
            include_in_learning=True,
        )
        source = _cpu_pick(client, source)
        source_id = source["draft"]["id"]

        reset = client.post(
            f"/api/v1/draft-sessions/{source_id}/reset",
            json={"revision": source["draft"]["revision"]},
        )
        assert reset.status_code == 201, reset.text
        replacement_id = reset.json()["id"]
        old = _mock(client, source_id)
        replacement = _mock(client, replacement_id)
        assert old["draft"]["status"] == "reset"
        assert old["last_cpu_decision"]["overall_pick"] == 1
        assert replacement["draft"]["reset_from_session_id"] == source_id
        assert replacement["draft"]["active_pick_count"] == 0
        assert replacement["mock"]["seed"] == source["mock"]["seed"]
        assert replacement["mock"]["randomness"] == source["mock"]["randomness"]
        assert replacement["mock"]["current_strategy_key"] == (
            source["mock"]["current_strategy_key"]
        )
        assert replacement["cpu_profiles"] == source["cpu_profiles"]
        assert replacement["mock"]["include_in_learning"] is False
        assert replacement["mock"]["reset_replay_status"] == "exact_replay"

        new_seed_reset = client.post(
            f"/api/v1/draft-sessions/{replacement_id}/reset",
            json={"revision": 0, "seed": "99"},
        )
        assert new_seed_reset.status_code == 201
        new_seed_id = new_seed_reset.json()["id"]
        new_seed_mock = _mock(client, new_seed_id)
        assert new_seed_mock["mock"]["seed"] == "99"
        assert new_seed_mock["mock"]["reset_replay_status"] == "new_seed"

        with app.state.session_factory() as database:
            now = utc_now_text()
            player_id = str(uuid4())
            database.add(
                PlayerRow(
                    id=player_id,
                    display_name="Fresh Snapshot",
                    first_name="Fresh",
                    last_name="Snapshot",
                    suffix=None,
                    search_name="fresh snapshot",
                    team="FA",
                    primary_position="TE",
                    fantasy_positions_json='["TE"]',
                    status="active",
                    rookie_class=2026,
                    is_rookie=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            database.flush()
            database.add(
                PlayerRelevanceRow(
                    id=str(uuid4()),
                    player_id=player_id,
                    reason="manual",
                    reference_id=None,
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            database.commit()

        changed_reset = client.post(
            f"/api/v1/draft-sessions/{new_seed_id}/reset",
            json={"revision": 0},
        )
        assert changed_reset.status_code == 201
        changed = _mock(client, changed_reset.json()["id"])
        assert changed["mock"]["reset_replay_status"] == "snapshot_changed"
        assert changed["draft"]["candidate_total"] == (
            new_seed_mock["draft"]["candidate_total"] + 1
        )

        live = client.post(
            f"/api/v1/boards/{board['id']}/draft-sessions",
            json={
                "name": "Live Draft",
                "mode": "live",
                "team_count": 2,
                "round_count": 1,
                "user_slot": 1,
            },
        ).json()
        rejected = client.post(
            f"/api/v1/draft-sessions/{live['id']}/reset",
            json={"revision": 0, "seed": "7"},
        )
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == (
            "DRAFT.SEED_NOT_APPLICABLE"
        )

    with TestClient(
        create_app(runtime_settings),
        headers=TRUSTED_HEADERS,
    ) as restarted:
        restored = _mock(restarted, replacement_id)
        assert restored["mock"]["reset_replay_status"] == "exact_replay"
        assert restored["draft"]["active_pick_count"] == 0


def test_correction_and_reset_failures_roll_back_both_domains(
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
        mock = _create_mock(
            client,
            board["id"],
            user_slot=1,
            team_names=["Your Team", "CPU One", "CPU Two"],
            fallback_archetypes={"2": "balanced", "3": "qb_priority"},
        )
        session_id = mock["draft"]["id"]
        candidates = _available_players(client, session_id)
        first_id = candidates[0]["player_id"]
        replacement_id = candidates[1]["player_id"]
        picked = client.post(
            f"/api/v1/draft-sessions/{session_id}/picks",
            json={
                "revision": 0,
                "expected_overall_pick": 1,
                "player_id": first_id,
            },
        )
        assert picked.status_code == 200
        baseline = _mock(client, session_id)

        def fail_mock_revision(*args: object, **kwargs: object) -> None:
            raise RuntimeError("injected lifecycle failure")

        monkeypatch.setattr(
            "friendly_hub.domains.mocks.lifecycle_service."
            "_update_mock_strategy",
            fail_mock_revision,
        )
        failed_correction = client.patch(
            f"/api/v1/draft-sessions/{session_id}/picks/1",
            json={
                "revision": baseline["draft"]["revision"],
                "expected_current_player_id": first_id,
                "replacement_player_id": replacement_id,
            },
        )
        assert failed_correction.status_code == 500
        after_failure = _mock(client, session_id)
        assert after_failure["draft"]["revision"] == baseline["draft"]["revision"]
        assert after_failure["mock"]["revision"] == baseline["mock"]["revision"]
        assert after_failure["draft"]["picks"][0]["player_id"] == first_id
        assert after_failure["current_checkpoint"]["id"] == (
            baseline["current_checkpoint"]["id"]
        )

        failed_reset = client.post(
            f"/api/v1/draft-sessions/{session_id}/reset",
            json={"revision": baseline["draft"]["revision"]},
        )
        assert failed_reset.status_code == 500
        after_reset_failure = _mock(client, session_id)
        assert after_reset_failure["draft"]["status"] == "active"
        with app.state.session_factory() as database:
            assert database.scalar(
                select(func.count()).select_from(DraftSessionRow)
            ) == 1
            assert database.scalar(
                select(func.count()).select_from(MockConfigurationRow)
            ) == 1
            configuration = database.scalar(
                select(MockConfigurationRow).where(
                    MockConfigurationRow.draft_session_id == session_id
                )
            )
            assert configuration is not None
            assert database.scalar(
                select(func.count())
                .select_from(MockGuidanceEventRow)
                .where(
                    MockGuidanceEventRow.mock_configuration_id
                    == configuration.id
                )
            ) == 2
