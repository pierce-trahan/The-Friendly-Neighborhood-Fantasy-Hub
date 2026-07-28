from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.domains.drafts.models import DraftSessionRow
from friendly_hub.domains.mocks.models import (
    MockConfigurationRow,
    MockCpuProfileRow,
    MockGuidanceEventRow,
    MockStrategyRevisionRow,
)
from friendly_hub.domains.mocks.schemas import MockSessionCreate
from friendly_hub.domains.mocks.service import create_mock_session
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}
PRIVATE_NOTE = "Private director's-cut board note"


def _seed_board(
    client: TestClient,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    preview = client.post("/api/v1/player-imports/fixture/preview")
    assert preview.status_code == 201
    committed = client.post(
        f"/api/v1/player-imports/{preview.json()['id']}/commit"
    )
    assert committed.status_code == 200
    players_response = client.get("/api/v1/players", params={"limit": 100})
    assert players_response.status_code == 200
    players = players_response.json()["items"]

    board_response = client.post(
        "/api/v1/boards",
        json={"name": "Mock Creation Board", "scope": "overall"},
    )
    assert board_response.status_code == 201
    board = board_response.json()
    for player in players[:3]:
        entry_response = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": player["id"]},
        )
        assert entry_response.status_code == 200
        board = entry_response.json()

    first_entry_id = board["entries"][0]["id"]
    note_response = client.patch(
        f"/api/v1/boards/{board['id']}/entries/{first_entry_id}",
        json={"note": PRIVATE_NOTE, "favorite": True},
    )
    assert note_response.status_code == 200
    return note_response.json(), players


def _payload(**overrides: object) -> dict[str, object]:
    return {
        "name": "Strategy Rehearsal",
        "draft_format": "snake",
        "third_round_reversal": False,
        "team_count": 4,
        "round_count": 3,
        "user_slot": 2,
        "team_names": ["CPU 1", "Your Team", "CPU 3", "CPU 4"],
        "seed": "2026072801",
        "randomness": 35,
        "strategy_key": "hero_rb",
        "include_in_learning": False,
        **overrides,
    }


