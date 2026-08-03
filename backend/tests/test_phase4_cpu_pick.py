from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.domains.drafts.models import DraftPickRevisionRow, DraftPickRow
from friendly_hub.domains.mocks.models import (
    MockConfigurationRow,
    MockPickDecisionRow,
)
from friendly_hub.domains.mocks.schemas import MockCpuPickCreate
from friendly_hub.domains.mocks.service import advance_cpu_pick
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}
PRIVATE_NOTE = "Do not expose this CPU-room note"


def _seed_board(client: TestClient) -> dict[str, object]:
    preview = client.post("/api/v1/player-imports/fixture/preview")
    assert preview.status_code == 201
    assert client.post(
        f"/api/v1/player-imports/{preview.json()['id']}/commit"
    ).status_code == 200
    players_response = client.get("/api/v1/players", params={"limit": 100})
    assert players_response.status_code == 200
    players = players_response.json()["items"]

    board_response = client.post(
        "/api/v1/boards",
        json={"name": "CPU Pick Board", "scope": "overall"},
    )
    assert board_response.status_code == 201
    board = board_response.json()
    for player in players[:3]:
        response = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": player["id"]},
        )
        assert response.status_code == 200
        board = response.json()
    first_entry = board["entries"][0]
    response = client.patch(
        f"/api/v1/boards/{board['id']}/entries/{first_entry['id']}",
        json={"note": PRIVATE_NOTE, "favorite": True},
    )
    assert response.status_code == 200
    return response.json()


def _mock_payload(**overrides: object) -> dict[str, object]:
    return {
        "name": "One Snap at a Time",
        "draft_format": "snake",
        "third_round_reversal": False,
        "team_count": 3,
        "round_count": 2,
        "user_slot": 3,
        "team_names": ["CPU One", "CPU Two", "Your Team"],
        "seed": "2026072801",
        "randomness": 35,
        "strategy_key": "balanced",
        "fallback_archetypes": {"1": "balanced", "2": "qb_priority"},
        **overrides,
    }


