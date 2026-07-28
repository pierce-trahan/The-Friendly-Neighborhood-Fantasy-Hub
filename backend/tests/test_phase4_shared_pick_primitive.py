from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from friendly_hub.core.errors import HubError
from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.drafts.models import (
    DraftCandidateRow,
    DraftPickRevisionRow,
    DraftPickRow,
    DraftSessionRow,
)
from friendly_hub.domains.drafts.service import (
    DraftPickMutation,
    record_pick_in_transaction,
)
from friendly_hub.domains.mocks.models import (
    MockConfigurationRow,
    MockPickDecisionRow,
)
from friendly_hub.domains.players.models import PlayerRow
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}


def _seed_draft(
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
        json={"name": "Primitive Board", "scope": "overall"},
    )
    assert board_response.status_code == 201
    board = board_response.json()
    for player in players[:3]:
        board = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": player["id"]},
        ).json()

    draft_response = client.post(
        f"/api/v1/boards/{board['id']}/draft-sessions",
        json={
            "name": "Primitive Draft",
            "mode": "mock",
            "draft_format": "snake",
            "team_count": 2,
            "round_count": 2,
            "user_slot": 2,
            "team_names": ["CPU", "Your Team"],
        },
    )
    assert draft_response.status_code == 201
    return draft_response.json(), players


def _revision_count(database: Session, session_id: str) -> int:
    return (
        database.scalar(
            select(func.count())
            .select_from(DraftPickRevisionRow)
            .where(DraftPickRevisionRow.session_id == session_id)
        )
        or 0
    )


def _add_mock_configuration(database: Session, draft_id: str) -> None:
    database.add(
        MockConfigurationRow(
            id="mock-config-1",
            draft_session_id=draft_id,
            seed="42",
            rng_version="sha256-counter-v1",
            cpu_engine_version="practice-board-v1",
            strategy_definition_version="strategy-v1",
            league_shape_json="{}",
            league_shape_source_timestamp=None,
            content_fingerprint="a" * 64,
            randomness=35,
            current_strategy_key="balanced",
            revision=0,
            include_in_learning=False,
            learning_opted_in_at=None,
            learning_withdrawn_at=None,
            created_at=utc_now_text(),
            updated_at=utc_now_text(),
        )
    )
    database.commit()


def _decision_row(
    mutation: DraftPickMutation,
    *,
    decision_id: str,
    profile_source: str = "fallback",
) -> MockPickDecisionRow:
    return MockPickDecisionRow(
        id=decision_id,
        mock_configuration_id="mock-config-1",
        draft_pick_revision_id=mutation.pick_revision.id,
        overall_pick=mutation.pick.overall_pick,
        selecting_slot=mutation.pick.selecting_slot,
        chosen_player_id=mutation.candidate.player_id,
        profile_source=profile_source,
        profile_archetype_key="balanced",
        engine_version="practice-board-v1",
        rng_version="sha256-counter-v1",
        total_score=100,
        component_scores_json="{}",
        random_audit_json="{}",
        alternatives_json="[]",
        reason_codes_json="[]",
        limitation_codes_json="[]",
        created_at=utc_now_text(),
    )