def test_mock_creation_is_atomic_deterministic_and_restart_safe(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board, _ = _seed_board(client)
        first = client.post(
            f"/api/v1/boards/{board['id']}/mock-sessions",
            json=_payload(),
        )
        second = client.post(
            f"/api/v1/boards/{board['id']}/mock-sessions",
            json=_payload(name="Replay"),
        )
        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text
        created = first.json()
        replay = second.json()

        assert created["practice_simulation"] is True
        assert created["draft"]["mode"] == "mock"
        assert created["draft"]["revision"] == 0
        assert created["mock"]["revision"] == 0
        assert created["mock"]["seed"] == "2026072801"
        assert created["mock"]["strategy_compatibility"] == "reduced"
        assert created["mock"]["strategy_limitations"] == [
            "LEAGUE_SHAPE_UNAVAILABLE"
        ]
        assert created["mock"]["include_in_learning"] is False
        assert created["mock"]["learning_opted_in_at"] is None
        assert created["current_strategy_revision"]["sequence_number"] == 1
        assert created["current_checkpoint"]["state"] == "on_plan"
        assert [profile["draft_slot"] for profile in created["cpu_profiles"]] == [
            1,
            3,
            4,
        ]
        assert all(
            profile["source"] == "fallback"
            and profile["confidence"] == "not_applicable"
            for profile in created["cpu_profiles"]
        )
        assert created["mock"]["content_fingerprint"] == replay["mock"][
            "content_fingerprint"
        ]
        assert [
            profile["archetype_key"] for profile in created["cpu_profiles"]
        ] == [
            profile["archetype_key"] for profile in replay["cpu_profiles"]
        ]
        assert PRIVATE_NOTE not in first.text
        assert "provider_key" not in first.text
        session_id = created["draft"]["id"]

        with app.state.session_factory() as session:
            configuration = session.scalar(
                select(MockConfigurationRow).where(
                    MockConfigurationRow.draft_session_id == session_id
                )
            )
            assert configuration is not None
            assert session.scalar(
                select(func.count())
                .select_from(MockCpuProfileRow)
                .where(
                    MockCpuProfileRow.mock_configuration_id == configuration.id
                )
            ) == 3
            assert session.scalar(
                select(func.count())
                .select_from(MockStrategyRevisionRow)
                .where(
                    MockStrategyRevisionRow.mock_configuration_id
                    == configuration.id
                )
            ) == 1
            assert session.scalar(
                select(func.count())
                .select_from(MockGuidanceEventRow)
                .where(
                    MockGuidanceEventRow.mock_configuration_id == configuration.id
                )
            ) == 1

    with TestClient(
        create_app(runtime_settings), headers=TRUSTED_HEADERS
    ) as restarted_client:
        restored = restarted_client.get(f"/api/v1/mock-sessions/{session_id}")
        assert restored.status_code == 200
        assert restored.json()["mock"]["content_fingerprint"] == created["mock"][
            "content_fingerprint"
        ]


def test_creation_validates_strategy_archetypes_seed_and_league_shape(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(
        create_app(runtime_settings), headers=TRUSTED_HEADERS
    ) as client:
        board, _ = _seed_board(client)
        board_id = board["id"]

        unknown_strategy = client.post(
            f"/api/v1/boards/{board_id}/mock-sessions",
            json=_payload(strategy_key="magic_beans"),
        )
        assert unknown_strategy.status_code == 422

        unknown_archetype = client.post(
            f"/api/v1/boards/{board_id}/mock-sessions",
            json=_payload(fallback_archetypes={"1": "mystery"}),
        )
        assert unknown_archetype.status_code == 422

        user_profile = client.post(
            f"/api/v1/boards/{board_id}/mock-sessions",
            json=_payload(fallback_archetypes={"2": "balanced"}),
        )
        assert user_profile.status_code == 422

        invalid_seed = client.post(
            f"/api/v1/boards/{board_id}/mock-sessions",
            json=_payload(seed=str(1 << 64)),
        )
        assert invalid_seed.status_code == 422

        incompatible = client.post(
            f"/api/v1/boards/{board_id}/mock-sessions",
            json=_payload(strategy_key="early_qb_superflex"),
        )
        assert incompatible.status_code == 409
        assert incompatible.json()["error"]["code"] == "MOCK.STRATEGY_INCOMPATIBLE"

        imported = client.post("/api/v1/league-profiles/samples/entropy")
        assert imported.status_code == 201
        compatible = client.post(
            f"/api/v1/boards/{board_id}/mock-sessions",
            json=_payload(
                team_count=10,
                user_slot=4,
                team_names=None,
                league_profile_id=imported.json()["id"],
                strategy_key="early_qb_superflex",
                fallback_archetypes={"1": "qb_priority"},
                include_in_learning=True,
            ),
        )
        assert compatible.status_code == 201, compatible.text
        body = compatible.json()
        assert body["mock"]["strategy_compatibility"] == "compatible"
        assert body["mock"]["include_in_learning"] is True
        assert body["mock"]["learning_opted_in_at"] is not None
        assert len(body["cpu_profiles"]) == 9
        assert body["cpu_profiles"][0]["archetype_key"] == "qb_priority"
        assert "provider_key" not in compatible.text

        timeline_limited = client.post(
            f"/api/v1/boards/{board_id}/mock-sessions",
            json=_payload(
                league_profile_id=imported.json()["id"],
                strategy_key="win_now",
            ),
        )
        assert timeline_limited.status_code == 201, timeline_limited.text
        assert timeline_limited.json()["current_checkpoint"][
            "state"
        ] == "insufficient_evidence"
        assert timeline_limited.json()["mock"]["strategy_limitations"] == [
            "LEAGUE_TEAM_COUNT_DIFFERS",
            "TIMELINE_EVIDENCE_UNAVAILABLE",
        ]


def test_failure_after_phase3_rows_rolls_back_the_whole_mock(
    runtime_settings: RuntimeSettings,
    monkeypatch,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board, _ = _seed_board(client)

        def fail_after_phase3(*args, **kwargs):
            raise RuntimeError("injected Phase 4 failure")

        monkeypatch.setattr(
            "friendly_hub.domains.mocks.service._add_mock_rows",
            fail_after_phase3,
        )
        with app.state.session_factory() as session:
            try:
                create_mock_session(
                    session,
                    board["id"],
                    MockSessionCreate.model_validate(_payload()),
                )
            except RuntimeError as error:
                assert str(error) == "injected Phase 4 failure"
            else:
                raise AssertionError("the injected failure should escape")

        with app.state.session_factory() as session:
            assert session.scalar(
                select(func.count()).select_from(DraftSessionRow)
            ) == 0
            assert session.scalar(
                select(func.count()).select_from(MockConfigurationRow)
            ) == 0