def _create_mock(
    client: TestClient,
    board_id: str,
    **overrides: object,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/boards/{board_id}/mock-sessions",
        json=_mock_payload(**overrides),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _cpu_pick(
    client: TestClient,
    mock: dict[str, object],
):
    current = mock["draft"]["current_pick"]
    assert isinstance(current, dict)
    return client.post(
        f"/api/v1/mock-sessions/{mock['draft']['id']}/cpu-pick",
        json={
            "draft_revision": mock["draft"]["revision"],
            "mock_revision": mock["mock"]["revision"],
            "expected_overall_pick": current["overall_pick"],
            "expected_selecting_slot": current["selecting_slot"],
        },
    )


def test_one_cpu_request_saves_one_reproducible_pick_and_audit(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board = _seed_board(client)
        first_mock = _create_mock(client, board["id"])
        replay_mock = _create_mock(client, board["id"], name="Replay")

        first_response = _cpu_pick(client, first_mock)
        replay_response = _cpu_pick(client, replay_mock)
        assert first_response.status_code == 200, first_response.text
        assert replay_response.status_code == 200, replay_response.text
        advanced = first_response.json()
        replay = replay_response.json()

        assert advanced["draft"]["revision"] == 1
        assert advanced["mock"]["revision"] == 1
        assert advanced["draft"]["active_pick_count"] == 1
        assert advanced["draft"]["current_pick"]["overall_pick"] == 2
        assert advanced["draft"]["current_pick"]["selecting_slot"] == 2
        assert advanced["can_advance_cpu"] is True
        decision = advanced["last_cpu_decision"]
        replay_decision = replay["last_cpu_decision"]
        assert decision["overall_pick"] == 1
        assert decision["selecting_slot"] == 1
        assert decision["decision_status"] == "active"
        assert decision["manually_corrected"] is False
        assert decision["limitation_codes"] == [
            "FALLBACK_PROFILE_NO_HISTORY",
            "LEAGUE_SHAPE_UNAVAILABLE",
            "MARKET_BASELINE_UNAVAILABLE",
            "NOT_MARKET_EVIDENCE",
        ]
        assert decision["chosen_player_id"] == replay_decision["chosen_player_id"]
        assert decision["total_score"] == replay_decision["total_score"]
        assert decision["component_scores"] == replay_decision["component_scores"]
        assert PRIVATE_NOTE not in first_response.text
        assert "provider_key" not in first_response.text
        assert "adp" not in first_response.text.lower()

        audit_response = client.get(
            f"/api/v1/mock-sessions/{advanced['draft']['id']}"
            "/decisions/1"
        )
        assert audit_response.status_code == 200
        audit = audit_response.json()
        replay_audit = client.get(
            f"/api/v1/mock-sessions/{replay['draft']['id']}/decisions/1"
        ).json()
        assert audit["chosen_player_id"] == decision["chosen_player_id"]
        assert len(audit["alternatives"]) <= 5
        assert audit["random_audit"] == replay_audit["random_audit"]
        assert isinstance(audit["random_audit"]["numerator"], str)
        assert PRIVATE_NOTE not in audit_response.text

        first_session_id = advanced["draft"]["id"]
        with app.state.session_factory() as database:
            configuration = database.scalar(
                select(MockConfigurationRow).where(
                    MockConfigurationRow.draft_session_id == first_session_id
                )
            )
            assert configuration is not None
            assert database.scalar(
                select(func.count())
                .select_from(DraftPickRevisionRow)
                .where(DraftPickRevisionRow.session_id == first_session_id)
            ) == 1
            assert database.scalar(
                select(func.count())
                .select_from(MockPickDecisionRow)
                .where(
                    MockPickDecisionRow.mock_configuration_id == configuration.id
                )
            ) == 1

    with TestClient(
        create_app(runtime_settings), headers=TRUSTED_HEADERS
    ) as restarted_client:
        restored = restarted_client.get(
            f"/api/v1/mock-sessions/{first_session_id}"
        )
        assert restored.status_code == 200
        second_response = _cpu_pick(restarted_client, restored.json())
        assert second_response.status_code == 200, second_response.text
        after_second = second_response.json()
        assert after_second["draft"]["revision"] == 2
        assert after_second["mock"]["revision"] == 2
        assert after_second["draft"]["active_pick_count"] == 2
        assert after_second["draft"]["current_pick"]["selecting_slot"] == 3
        assert after_second["last_cpu_decision"]["overall_pick"] == 2
        assert after_second["can_advance_cpu"] is False


def test_cpu_guards_reject_user_live_paused_and_stale_requests(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board = _seed_board(client)
        user_first = _create_mock(
            client,
            board["id"],
            user_slot=1,
            team_names=["Your Team", "CPU Two", "CPU Three"],
            fallback_archetypes={"2": "balanced", "3": "balanced"},
        )
        rejected_user = _cpu_pick(client, user_first)
        assert rejected_user.status_code == 409
        assert rejected_user.json()["error"]["code"] == "MOCK.USER_SLOT"

        cpu_first = _create_mock(client, board["id"], name="Guarded CPU")
        session_id = cpu_first["draft"]["id"]
        stale_mock = client.post(
            f"/api/v1/mock-sessions/{session_id}/cpu-pick",
            json={
                "draft_revision": 0,
                "mock_revision": 1,
                "expected_overall_pick": 1,
                "expected_selecting_slot": 1,
            },
        )
        assert stale_mock.status_code == 409
        assert stale_mock.json()["error"]["code"] == "MOCK.STALE_REVISION"

        stale_pick = client.post(
            f"/api/v1/mock-sessions/{session_id}/cpu-pick",
            json={
                "draft_revision": 0,
                "mock_revision": 0,
                "expected_overall_pick": 2,
                "expected_selecting_slot": 1,
            },
        )
        assert stale_pick.status_code == 409
        assert stale_pick.json()["error"]["code"] == "MOCK.STALE_CURRENT_PICK"

        stale_slot = client.post(
            f"/api/v1/mock-sessions/{session_id}/cpu-pick",
            json={
                "draft_revision": 0,
                "mock_revision": 0,
                "expected_overall_pick": 1,
                "expected_selecting_slot": 2,
            },
        )
        assert stale_slot.status_code == 409
        assert stale_slot.json()["error"]["code"] == "MOCK.STALE_CURRENT_SLOT"

        stale_draft = client.post(
            f"/api/v1/mock-sessions/{session_id}/cpu-pick",
            json={
                "draft_revision": 1,
                "mock_revision": 0,
                "expected_overall_pick": 1,
                "expected_selecting_slot": 1,
            },
        )
        assert stale_draft.status_code == 409
        assert stale_draft.json()["error"]["code"] == "DRAFT.STALE_REVISION"

        missing_decision = client.get(
            f"/api/v1/mock-sessions/{session_id}/decisions/1"
        )
        assert missing_decision.status_code == 404
        assert missing_decision.json()["error"]["code"] == (
            "MOCK.DECISION_NOT_FOUND"
        )

        paused = client.patch(
            f"/api/v1/draft-sessions/{session_id}",
            json={"revision": 0, "status": "paused"},
        )
        assert paused.status_code == 200
        rejected_paused = client.post(
            f"/api/v1/mock-sessions/{session_id}/cpu-pick",
            json={
                "draft_revision": 1,
                "mock_revision": 0,
                "expected_overall_pick": 1,
                "expected_selecting_slot": 1,
            },
        )
        assert rejected_paused.status_code == 409
        assert rejected_paused.json()["error"]["code"] == "MOCK.NOT_ACTIVE"

        live = client.post(
            f"/api/v1/boards/{board['id']}/draft-sessions",
            json={
                "name": "Live Draft",
                "mode": "live",
                "team_count": 2,
                "round_count": 1,
                "user_slot": 2,
            },
        )
        assert live.status_code == 201
        rejected_live = client.post(
            f"/api/v1/mock-sessions/{live.json()['id']}/cpu-pick",
            json={
                "draft_revision": 0,
                "mock_revision": 0,
                "expected_overall_pick": 1,
                "expected_selecting_slot": 1,
            },
        )
        assert rejected_live.status_code == 409
        assert rejected_live.json()["error"]["code"] == "MOCK.LIVE_SESSION"

        unsupported = _create_mock(client, board["id"], name="Future Engine")
        with app.state.session_factory() as database:
            configuration = database.scalar(
                select(MockConfigurationRow).where(
                    MockConfigurationRow.draft_session_id
                    == unsupported["draft"]["id"]
                )
            )
            assert configuration is not None
            configuration.cpu_engine_version = "future-engine-v2"
            database.commit()
        rejected_version = _cpu_pick(client, unsupported)
        assert rejected_version.status_code == 409
        assert rejected_version.json()["error"]["code"] == (
            "MOCK.VERSION_UNSUPPORTED"
        )

        with app.state.session_factory() as database:
            assert database.scalar(
                select(func.count())
                .select_from(MockPickDecisionRow)
            ) == 0


def test_cpu_decision_failure_rolls_back_both_revisions(
    runtime_settings: RuntimeSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board = _seed_board(client)
        mock = _create_mock(client, board["id"])
        session_id = mock["draft"]["id"]

        def fail_after_revisions(**kwargs):
            raise RuntimeError("injected decision-audit failure")

        monkeypatch.setattr(
            "friendly_hub.domains.mocks.service._build_cpu_decision_row",
            fail_after_revisions,
        )
        with app.state.session_factory() as database:
            with pytest.raises(RuntimeError, match="decision-audit"):
                advance_cpu_pick(
                    database,
                    session_id,
                    MockCpuPickCreate(
                        draft_revision=0,
                        mock_revision=0,
                        expected_overall_pick=1,
                        expected_selecting_slot=1,
                    ),
                )

        with app.state.session_factory() as database:
            configuration = database.scalar(
                select(MockConfigurationRow).where(
                    MockConfigurationRow.draft_session_id == session_id
                )
            )
            assert configuration is not None
            assert configuration.revision == 0
            first_pick = database.scalar(
                select(DraftPickRow).where(
                    DraftPickRow.session_id == session_id,
                    DraftPickRow.overall_pick == 1,
                )
            )
            assert first_pick is not None
            assert first_pick.player_id is None
            assert database.scalar(
                select(func.count())
                .select_from(DraftPickRevisionRow)
                .where(DraftPickRevisionRow.session_id == session_id)
            ) == 0
            assert database.scalar(
                select(func.count()).select_from(MockPickDecisionRow)
            ) == 0
