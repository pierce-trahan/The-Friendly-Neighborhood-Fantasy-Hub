from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_phase5_alert_evaluation_api import (
    TRUSTED_HEADERS,
    _advance_to_pick_55,
    _attach,
    _commit_evidence,
    _create_draft,
    _evaluate,
    _seed_workspace,
)

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.alerts import configuration_service, lifecycle_service
from friendly_hub.domains.alerts.models import (
    DraftAlertConfigurationRevisionRow,
    DraftAlertConfigurationRow,
    DraftAlertEvaluationRow,
    DraftAlertEventRow,
)
from friendly_hub.domains.drafts.models import DraftSessionRow
from friendly_hub.domains.players.models import PlayerRow
from friendly_hub.main import create_app


def _event(
    body: dict[str, object],
    *,
    player_name: str,
    kind: str,
    status: str | None = None,
) -> dict[str, object]:
    matches = [
        event
        for item in body["items"]
        if item["player"]["display_name"] == player_name
        for event in item["events"]
        if event["kind"] == kind and (status is None or event["status"] == status)
    ]
    assert matches
    return max(matches, key=lambda item: (item["updated_at"], item["id"]))


def _patch_event(
    client: TestClient,
    *,
    draft_id: str,
    event_id: str,
    configuration_revision: int,
    expected_status: str,
    status: str,
):
    return client.patch(
        f"/api/v1/draft-sessions/{draft_id}/alerts/{event_id}",
        json={
            "configuration_revision": configuration_revision,
            "expected_status": expected_status,
            "status": status,
        },
    )


