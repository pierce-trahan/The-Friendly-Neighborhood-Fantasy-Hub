from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.domains.mocks.models import (
    MockConfigurationRow,
    MockGuidanceEventRow,
    MockStrategyRevisionRow,
)
from friendly_hub.domains.mocks.schemas import MockStrategyPivotCreate
from friendly_hub.domains.mocks.strategy_service import pivot_strategy
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}
PRIVATE_NOTE = "Local pivot note that must never leave SQLite"


def _seed_board(client: TestClient) -> dict[str, object]:
    preview = client.post("/api/v1/player-imports/fixture/preview")
    assert preview.status_code == 201
    assert client.post(
        f"/api/v1/player-imports/{preview.json()['id']}/commit"
    ).status_code == 200
    players = client.get("/api/v1/players", params={"limit": 100}).json()["items"]
    board = client.post(
        "/api/v1/boards",
        json={"name": "Strategy Board", "scope": "overall"},
    ).json()
    for player in players[:3]:
        board = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": player["id"]},
        ).json()
    first_entry = board["entries"][0]
    response = client.patch(
        f"/api/v1/boards/{board['id']}/entries/{first_entry['id']}",
        json={"note": "Private strategy-room note"},
    )
    assert response.status_code == 200
    return response.json()


def _create_mock(client: TestClient, board_id: str, *, name: str = "Hero RB Lab"):
    response = client.post(
        f"/api/v1/boards/{board_id}/mock-sessions",
        json={
            "name": name,
            "team_count": 3,
            "round_count": 8,
            "user_slot": 3,
            "team_names": ["CPU One", "CPU Two", "Your Team"],
            "seed": "87",
            "randomness": 20,
            "strategy_key": "hero_rb",
            "fallback_archetypes": {"1": "balanced", "2": "balanced"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _advance_cpu(client: TestClient, mock: dict[str, object]):
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


def _make_user_pick(client: TestClient, mock: dict[str, object]):
    candidates = client.get(
        f"/api/v1/draft-sessions/{mock['draft']['id']}/candidates",
        params={"view": "blind", "include_drafted": False},
    )
    assert candidates.status_code == 200
    player_id = candidates.json()["items"][0]["player_id"]
    current = mock["draft"]["current_pick"]
    response = client.post(
        f"/api/v1/draft-sessions/{mock['draft']['id']}/picks",
        json={
            "revision": mock["draft"]["revision"],
            "expected_overall_pick": current["overall_pick"],
            "player_id": player_id,
        },
    )
    assert response.status_code == 200, response.text


def test_user_pick_checkpoint_pivot_history_and_guidance_status(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board = _seed_board(client)
        mock = _create_mock(client, board["id"])
        assert mock["current_checkpoint"]["state"] == "watch"
        assert mock["current_checkpoint"]["strategy_key"] == "hero_rb"

        mock = _advance_cpu(client, mock)
        mock = _advance_cpu(client, mock)
        assert mock["draft"]["current_pick"]["selecting_slot"] == 3
        _make_user_pick(client, mock)
        refreshed = client.get(
            f"/api/v1/mock-sessions/{mock['draft']['id']}"
        ).json()
        assert refreshed["draft"]["revision"] == 3
        assert refreshed["mock"]["revision"] == 3
        assert refreshed["user_roster_counts"]["TOTAL"] == 1
        assert refreshed["current_checkpoint"]["effective_overall_pick"] == 4

        pivot = client.patch(
            f"/api/v1/mock-sessions/{mock['draft']['id']}/strategy",
            json={
                "mock_revision": 3,
                "expected_current_overall_pick": 4,
                "strategy_key": "productive_struggle",
                "private_user_note": PRIVATE_NOTE,
            },
        )
        assert pivot.status_code == 200, pivot.text
        pivoted = pivot.json()
        assert pivoted["mock"]["revision"] == 4
        assert pivoted["mock"]["current_strategy_key"] == "productive_struggle"
        assert pivoted["current_strategy_revision"]["sequence_number"] == 2
        assert pivoted["current_strategy_revision"]["reason"] == "user_pivot"
        assert pivoted["current_strategy_revision"][
            "previous_strategy_key"
        ] == "hero_rb"
        assert pivoted["current_strategy_revision"][
            "effective_overall_pick"
        ] == 4
        assert pivoted["current_checkpoint"]["strategy_key"] == (
            "productive_struggle"
        )
        assert pivoted["current_checkpoint"]["confidence"] == "low"
        assert PRIVATE_NOTE not in pivot.text
        assert "player_id" not in str(pivoted["current_checkpoint"])

        guidance = client.get(
            f"/api/v1/mock-sessions/{mock['draft']['id']}/guidance",
            params={"limit": 2},
        )
        assert guidance.status_code == 200
        page = guidance.json()
        assert page["total"] == 3
        assert len(page["items"]) == 2
        assert page["items"][0]["strategy_key"] == "productive_struggle"
        assert any(item["strategy_key"] == "hero_rb" for item in page["items"])
        final_page = client.get(
            f"/api/v1/mock-sessions/{mock['draft']['id']}/guidance",
            params={"limit": 2, "offset": 2},
        )
        assert final_page.status_code == 200
        assert len(final_page.json()["items"]) == 1

        event_id = pivoted["current_checkpoint"]["id"]
        dismissed = client.patch(
            f"/api/v1/mock-sessions/{mock['draft']['id']}/guidance/{event_id}",
            json={"mock_revision": 4, "status": "dismissed"},
        )
        assert dismissed.status_code == 200
        assert dismissed.json()["mock"]["revision"] == 5
        assert dismissed.json()["current_checkpoint"]["status"] == "dismissed"
        assert dismissed.json()["current_checkpoint"]["resolved_at"] is not None

        reopened = client.patch(
            f"/api/v1/mock-sessions/{mock['draft']['id']}/guidance/{event_id}",
            json={"mock_revision": 5, "status": "open"},
        )
        assert reopened.status_code == 200
        assert reopened.json()["mock"]["revision"] == 6
        assert reopened.json()["current_checkpoint"]["resolved_at"] is None

        stale_guidance = client.patch(
            f"/api/v1/mock-sessions/{mock['draft']['id']}/guidance/{event_id}",
            json={"mock_revision": 5, "status": "dismissed"},
        )
        assert stale_guidance.status_code == 409
        assert stale_guidance.json()["error"]["code"] == "MOCK.STALE_REVISION"

        unchanged_guidance = client.patch(
            f"/api/v1/mock-sessions/{mock['draft']['id']}/guidance/{event_id}",
            json={"mock_revision": 6, "status": "open"},
        )
        assert unchanged_guidance.status_code == 409
        assert unchanged_guidance.json()["error"]["code"] == (
            "MOCK.GUIDANCE_STATUS_UNCHANGED"
        )

        missing_guidance = client.patch(
            f"/api/v1/mock-sessions/{mock['draft']['id']}/guidance/missing-event",
            json={"mock_revision": 6, "status": "dismissed"},
        )
        assert missing_guidance.status_code == 404
        assert missing_guidance.json()["error"]["code"] == (
            "MOCK.GUIDANCE_NOT_FOUND"
        )

        stale = client.patch(
            f"/api/v1/mock-sessions/{mock['draft']['id']}/strategy",
            json={
                "mock_revision": 5,
                "expected_current_overall_pick": 4,
                "strategy_key": "balanced",
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "MOCK.STALE_REVISION"

        unchanged_strategy = client.patch(
            f"/api/v1/mock-sessions/{mock['draft']['id']}/strategy",
            json={
                "mock_revision": 6,
                "expected_current_overall_pick": 4,
                "strategy_key": "productive_struggle",
            },
        )
        assert unchanged_strategy.status_code == 409
        assert unchanged_strategy.json()["error"]["code"] == (
            "MOCK.STRATEGY_UNCHANGED"
        )

        incompatible = client.patch(
            f"/api/v1/mock-sessions/{mock['draft']['id']}/strategy",
            json={
                "mock_revision": 6,
                "expected_current_overall_pick": 4,
                "strategy_key": "early_qb_superflex",
            },
        )
        assert incompatible.status_code == 409
        assert incompatible.json()["error"]["code"] == (
            "MOCK.STRATEGY_INCOMPATIBLE"
        )

        with app.state.session_factory() as database:
            revisions = list(
                database.scalars(
                    select(MockStrategyRevisionRow)
                    .where(
                        MockStrategyRevisionRow.mock_configuration_id
                        == database.scalar(
                            select(MockConfigurationRow.id).where(
                                MockConfigurationRow.draft_session_id
                                == mock["draft"]["id"]
                            )
                        )
                    )
                    .order_by(MockStrategyRevisionRow.sequence_number)
                )
            )
            assert len(revisions) == 2
            assert revisions[1].private_user_note == PRIVATE_NOTE
        session_id = mock["draft"]["id"]

    with TestClient(
        create_app(runtime_settings), headers=TRUSTED_HEADERS
    ) as restarted_client:
        restored = restarted_client.get(f"/api/v1/mock-sessions/{session_id}")
        assert restored.status_code == 200
        assert restored.json()["mock"]["current_strategy_key"] == (
            "productive_struggle"
        )
        assert restored.json()["current_checkpoint"]["status"] == "open"
        assert PRIVATE_NOTE not in restored.text


def test_paused_pivot_is_allowed_and_failure_rolls_back(
    runtime_settings: RuntimeSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board = _seed_board(client)
        paused_mock = _create_mock(client, board["id"], name="Paused Pivot")
        paused = client.patch(
            f"/api/v1/draft-sessions/{paused_mock['draft']['id']}",
            json={"revision": 0, "status": "paused"},
        )
        assert paused.status_code == 200
        pivoted = client.patch(
            f"/api/v1/mock-sessions/{paused_mock['draft']['id']}/strategy",
            json={
                "mock_revision": 0,
                "expected_current_overall_pick": 1,
                "strategy_key": "balanced",
            },
        )
        assert pivoted.status_code == 200, pivoted.text
        assert pivoted.json()["draft"]["status"] == "paused"
        assert pivoted.json()["mock"]["revision"] == 1

        rollback_mock = _create_mock(client, board["id"], name="Rollback Pivot")
        rollback_id = rollback_mock["draft"]["id"]

        def fail_guidance(*args, **kwargs):
            raise RuntimeError("injected guidance failure")

        monkeypatch.setattr(
            "friendly_hub.domains.mocks.strategy_service._add_guidance_event",
            fail_guidance,
        )
        with app.state.session_factory() as database:
            with pytest.raises(RuntimeError, match="guidance failure"):
                pivot_strategy(
                    database,
                    rollback_id,
                    MockStrategyPivotCreate(
                        mock_revision=0,
                        expected_current_overall_pick=1,
                        strategy_key="balanced",
                    ),
                )

        with app.state.session_factory() as database:
            configuration = database.scalar(
                select(MockConfigurationRow).where(
                    MockConfigurationRow.draft_session_id == rollback_id
                )
            )
            assert configuration is not None
            assert configuration.revision == 0
            assert configuration.current_strategy_key == "hero_rb"
            assert database.scalar(
                select(func.count())
                .select_from(MockStrategyRevisionRow)
                .where(
                    MockStrategyRevisionRow.mock_configuration_id
                    == configuration.id
                )
            ) == 1
            assert database.scalar(
                select(func.count())
                .select_from(MockGuidanceEventRow)
                .where(
                    MockGuidanceEventRow.mock_configuration_id == configuration.id
                )
            ) == 1
