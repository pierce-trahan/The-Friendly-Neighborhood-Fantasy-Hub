from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.alerts import evaluation_service
from friendly_hub.domains.alerts.models import (
    DraftAlertEvaluationRow,
    DraftAlertEventRow,
    DraftAlertTradeReferenceRow,
)
from friendly_hub.domains.drafts.models import (
    DraftCandidateRow,
    DraftPickRow,
    DraftSessionRow,
)
from friendly_hub.domains.players.models import PlayerRow
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}
PRIVATE_MARKERS = {
    "configuration-private-reference",
    "demo-qb-001",
    "demo-rb-001",
    "demo-wr-001",
    "demo-te-001",
    "demo-wr-002",
    "demo-rb-002",
    "Private evaluation note",
    "probability",
    "fairness",
    "ownership",
}


def _fixture_root() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _seed_workspace(
    client: TestClient,
) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    preview = client.post("/api/v1/player-imports/fixture/preview")
    assert preview.status_code == 201
    committed = client.post(f"/api/v1/player-imports/{preview.json()['id']}/commit")
    assert committed.status_code == 200
    players = client.get("/api/v1/players", params={"limit": 100}).json()["items"]

    board_response = client.post(
        "/api/v1/boards",
        json={"name": "Phase 5 Evaluation Board", "scope": "overall"},
    )
    assert board_response.status_code == 201
    board = board_response.json()
    for player in players:
        response = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": player["id"]},
        )
        assert response.status_code == 200

    profile_response = client.post("/api/v1/league-profiles/samples/entropy")
    assert profile_response.status_code == 201
    return board, profile_response.json(), players