def _add_local_players(
    client: TestClient,
    count: int,
) -> list[str]:
    now = utc_now_text()
    player_ids = []
    with client.app.state.session_factory() as session:
        for number in range(count):
            player_id = str(uuid4())
            player_ids.append(player_id)
            session.add(
                PlayerRow(
                    id=player_id,
                    display_name=f"Lifecycle Reserve {number + 1}",
                    first_name="Lifecycle",
                    last_name=f"Reserve {number + 1}",
                    suffix=None,
                    search_name=f"lifecycle reserve {number + 1}",
                    team=None,
                    primary_position="WR",
                    fantasy_positions_json='["WR"]',
                    status="active",
                    rookie_class=None,
                    is_rookie=False,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.commit()
    return player_ids


def _make_picks(
    client: TestClient,
    *,
    draft_id: str,
    revision: int,
    current_pick: int,
    player_ids: list[str],
) -> dict[str, object]:
    latest: dict[str, object] = {}
    for player_id in player_ids:
        response = client.post(
            f"/api/v1/draft-sessions/{draft_id}/picks",
            json={
                "revision": revision,
                "expected_overall_pick": current_pick,
                "player_id": player_id,
            },
        )
        assert response.status_code == 200, response.text
        latest = response.json()
        revision = int(latest["revision"])
        current = latest["current_pick"]
        assert isinstance(current, dict)
        current_pick = int(current["overall_pick"])
    return latest


def _setup_evaluated_draft(
    client: TestClient,
) -> dict[str, object]:
    board, profile, players = _seed_workspace(client)
    draft = _create_draft(client, str(board["id"]), str(profile["id"]))
    candidate_ids = _advance_to_pick_55(client, str(draft["id"]))
    snapshot = _commit_evidence(client)
    configuration = _attach(
        client,
        {**draft, "revision": 54},
        str(snapshot["id"]),
    )
    evaluated = _evaluate(client, str(draft["id"]), draft_revision=54)
    assert evaluated.status_code == 200, evaluated.text
    return {
        "board": board,
        "profile": profile,
        "players": players,
        "draft": {**draft, "revision": 54},
        "candidate_ids": candidate_ids,
        "snapshot": snapshot,
        "configuration": configuration,
        "evaluation": evaluated.json(),
    }


def test_lifecycle_guards_undo_expiry_disable_and_correction(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        setup = _setup_evaluated_draft(client)
        draft_id = str(setup["draft"]["id"])
        candidate_ids = setup["candidate_ids"]
        initial_alerts = setup["evaluation"]["alerts"]
        theo_value = _event(
            initial_alerts,
            player_name="Theo Banks",
            kind="value_watch",
        )
        andre_trade = _event(
            initial_alerts,
            player_name="Andre Vale III",
            kind="trade_up_window",
        )

        dismissed = _patch_event(
            client,
            draft_id=draft_id,
            event_id=str(theo_value["id"]),
            configuration_revision=0,
            expected_status="open",
            status="dismissed",
        )
        assert dismissed.status_code == 200, dismissed.text
        assert dismissed.json()["event"]["status"] == "dismissed"
        assert dismissed.json()["event"]["dismissed_at"] is not None

        stale = _patch_event(
            client,
            draft_id=draft_id,
            event_id=str(theo_value["id"]),
            configuration_revision=0,
            expected_status="open",
            status="snoozed",
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "ALERT_EVENT_STALE_STATUS"
        invalid_transition = _patch_event(
            client,
            draft_id=draft_id,
            event_id=str(theo_value["id"]),
            configuration_revision=0,
            expected_status="dismissed",
            status="snoozed",
        )
        assert invalid_transition.status_code == 409

        reopened = _patch_event(
            client,
            draft_id=draft_id,
            event_id=str(theo_value["id"]),
            configuration_revision=0,
            expected_status="dismissed",
            status="open",
        )
        assert reopened.status_code == 200
        assert reopened.json()["event"]["dismissed_at"] is None

        snoozed = _patch_event(
            client,
            draft_id=draft_id,
            event_id=str(andre_trade["id"]),
            configuration_revision=0,
            expected_status="open",
            status="snoozed",
        )
        assert snoozed.status_code == 200, snoozed.text
        assert snoozed.json()["event"]["snooze_boundary"] == 60
        current = client.get(f"/api/v1/draft-sessions/{draft_id}/alerts")
        assert current.status_code == 200
        assert all(
            event["id"] != andre_trade["id"]
            for item in current.json()["items"]
            for event in item["events"]
        )

        picked = client.post(
            f"/api/v1/draft-sessions/{draft_id}/picks",
            json={
                "revision": 54,
                "expected_overall_pick": 55,
                "player_id": candidate_ids["andre"],
            },
        )
        assert picked.status_code == 200, picked.text
        after_pick = _evaluate(
            client,
            draft_id,
            draft_revision=55,
            current_pick=56,
            last_evaluation_revision=54,
        )
        assert after_pick.status_code == 200, after_pick.text
        old_trade = client.get(f"/api/v1/draft-sessions/{draft_id}/alerts/{andre_trade['id']}")
        assert old_trade.status_code == 200
        assert old_trade.json()["event"]["status"] == "superseded"
        assert old_trade.json()["event"]["snooze_boundary"] == 60

        undone = client.post(
            f"/api/v1/draft-sessions/{draft_id}/undo",
            json={"revision": 55},
        )
        assert undone.status_code == 200, undone.text
        after_undo = _evaluate(
            client,
            draft_id,
            draft_revision=56,
            current_pick=55,
            last_evaluation_revision=55,
        )
        assert after_undo.status_code == 200, after_undo.text
        history = client.get(
            f"/api/v1/draft-sessions/{draft_id}/alerts",
            params={"scope": "history", "limit": 100},
        )
        assert history.status_code == 200
        regenerated_trade = _event(
            history.json(),
            player_name="Andre Vale III",
            kind="trade_up_window",
            status="snoozed",
        )
        assert regenerated_trade["id"] != andre_trade["id"]
        assert regenerated_trade["snooze_boundary"] == 60

        manually_reopened = _patch_event(
            client,
            draft_id=draft_id,
            event_id=str(regenerated_trade["id"]),
            configuration_revision=0,
            expected_status="snoozed",
            status="open",
        )
        assert manually_reopened.status_code == 200
        snoozed_again = _patch_event(
            client,
            draft_id=draft_id,
            event_id=str(regenerated_trade["id"]),
            configuration_revision=0,
            expected_status="open",
            status="snoozed",
        )
        assert snoozed_again.status_code == 200
        assert snoozed_again.json()["event"]["snooze_boundary"] == 60

        reserves = _add_local_players(client, 7)
        after_five = _make_picks(
            client,
            draft_id=draft_id,
            revision=56,
            current_pick=55,
            player_ids=reserves[:5],
        )
        assert after_five["revision"] == 61
        expired = _evaluate(
            client,
            draft_id,
            draft_revision=61,
            current_pick=60,
            last_evaluation_revision=56,
        )
        assert expired.status_code == 200, expired.text
        reopened_trade = client.get(
            f"/api/v1/draft-sessions/{draft_id}/alerts/{regenerated_trade['id']}"
        )
        assert reopened_trade.status_code == 200
        assert reopened_trade.json()["event"]["status"] == "open"
        assert reopened_trade.json()["event"]["snooze_boundary"] is None

        dismissed_again = _patch_event(
            client,
            draft_id=draft_id,
            event_id=str(regenerated_trade["id"]),
            configuration_revision=0,
            expected_status="open",
            status="dismissed",
        )
        assert dismissed_again.status_code == 200
        disabled = client.patch(
            f"/api/v1/draft-sessions/{draft_id}/alert-configuration",
            json={
                "draft_revision": 61,
                "configuration_revision": 0,
                "enabled": False,
            },
        )
        assert disabled.status_code == 200, disabled.text
        assert disabled.json()["revision"] == 1
        disabled_evaluation = _evaluate(
            client,
            draft_id,
            draft_revision=61,
            configuration_revision=1,
            current_pick=60,
            last_evaluation_revision=61,
        )
        assert disabled_evaluation.status_code == 200
        assert disabled_evaluation.json()["alerts"]["items"] == []

        enabled = client.patch(
            f"/api/v1/draft-sessions/{draft_id}/alert-configuration",
            json={
                "draft_revision": 61,
                "configuration_revision": 1,
                "enabled": True,
            },
        )
        assert enabled.status_code == 200
        enabled_evaluation = _evaluate(
            client,
            draft_id,
            draft_revision=61,
            configuration_revision=2,
            current_pick=60,
            last_evaluation_revision=61,
        )
        assert enabled_evaluation.status_code == 200, enabled_evaluation.text
        refreshed_history = client.get(
            f"/api/v1/draft-sessions/{draft_id}/alerts",
            params={"scope": "history", "limit": 100},
        )
        carried_dismissal = _event(
            refreshed_history.json(),
            player_name="Andre Vale III",
            kind="trade_up_window",
            status="dismissed",
        )
        assert carried_dismissal["id"] != regenerated_trade["id"]
        assert all(
            event["id"] != carried_dismissal["id"]
            for item in enabled_evaluation.json()["alerts"]["items"]
            for event in item["events"]
        )
        stale_configuration = _patch_event(
            client,
            draft_id=draft_id,
            event_id=str(carried_dismissal["id"]),
            configuration_revision=1,
            expected_status="dismissed",
            status="open",
        )
        assert stale_configuration.status_code == 409
        assert stale_configuration.json()["error"]["code"] == "ALERT_CONFIGURATION_STALE_REVISION"
        carried_reopened = _patch_event(
            client,
            draft_id=draft_id,
            event_id=str(carried_dismissal["id"]),
            configuration_revision=2,
            expected_status="dismissed",
            status="open",
        )
        assert carried_reopened.status_code == 200

        theo_before = {
            event["id"]
            for item in enabled_evaluation.json()["alerts"]["items"]
            if item["player"]["display_name"] == "Theo Banks"
            for event in item["events"]
        }
        theo_pick = client.post(
            f"/api/v1/draft-sessions/{draft_id}/picks",
            json={
                "revision": 61,
                "expected_overall_pick": 60,
                "player_id": candidate_ids["theo"],
            },
        )
        assert theo_pick.status_code == 200, theo_pick.text
        after_theo_pick = _evaluate(
            client,
            draft_id,
            draft_revision=62,
            configuration_revision=2,
            current_pick=61,
            last_evaluation_revision=61,
        )
        assert after_theo_pick.status_code == 200
        corrected = client.patch(
            f"/api/v1/draft-sessions/{draft_id}/picks/60",
            json={
                "revision": 62,
                "expected_current_player_id": candidate_ids["theo"],
                "replacement_player_id": reserves[5],
            },
        )
        assert corrected.status_code == 200, corrected.text
        after_correction = _evaluate(
            client,
            draft_id,
            draft_revision=63,
            configuration_revision=2,
            current_pick=61,
            last_evaluation_revision=62,
        )
        assert after_correction.status_code == 200, after_correction.text
        theo_after = {
            event["id"]
            for item in after_correction.json()["alerts"]["items"]
            if item["player"]["display_name"] == "Theo Banks"
            for event in item["events"]
        }
        assert theo_after
        assert theo_before.isdisjoint(theo_after)


def test_reset_copy_is_explicit_history_safe_and_restart_safe(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        setup = _setup_evaluated_draft(client)
        draft_id = str(setup["draft"]["id"])
        initial = setup["evaluation"]["alerts"]
        event = _event(
            initial,
            player_name="Theo Banks",
            kind="value_watch",
        )
        dismissed = _patch_event(
            client,
            draft_id=draft_id,
            event_id=str(event["id"]),
            configuration_revision=0,
            expected_status="open",
            status="dismissed",
        )
        assert dismissed.status_code == 200

        reset = client.post(
            f"/api/v1/draft-sessions/{draft_id}/reset",
            json={
                "revision": 54,
                "copy_alert_configuration": True,
            },
        )
        assert reset.status_code == 201, reset.text
        replacement_id = reset.json()["id"]
        assert reset.json()["revision"] == 0

        old_current = client.get(f"/api/v1/draft-sessions/{draft_id}/alerts")
        assert old_current.status_code == 200
        assert old_current.json()["items"] == []
        old_history = client.get(
            f"/api/v1/draft-sessions/{draft_id}/alerts",
            params={"scope": "history", "limit": 100},
        )
        assert old_history.status_code == 200
        assert (
            _event(
                old_history.json(),
                player_name="Theo Banks",
                kind="value_watch",
                status="dismissed",
            )["id"]
            == event["id"]
        )
        reset_patch = _patch_event(
            client,
            draft_id=draft_id,
            event_id=str(event["id"]),
            configuration_revision=0,
            expected_status="dismissed",
            status="open",
        )
        assert reset_patch.status_code == 409
        assert reset_patch.json()["error"]["code"] == "ALERT_EVENT_STALE_STATUS"

        copied = client.get(f"/api/v1/draft-sessions/{replacement_id}/alert-configuration")
        assert copied.status_code == 200, copied.text
        copied_body = copied.json()
        assert copied_body["revision"] == 0
        assert copied_body["evidence_snapshot_id"] == setup["configuration"]["evidence_snapshot_id"]
        assert copied_body["enabled"] is True
        replacement_alerts = client.get(
            f"/api/v1/draft-sessions/{replacement_id}/alerts",
            params={"scope": "history"},
        )
        assert replacement_alerts.status_code == 200
        assert replacement_alerts.json()["evaluation_state"] == "missing"
        assert replacement_alerts.json()["items"] == []
        with app.state.session_factory() as session:
            replacement_configuration = session.scalar(
                select(DraftAlertConfigurationRow).where(
                    DraftAlertConfigurationRow.draft_session_id == replacement_id
                )
            )
            assert replacement_configuration is not None
            revisions = list(
                session.scalars(
                    select(DraftAlertConfigurationRevisionRow).where(
                        DraftAlertConfigurationRevisionRow.configuration_id
                        == replacement_configuration.id
                    )
                )
            )
            assert len(revisions) == 1
            assert revisions[0].reason == "reset_copy"
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(DraftAlertEvaluationRow)
                    .where(DraftAlertEvaluationRow.configuration_id == replacement_configuration.id)
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(DraftAlertEventRow)
                    .where(DraftAlertEventRow.configuration_id == replacement_configuration.id)
                )
                == 0
            )

        no_copy_source = _create_draft(
            client,
            str(setup["board"]["id"]),
            str(setup["profile"]["id"]),
        )
        _attach(
            client,
            no_copy_source,
            str(setup["snapshot"]["id"]),
        )
        no_copy = client.post(
            f"/api/v1/draft-sessions/{no_copy_source['id']}/reset",
            json={"revision": 0},
        )
        assert no_copy.status_code == 201
        absent = client.get(f"/api/v1/draft-sessions/{no_copy.json()['id']}/alert-configuration")
        assert absent.status_code == 404

    with TestClient(
        create_app(runtime_settings),
        headers=TRUSTED_HEADERS,
    ) as client:
        restored_old = client.get(
            f"/api/v1/draft-sessions/{draft_id}/alerts",
            params={"scope": "history", "limit": 100},
        )
        assert restored_old.status_code == 200
        assert (
            _event(
                restored_old.json(),
                player_name="Theo Banks",
                kind="value_watch",
                status="dismissed",
            )["id"]
            == event["id"]
        )
        restored_copy = client.get(f"/api/v1/draft-sessions/{replacement_id}/alert-configuration")
        assert restored_copy.status_code == 200
        assert restored_copy.json()["revision"] == 0


def test_reset_copy_failure_rolls_back_both_draft_and_alert_domains(
    runtime_settings: RuntimeSettings,
    monkeypatch,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(
        app,
        headers=TRUSTED_HEADERS,
        raise_server_exceptions=False,
    ) as client:
        setup = _setup_evaluated_draft(client)
        draft_id = str(setup["draft"]["id"])
        with app.state.session_factory() as session:
            draft_count = session.scalar(select(func.count()).select_from(DraftSessionRow))

        def fail_copy(*_args, **_kwargs):
            raise RuntimeError("synthetic alert copy failure")

        monkeypatch.setattr(
            configuration_service,
            "copy_alert_configuration_on_reset_in_transaction",
            fail_copy,
        )
        failed = client.post(
            f"/api/v1/draft-sessions/{draft_id}/reset",
            json={
                "revision": 54,
                "copy_alert_configuration": True,
            },
        )
        assert failed.status_code == 500
        with app.state.session_factory() as session:
            source = session.get(DraftSessionRow, draft_id)
            assert source is not None
            assert source.status == "active"
            assert source.revision == 54
            assert source.reset_at is None
            assert session.scalar(select(func.count()).select_from(DraftSessionRow)) == draft_count
            assert session.scalar(select(func.count()).select_from(DraftAlertConfigurationRow)) == 1


def test_paused_lifecycle_survives_restart(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        setup = _setup_evaluated_draft(client)
        draft_id = str(setup["draft"]["id"])
        event = _event(
            setup["evaluation"]["alerts"],
            player_name="Andre Vale III",
            kind="trade_up_window",
        )
        paused = client.patch(
            f"/api/v1/draft-sessions/{draft_id}",
            json={"revision": 54, "status": "paused"},
        )
        assert paused.status_code == 200
        assert paused.json()["revision"] == 55
        snoozed = _patch_event(
            client,
            draft_id=draft_id,
            event_id=str(event["id"]),
            configuration_revision=0,
            expected_status="open",
            status="snoozed",
        )
        assert snoozed.status_code == 200
        assert snoozed.json()["event"]["snooze_boundary"] == 60

    with TestClient(
        create_app(runtime_settings),
        headers=TRUSTED_HEADERS,
    ) as client:
        restored = client.get(f"/api/v1/draft-sessions/{draft_id}/alerts/{event['id']}")
        assert restored.status_code == 200
        assert restored.json()["event"]["status"] == "snoozed"
        assert restored.json()["event"]["snooze_boundary"] == 60
        current = client.get(f"/api/v1/draft-sessions/{draft_id}/alerts")
        assert current.status_code == 200
        assert all(
            item["id"] != event["id"]
            for group in current.json()["items"]
            for item in group["events"]
        )
        reopened = _patch_event(
            client,
            draft_id=draft_id,
            event_id=str(event["id"]),
            configuration_revision=0,
            expected_status="snoozed",
            status="open",
        )
        assert reopened.status_code == 200
        draft = client.get(f"/api/v1/draft-sessions/{draft_id}")
        assert draft.json()["status"] == "paused"
        assert draft.json()["revision"] == 55


def test_lifecycle_failure_rolls_back_without_touching_draft(
    runtime_settings: RuntimeSettings,
    monkeypatch,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(
        app,
        headers=TRUSTED_HEADERS,
        raise_server_exceptions=False,
    ) as client:
        setup = _setup_evaluated_draft(client)
        draft_id = str(setup["draft"]["id"])
        event = _event(
            setup["evaluation"]["alerts"],
            player_name="Theo Banks",
            kind="value_watch",
        )

        def fail_commit(_session) -> None:
            raise RuntimeError("synthetic lifecycle commit failure")

        monkeypatch.setattr(
            lifecycle_service,
            "_commit_transaction",
            fail_commit,
        )
        failed = _patch_event(
            client,
            draft_id=draft_id,
            event_id=str(event["id"]),
            configuration_revision=0,
            expected_status="open",
            status="dismissed",
        )
        assert failed.status_code == 500
        assert failed.json()["error"]["code"] == "ALERT_EVALUATION_FAILED"
        with app.state.session_factory() as session:
            saved_event = session.get(DraftAlertEventRow, str(event["id"]))
            saved_draft = session.get(DraftSessionRow, draft_id)
            assert saved_event is not None
            assert saved_event.status == "open"
            assert saved_event.dismissed_at is None
            assert saved_draft is not None
            assert saved_draft.status == "active"
            assert saved_draft.revision == 54


def test_alert_disable_does_not_change_mock_cpu_decision(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(
        create_app(runtime_settings),
        headers=TRUSTED_HEADERS,
    ) as client:
        board, profile, _players = _seed_workspace(client)
        snapshot = _commit_evidence(client)

        def create_mock(name: str) -> dict[str, object]:
            response = client.post(
                f"/api/v1/boards/{board['id']}/mock-sessions",
                json={
                    "name": name,
                    "league_profile_id": profile["id"],
                    "draft_format": "snake",
                    "third_round_reversal": True,
                    "team_count": 10,
                    "round_count": 24,
                    "user_slot": 10,
                    "seed": "8675309",
                    "randomness": 0,
                    "strategy_key": "hero_rb",
                },
            )
            assert response.status_code == 201, response.text
            return response.json()

        enabled_mock = create_mock("Alerts Enabled Mock")
        disabled_mock = create_mock("Alerts Disabled Mock")
        for mock in (enabled_mock, disabled_mock):
            _attach(
                client,
                mock["draft"],
                str(snapshot["id"]),
            )
        disabled = client.patch(
            (f"/api/v1/draft-sessions/{disabled_mock['draft']['id']}/alert-configuration"),
            json={
                "draft_revision": 0,
                "configuration_revision": 0,
                "enabled": False,
            },
        )
        assert disabled.status_code == 200

        def cpu_pick(mock: dict[str, object]):
            current = mock["draft"]["current_pick"]
            assert isinstance(current, dict)
            return client.post(
                f"/api/v1/mock-sessions/{mock['draft']['id']}/cpu-pick",
                json={
                    "draft_revision": 0,
                    "mock_revision": 0,
                    "expected_overall_pick": current["overall_pick"],
                    "expected_selecting_slot": current["selecting_slot"],
                },
            )

        enabled_pick = cpu_pick(enabled_mock)
        disabled_pick = cpu_pick(disabled_mock)
        assert enabled_pick.status_code == disabled_pick.status_code == 200
        enabled_body = enabled_pick.json()
        disabled_body = disabled_pick.json()
        assert (
            enabled_body["last_cpu_decision"]["chosen_player_id"]
            == disabled_body["last_cpu_decision"]["chosen_player_id"]
        )
        assert (
            enabled_body["last_cpu_decision"]["component_scores"]
            == disabled_body["last_cpu_decision"]["component_scores"]
        )
        assert enabled_body["draft"]["revision"] == 1
        assert disabled_body["draft"]["revision"] == 1
        assert enabled_body["mock"]["revision"] == 1
        assert disabled_body["mock"]["revision"] == 1