def test_shared_pick_primitive_defers_commit_and_returns_audit_rows(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        draft, players = _seed_draft(client)
        player_id = str(players[0]["id"])
        current_pick = draft["current_pick"]
        assert isinstance(current_pick, dict)

        with app.state.session_factory() as database:
            mutation = record_pick_in_transaction(
                database,
                str(draft["id"]),
                revision=0,
                expected_overall_pick=1,
                expected_selecting_slot=1,
                player_id=player_id,
                client_entered_at="2026-07-28T08:00:00-05:00",
            )
            assert mutation.draft_session.revision == 1
            assert mutation.pick.overall_pick == 1
            assert mutation.pick.player_id == player_id
            assert mutation.pick_revision.action_kind == "made"
            assert mutation.pick_revision.next_player_id == player_id
            assert mutation.candidate.player_id == player_id
            database.rollback()

        unchanged = client.get(
            f"/api/v1/draft-sessions/{draft['id']}"
        ).json()
        assert unchanged["revision"] == 0
        assert unchanged["active_pick_count"] == 0

        with app.state.session_factory() as database:
            _add_mock_configuration(database, str(draft["id"]))
        with app.state.session_factory() as database:
            mutation = record_pick_in_transaction(
                database,
                str(draft["id"]),
                revision=0,
                expected_overall_pick=1,
                expected_selecting_slot=1,
                player_id=player_id,
            )
            audit_id = mutation.pick_revision.id
            decision_id = "decision-1"
            database.add(
                _decision_row(
                    mutation,
                    decision_id=decision_id,
                )
            )
            database.commit()

        saved = client.get(f"/api/v1/draft-sessions/{draft['id']}").json()
        assert saved["revision"] == 1
        assert saved["active_pick_count"] == 1
        assert saved["picks"][0]["player_id"] == player_id
        with app.state.session_factory() as database:
            assert database.get(DraftPickRevisionRow, audit_id) is not None
            assert database.get(MockPickDecisionRow, decision_id) is not None
            assert _revision_count(database, str(draft["id"])) == 1


def test_shared_pick_guards_roll_back_late_additions_and_stale_actions(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        draft, players = _seed_draft(client)
        draft_id = str(draft["id"])
        late_player_id = str(uuid4())
        with app.state.session_factory() as database:
            now = utc_now_text()
            database.add(
                PlayerRow(
                    id=late_player_id,
                    display_name="Rollback Prospect",
                    first_name="Rollback",
                    last_name="Prospect",
                    suffix=None,
                    search_name="rollback prospect",
                    team=None,
                    primary_position="RB",
                    fantasy_positions_json='["RB"]',
                    status="active",
                    rookie_class=2026,
                    is_rookie=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            database.commit()

        with app.state.session_factory() as database:
            with pytest.raises(HubError) as wrong_pick:
                record_pick_in_transaction(
                    database,
                    draft_id,
                    revision=0,
                    expected_overall_pick=2,
                    expected_selecting_slot=1,
                    player_id=late_player_id,
                )
            assert wrong_pick.value.code == "DRAFT.STALE_CURRENT_PICK"
            database.rollback()

        with app.state.session_factory() as database:
            with pytest.raises(HubError) as wrong_slot:
                record_pick_in_transaction(
                    database,
                    draft_id,
                    revision=0,
                    expected_overall_pick=1,
                    expected_selecting_slot=2,
                    player_id=late_player_id,
                )
            assert wrong_slot.value.code == "DRAFT.STALE_CURRENT_SLOT"
            database.rollback()

        with app.state.session_factory() as database:
            _add_mock_configuration(database, draft_id)
        with app.state.session_factory() as database:
            mutation = record_pick_in_transaction(
                database,
                draft_id,
                revision=0,
                expected_overall_pick=1,
                expected_selecting_slot=1,
                player_id=late_player_id,
            )
            database.add(
                _decision_row(
                    mutation,
                    decision_id="invalid-decision",
                    profile_source="invalid",
                )
            )
            with pytest.raises(IntegrityError):
                database.commit()
            database.rollback()

        with app.state.session_factory() as database:
            late_candidate = database.scalar(
                select(DraftCandidateRow).where(
                    DraftCandidateRow.session_id == draft_id,
                    DraftCandidateRow.player_id == late_player_id,
                )
            )
            assert late_candidate is None
            assert database.get(DraftSessionRow, draft_id).revision == 0
            first_pick = database.scalar(
                select(DraftPickRow).where(
                    DraftPickRow.session_id == draft_id,
                    DraftPickRow.overall_pick == 1,
                )
            )
            assert first_pick is not None
            assert first_pick.player_id is None
            assert _revision_count(database, draft_id) == 0
            assert database.get(MockPickDecisionRow, "invalid-decision") is None

        committed = client.post(
            f"/api/v1/draft-sessions/{draft_id}/picks",
            json={
                "revision": 0,
                "expected_overall_pick": 1,
                "player_id": players[0]["id"],
            },
        )
        assert committed.status_code == 200
        with app.state.session_factory() as database:
            with pytest.raises(HubError) as stale:
                record_pick_in_transaction(
                    database,
                    draft_id,
                    revision=0,
                    expected_overall_pick=2,
                    expected_selecting_slot=2,
                    player_id=str(players[1]["id"]),
                )
            assert stale.value.code == "DRAFT.STALE_REVISION"
            database.rollback()
        unchanged = client.get(f"/api/v1/draft-sessions/{draft_id}").json()
        assert unchanged["revision"] == 1
        assert unchanged["active_pick_count"] == 1