def _create_draft(
    client: TestClient,
    board_id: str,
    profile_id: str,
    *,
    mode: str = "live",
) -> dict[str, object]:
    if mode == "mock":
        response = client.post(
            f"/api/v1/boards/{board_id}/mock-sessions",
            json={
                "name": "Phase 5 Evaluation Mock",
                "league_profile_id": profile_id,
                "draft_format": "snake",
                "third_round_reversal": True,
                "team_count": 10,
                "round_count": 24,
                "user_slot": 1,
                "seed": "55070",
                "randomness": 0,
                "strategy_key": "hero_rb",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["draft"]
    response = client.post(
        f"/api/v1/boards/{board_id}/draft-sessions",
        json={
            "name": "Phase 5 Evaluation Draft",
            "mode": "live",
            "league_profile_id": profile_id,
            "draft_format": "snake",
            "third_round_reversal": True,
            "team_count": 10,
            "round_count": 24,
            "user_slot": 1,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _evidence_payload(
    *,
    include_pick_curve: bool = True,
    evidence_as_of: str = "2026-07-28T00:00:00Z",
) -> dict[str, object]:
    evidence_root = _fixture_root() / "alert_evidence"
    player_csv = (evidence_root / "player-signals.synthetic.csv").read_text(encoding="utf-8")
    player_csv = player_csv.replace(",55,80,", ",55,60,").replace(
        "2026-07-28T00:00:00Z",
        evidence_as_of,
    )
    payload: dict[str, object] = {
        "player_filename": "player-signals.synthetic.csv",
        "player_csv_text": player_csv,
        "metadata": {
            "snapshot_key": f"phase-5-evaluation-{uuid4()}",
            "source_label": "Neighborhood Synthetic Market",
            "source_kind": "synthetic",
            "source_namespace": "sanitized_fixture",
            "permitted_use_confirmed": True,
            "private_source_reference": "configuration-private-reference",
            "as_of": evidence_as_of,
            "league_type": "dynasty",
            "draft_purpose": "startup",
            "team_count": 10,
            "draft_format": "snake",
            "third_round_reversal": True,
            "round_count": 24,
            "quarterback_mode": "superflex",
            "reception_scoring": "ppr",
            "tight_end_premium": True,
            "supported_draft_depth": 240,
        },
    }
    if include_pick_curve:
        pick_csv = (evidence_root / "pick-values.synthetic.csv").read_text(encoding="utf-8")
        payload.update(
            {
                "pick_filename": "pick-values.synthetic.csv",
                "pick_csv_text": pick_csv.replace(
                    "2026-07-28T00:00:00Z",
                    evidence_as_of,
                ),
            }
        )
    return payload


def _commit_evidence(
    client: TestClient,
    *,
    include_pick_curve: bool = True,
    evidence_as_of: str = "2026-07-28T00:00:00Z",
) -> dict[str, object]:
    preview = client.post(
        "/api/v1/alert-evidence-imports/preview",
        json=_evidence_payload(
            include_pick_curve=include_pick_curve,
            evidence_as_of=evidence_as_of,
        ),
    )
    assert preview.status_code == 201, preview.text
    committed = client.post(
        f"/api/v1/alert-evidence-imports/{preview.json()['id']}/commit",
        json={
            "content_hash": preview.json()["content_hash"],
            "permitted_use_confirmed": True,
        },
    )
    assert committed.status_code == 200, committed.text
    return committed.json()["snapshot"]


def _attach(
    client: TestClient,
    draft: dict[str, object],
    snapshot_id: str,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/draft-sessions/{draft['id']}/alert-configuration",
        json={
            "draft_revision": draft["revision"],
            "evidence_snapshot_id": snapshot_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _advance_to_pick_55(
    client: TestClient,
    draft_id: str,
) -> dict[str, str]:
    now = utc_now_text()
    with client.app.state.session_factory() as session:
        draft = session.get(DraftSessionRow, draft_id)
        assert draft is not None
        candidates = list(
            session.scalars(
                select(DraftCandidateRow).where(DraftCandidateRow.session_id == draft_id)
            )
        )
        by_name = {candidate.display_name: candidate for candidate in candidates}
        theo = by_name["Theo Banks"]
        andre = by_name["Andre Vale III"]
        theo.tier_order = 1
        theo.favorite = True
        theo.board_note = "Private evaluation note"
        andre.tier_order = 2
        andre.favorite = False

        dummy_ids: list[str] = []
        dummy_rows: list[tuple[str, str, int]] = []
        for number in range(1, 55):
            player_id = str(uuid4())
            dummy_ids.append(player_id)
            display_name = f"Fictional Pick {number:02d}"
            dummy_rows.append((player_id, display_name, number))
            session.add(
                PlayerRow(
                    id=player_id,
                    display_name=display_name,
                    first_name="Fictional",
                    last_name=f"Pick {number:02d}",
                    suffix=None,
                    search_name=display_name.lower(),
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
        session.flush()
        for player_id, display_name, number in dummy_rows:
            session.add(
                DraftCandidateRow(
                    id=str(uuid4()),
                    session_id=draft_id,
                    player_id=player_id,
                    display_name=display_name,
                    search_name=display_name.lower(),
                    primary_position="WR",
                    fantasy_positions_json='["WR"]',
                    team=None,
                    player_status="active",
                    is_rookie=False,
                    rookie_class=None,
                    snapshot_source="test_fixture",
                    manual_rank=1000 + number,
                    tier_name=None,
                    tier_color=None,
                    tier_order=None,
                    favorite=False,
                    board_note=None,
                    created_at=now,
                )
            )
        session.flush()
        picks = list(
            session.scalars(
                select(DraftPickRow)
                .where(DraftPickRow.session_id == draft_id)
                .order_by(DraftPickRow.overall_pick)
                .limit(54)
            )
        )
        assert len(picks) == 54
        for pick, player_id in zip(picks, dummy_ids, strict=True):
            pick.player_id = player_id
            pick.recorded_at = now
        draft.revision = 54
        draft.updated_at = now
        session.commit()
        return {"theo": theo.player_id, "andre": andre.player_id}


def _evaluate(
    client: TestClient,
    draft_id: str,
    *,
    draft_revision: int,
    configuration_revision: int = 0,
    current_pick: int | None = 55,
    last_evaluation_revision: int | None = None,
):
    return client.post(
        f"/api/v1/draft-sessions/{draft_id}/alerts/evaluate",
        json={
            "draft_revision": draft_revision,
            "configuration_revision": configuration_revision,
            "expected_current_overall_pick": current_pick,
            "last_evaluation_draft_revision": last_evaluation_revision,
        },
    )


def test_evaluation_is_idempotent_revision_safe_and_privacy_safe(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board, profile, _players = _seed_workspace(client)
        draft = _create_draft(client, str(board["id"]), str(profile["id"]))
        candidate_ids = _advance_to_pick_55(client, str(draft["id"]))
        snapshot = _commit_evidence(client)
        _attach(
            client,
            {**draft, "revision": 54},
            str(snapshot["id"]),
        )

        stale_draft = _evaluate(
            client,
            str(draft["id"]),
            draft_revision=53,
        )
        assert stale_draft.status_code == 409
        assert stale_draft.json()["error"]["code"] == "ALERT_DRAFT_STALE_REVISION"
        stale_configuration = _evaluate(
            client,
            str(draft["id"]),
            draft_revision=54,
            configuration_revision=1,
        )
        assert stale_configuration.status_code == 409
        assert stale_configuration.json()["error"]["code"] == "ALERT_CONFIGURATION_STALE_REVISION"
        stale_pick = _evaluate(
            client,
            str(draft["id"]),
            draft_revision=54,
            current_pick=54,
        )
        assert stale_pick.status_code == 409
        assert stale_pick.json()["error"]["code"] == "ALERT_EVALUATION_STALE"

        evaluated = _evaluate(client, str(draft["id"]), draft_revision=54)
        assert evaluated.status_code == 200, evaluated.text
        body = evaluated.json()
        assert body["evaluation"]["idempotent"] is False
        assert body["evaluation"]["draft_revision"] == 54
        assert body["evaluation"]["configuration_revision"] == 0
        assert body["evaluation"]["current_overall_pick"] == 55
        assert body["evaluation"]["next_user_pick"] == 70
        assert body["evaluation"]["opened_count"] == 4
        assert body["evaluation"]["updated_count"] == 0
        assert body["evaluation"]["superseded_count"] == 0

        groups = {item["player"]["display_name"]: item for item in body["alerts"]["items"]}
        assert set(groups) == {"Theo Banks", "Andre Vale III"}
        assert {event["kind"] for event in groups["Theo Banks"]["events"]} == {
            "value_watch",
            "return_risk",
        }
        assert {event["kind"] for event in groups["Andre Vale III"]["events"]} == {
            "return_risk",
            "trade_up_window",
        }
        first_page = client.get(
            f"/api/v1/draft-sessions/{draft['id']}/alerts",
            params={"limit": 1, "offset": 0},
        )
        second_page = client.get(
            f"/api/v1/draft-sessions/{draft['id']}/alerts",
            params={"limit": 1, "offset": 1},
        )
        assert first_page.status_code == second_page.status_code == 200
        assert first_page.json()["total"] == second_page.json()["total"] == 2
        assert len(first_page.json()["items"]) == 1
        assert len(second_page.json()["items"]) == 1
        assert (
            first_page.json()["items"][0]["player"]["id"]
            != second_page.json()["items"][0]["player"]["id"]
        )

        stale_client = _evaluate(
            client,
            str(draft["id"]),
            draft_revision=54,
        )
        assert stale_client.status_code == 409
        assert stale_client.json()["error"]["code"] == "ALERT_EVALUATION_STALE"

        repeated = _evaluate(
            client,
            str(draft["id"]),
            draft_revision=54,
            last_evaluation_revision=54,
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["evaluation"]["idempotent"] is True
        assert repeated.json()["evaluation"]["id"] == body["evaluation"]["id"]

        with app.state.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(DraftAlertEvaluationRow)) == 1
            assert session.scalar(select(func.count()).select_from(DraftAlertEventRow)) == 4

        trade_event = next(
            event
            for event in groups["Andre Vale III"]["events"]
            if event["kind"] == "trade_up_window"
        )
        detail = client.get(f"/api/v1/draft-sessions/{draft['id']}/alerts/{trade_event['id']}")
        assert detail.status_code == 200, detail.text
        trade = detail.json()["trade_reference"]
        assert trade["target_pick_window"] == {"low": 55, "high": 58}
        assert trade["cost_availability"] == "available"
        assert trade["pick_only_references"]
        assert all(
            "asset_key" not in reference and reference["label"].startswith("Year ")
            for reference in trade["pick_only_references"]
        )
        assert "FUTURE_DISCOUNT_ASSUMPTION" in trade["limitation_codes"]
        assert all(marker.lower() not in detail.text.lower() for marker in PRIVATE_MARKERS)
        assert '"player_id"' not in detail.text
        assert "make_pick" not in detail.text
        assert "execute_trade" not in detail.text

        picked = client.post(
            f"/api/v1/draft-sessions/{draft['id']}/picks",
            json={
                "revision": 54,
                "expected_overall_pick": 55,
                "player_id": candidate_ids["theo"],
            },
        )
        assert picked.status_code == 200, picked.text
        after_pick = _evaluate(
            client,
            str(draft["id"]),
            draft_revision=55,
            current_pick=56,
            last_evaluation_revision=54,
        )
        assert after_pick.status_code == 200, after_pick.text
        assert after_pick.json()["evaluation"]["superseded_count"] == 2

        undone = client.post(
            f"/api/v1/draft-sessions/{draft['id']}/undo",
            json={"revision": 55},
        )
        assert undone.status_code == 200, undone.text
        after_undo = _evaluate(
            client,
            str(draft["id"]),
            draft_revision=56,
            current_pick=55,
            last_evaluation_revision=55,
        )
        assert after_undo.status_code == 200, after_undo.text
        assert after_undo.json()["evaluation"]["opened_count"] == 2
        updated_trade = client.get(
            f"/api/v1/draft-sessions/{draft['id']}/alerts/{trade_event['id']}"
        )
        assert updated_trade.status_code == 200
        assert updated_trade.json()["original_evidence"]["draft_revision"] == 54
        assert updated_trade.json()["current_evidence"]["draft_revision"] == 56
        assert updated_trade.json()["event"]["first_confirmed_draft_revision"] == 54
        assert updated_trade.json()["event"]["last_confirmed_draft_revision"] == 56
        history = client.get(
            f"/api/v1/draft-sessions/{draft['id']}/alerts",
            params={"scope": "history", "limit": 100},
        )
        assert history.status_code == 200
        theo_history = next(
            item
            for item in history.json()["items"]
            if item["player"]["id"] == candidate_ids["theo"]
        )
        assert {event["status"] for event in theo_history["events"]} == {
            "open",
            "superseded",
        }

        blind = client.get(
            f"/api/v1/draft-sessions/{draft['id']}/candidates",
            params={"view": "blind", "limit": 100},
        )
        assert blind.status_code == 200
        assert all(
            "favorite" not in item and "board_note" not in item for item in blind.json()["items"]
        )
        exported = client.get(f"/api/v1/draft-sessions/{draft['id']}/export.csv")
        assert exported.status_code == 200
        assert "alert" not in exported.text.lower()
        assert "Neighborhood Synthetic Market" not in exported.text
        assert "Private evaluation note" not in exported.text


def test_evaluation_rolls_back_and_missing_pick_curve_is_non_blocking(
    runtime_settings: RuntimeSettings,
    monkeypatch,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board, profile, _players = _seed_workspace(client)
        draft = _create_draft(client, str(board["id"]), str(profile["id"]))
        _advance_to_pick_55(client, str(draft["id"]))
        snapshot = _commit_evidence(client, include_pick_curve=False)
        _attach(client, {**draft, "revision": 54}, str(snapshot["id"]))

        original_commit = evaluation_service._commit_transaction

        def fail_commit(_session) -> None:
            raise RuntimeError("synthetic commit failure")

        monkeypatch.setattr(
            evaluation_service,
            "_commit_transaction",
            fail_commit,
        )
        failed = _evaluate(client, str(draft["id"]), draft_revision=54)
        assert failed.status_code == 500
        assert failed.json()["error"]["code"] == "ALERT_EVALUATION_FAILED"
        with app.state.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(DraftAlertEvaluationRow)) == 0
            assert session.scalar(select(func.count()).select_from(DraftAlertEventRow)) == 0
            assert (
                session.scalar(select(func.count()).select_from(DraftAlertTradeReferenceRow)) == 0
            )
            saved = session.get(DraftSessionRow, str(draft["id"]))
            assert saved is not None
            assert saved.revision == 54

        monkeypatch.setattr(
            evaluation_service,
            "_commit_transaction",
            original_commit,
        )
        evaluated = _evaluate(client, str(draft["id"]), draft_revision=54)
        assert evaluated.status_code == 200, evaluated.text
        trade_event = next(
            event
            for item in evaluated.json()["alerts"]["items"]
            for event in item["events"]
            if event["kind"] == "trade_up_window"
        )
        detail = client.get(f"/api/v1/draft-sessions/{draft['id']}/alerts/{trade_event['id']}")
        assert detail.status_code == 200
        trade = detail.json()["trade_reference"]
        assert trade["cost_availability"] == "unavailable"
        assert trade["incremental_cost"] is None
        assert trade["pick_only_references"] == []
        assert "PICK_CURVE_UNAVAILABLE" in trade["limitation_codes"]


def test_expired_evidence_warns_without_actionable_alerts(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(
        create_app(runtime_settings),
        headers=TRUSTED_HEADERS,
    ) as client:
        board, profile, _players = _seed_workspace(client)
        draft = _create_draft(client, str(board["id"]), str(profile["id"]))
        _advance_to_pick_55(client, str(draft["id"]))
        with client.app.state.session_factory() as session:
            nolan = session.scalar(
                select(DraftCandidateRow).where(
                    DraftCandidateRow.session_id == draft["id"],
                    DraftCandidateRow.display_name == "Nolan Reed",
                )
            )
            assert nolan is not None
            nolan.favorite = True
            session.commit()
        snapshot = _commit_evidence(
            client,
            evidence_as_of="2025-01-01T00:00:00Z",
        )
        _attach(client, {**draft, "revision": 54}, str(snapshot["id"]))

        evaluated = _evaluate(client, str(draft["id"]), draft_revision=54)
        assert evaluated.status_code == 200, evaluated.text
        events = [event for item in evaluated.json()["alerts"]["items"] for event in item["events"]]
        assert events
        assert {event["kind"] for event in events} == {"evidence_warning"}
        assert {event["freshness"] for event in events} == {"expired"}
        assert {event["confidence"] for event in events} == {"unavailable"}
        nolan_event = next(
            event
            for item in evaluated.json()["alerts"]["items"]
            if item["player"]["display_name"] == "Nolan Reed"
            for event in item["events"]
        )
        assert nolan_event["evidence"]["expected_selection"] is None
        assert "EXPECTED_SELECTION_UNAVAILABLE" in nolan_event["limitation_codes"]


def test_mock_strategy_state_is_fingerprinted_without_exposing_private_note(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(
        create_app(runtime_settings),
        headers=TRUSTED_HEADERS,
    ) as client:
        board, profile, _players = _seed_workspace(client)
        draft = _create_draft(
            client,
            str(board["id"]),
            str(profile["id"]),
            mode="mock",
        )
        _advance_to_pick_55(client, str(draft["id"]))
        snapshot = _commit_evidence(client)
        _attach(client, {**draft, "revision": 54}, str(snapshot["id"]))

        first = _evaluate(client, str(draft["id"]), draft_revision=54)
        assert first.status_code == 200, first.text
        first_evaluation_id = first.json()["evaluation"]["id"]
        first_event = first.json()["alerts"]["items"][0]["events"][0]
        assert first_event["evidence"]["components"]["strategy_fit"] == {
            "state": "available",
            "band": "hero_rb",
            "reasons": [],
        }

        pivoted = client.patch(
            f"/api/v1/mock-sessions/{draft['id']}/strategy",
            json={
                "mock_revision": 0,
                "expected_current_overall_pick": 55,
                "strategy_key": "productive_struggle",
                "private_user_note": "Private strategy pivot note",
            },
        )
        assert pivoted.status_code == 200, pivoted.text
        second = _evaluate(
            client,
            str(draft["id"]),
            draft_revision=54,
            last_evaluation_revision=54,
        )
        assert second.status_code == 200, second.text
        assert second.json()["evaluation"]["id"] != first_evaluation_id
        assert second.json()["evaluation"]["updated_count"] == 4
        second_event = second.json()["alerts"]["items"][0]["events"][0]
        assert second_event["evidence"]["components"]["strategy_fit"] == {
            "state": "available",
            "band": "productive_struggle",
            "reasons": [],
        }
        assert "Private strategy pivot note" not in second.text


def test_restart_reconciles_one_missing_evaluation(
    runtime_settings: RuntimeSettings,
) -> None:
    app = create_app(runtime_settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        board, profile, _players = _seed_workspace(client)
        draft = _create_draft(client, str(board["id"]), str(profile["id"]))
        _advance_to_pick_55(client, str(draft["id"]))
        snapshot = _commit_evidence(client)
        _attach(client, {**draft, "revision": 54}, str(snapshot["id"]))
        before = client.get(f"/api/v1/draft-sessions/{draft['id']}/alerts")
        assert before.status_code == 200
        assert before.json()["evaluation_state"] == "missing"
        draft_id = str(draft["id"])

    with TestClient(
        create_app(runtime_settings),
        headers=TRUSTED_HEADERS,
    ) as client:
        reconciled = _evaluate(client, draft_id, draft_revision=54)
        assert reconciled.status_code == 200, reconciled.text
        evaluation_id = reconciled.json()["evaluation"]["id"]

    with TestClient(
        create_app(runtime_settings),
        headers=TRUSTED_HEADERS,
    ) as client:
        restored = client.get(f"/api/v1/draft-sessions/{draft_id}/alerts")
        assert restored.status_code == 200
        assert restored.json()["evaluation_state"] == "current"
        repeated = _evaluate(
            client,
            draft_id,
            draft_revision=54,
            last_evaluation_revision=54,
        )
        assert repeated.status_code == 200
        assert repeated.json()["evaluation"]["id"] == evaluation_id
        assert repeated.json()["evaluation"]["idempotent"] is True
        with client.app.state.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(DraftAlertEvaluationRow)) == 1
