from __future__ import annotations

import json
from time import perf_counter
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_phase4_live_workflow import (
    TOTAL_PICKS,
    USER_SLOT,
    _advance_cpu,
    _create_mock,
    _make_user_pick,
    _pick_sequence,
    _read_mock,
)
from test_phase5_alert_evaluation_api import (
    PRIVATE_MARKERS,
    TRUSTED_HEADERS,
    _attach,
    _evaluate,
    _evidence_payload,
    _seed_workspace,
)
from test_phase5_alert_lifecycle_api import _event, _patch_event

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.boards.models import BoardEntryRow
from friendly_hub.domains.drafts.models import DraftCandidateRow
from friendly_hub.domains.players.models import PlayerRow
from friendly_hub.main import create_app

TOTAL_PLAYERS = 260
TARGET_NAMES = {"Theo Banks", "Andre Vale III"}
PRIVATE_WORKFLOW_NOTE = "private-phase-5-live-workflow-note"


def _expand_board_for_full_mock(
    client: TestClient,
    *,
    board_id: str,
) -> dict[str, str]:
    now = utc_now_text()
    target_ids: dict[str, str] = {}
    with client.app.state.session_factory() as session:
        existing_entries = list(
            session.scalars(
                select(BoardEntryRow)
                .where(BoardEntryRow.board_id == board_id)
                .order_by(BoardEntryRow.manual_order)
            )
        )
        for entry in existing_entries:
            player = session.get(PlayerRow, entry.player_id)
            assert player is not None
            if player.display_name in TARGET_NAMES:
                entry.manual_order = 1000 + len(target_ids)
                entry.favorite = True
                entry.note = PRIVATE_WORKFLOW_NOTE
                target_ids[player.display_name] = player.id

        added_entries: list[BoardEntryRow] = []
        for number in range(1, TOTAL_PLAYERS - len(existing_entries) + 1):
            player_id = str(uuid4())
            position = ("QB", "RB", "WR", "WR", "TE")[(number - 1) % 5]
            display_name = f"Workflow Player {number:03d}"
            session.add(
                PlayerRow(
                    id=player_id,
                    display_name=display_name,
                    first_name="Workflow",
                    last_name=f"Player {number:03d}",
                    suffix=None,
                    search_name=display_name.casefold(),
                    team=f"T{number % 32:02d}",
                    primary_position=position,
                    fantasy_positions_json=json.dumps([position]),
                    status="active",
                    rookie_class=2026 if number % 7 == 0 else 2024,
                    is_rookie=number % 7 == 0,
                    created_at=now,
                    updated_at=now,
                )
            )
            added_entries.append(
                BoardEntryRow(
                    id=str(uuid4()),
                    board_id=board_id,
                    player_id=player_id,
                    tier_id=None,
                    manual_order=len(existing_entries) + number,
                    note=None,
                    favorite=False,
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.flush()
        session.add_all(added_entries)
        session.commit()
    assert set(target_ids) == TARGET_NAMES
    return target_ids


def _deprioritize_alert_targets(
    client: TestClient,
    *draft_ids: str,
) -> None:
    with client.app.state.session_factory() as session:
        candidates = list(
            session.scalars(
                select(DraftCandidateRow).where(
                    DraftCandidateRow.session_id.in_(draft_ids),
                    DraftCandidateRow.display_name.in_(TARGET_NAMES),
                )
            )
        )
        assert len(candidates) == len(draft_ids) * len(TARGET_NAMES)
        for candidate in candidates:
            candidate.manual_rank = 1000
            candidate.favorite = True
            candidate.board_note = PRIVATE_WORKFLOW_NOTE
        session.commit()


def _commit_live_evidence(client: TestClient) -> dict[str, object]:
    payload = _evidence_payload()
    payload["player_csv_text"] = str(payload["player_csv_text"]).replace(
        ",55,60,",
        ",55,63,",
    )
    preview = client.post(
        "/api/v1/alert-evidence-imports/preview",
        json=payload,
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


def _safe_user_player(client: TestClient, draft_id: str) -> str:
    response = client.get(
        f"/api/v1/draft-sessions/{draft_id}/candidates",
        params={
            "view": "personal",
            "include_drafted": False,
            "limit": 250,
        },
    )
    assert response.status_code == 200, response.text
    player = next(
        item
        for item in response.json()["items"]
        if item["display_name"].startswith("Workflow Player")
    )
    return str(player["player_id"])


def _run_until(
    client: TestClient,
    mock: dict[str, object],
    *,
    stop_after: int,
) -> tuple[dict[str, object], float]:
    started = perf_counter()
    while mock["draft"]["current_pick"] is not None:
        current = mock["draft"]["current_pick"]
        if current["overall_pick"] > stop_after:
            break
        if current["selecting_slot"] == USER_SLOT:
            mock, _ = _make_user_pick(
                client,
                mock,
                player_id=_safe_user_player(client, str(mock["draft"]["id"])),
            )
        else:
            mock = _advance_cpu(client, mock)
    return mock, perf_counter() - started


def _assert_targets_available(client: TestClient, draft_id: str) -> None:
    response = client.get(
        f"/api/v1/draft-sessions/{draft_id}/candidates",
        params={
            "view": "personal",
            "include_drafted": False,
            "limit": 250,
        },
    )
    assert response.status_code == 200
    available_names = {item["display_name"] for item in response.json()["items"]}
    assert TARGET_NAMES.issubset(available_names)


def _correct_and_undo_pick(
    client: TestClient,
    mock: dict[str, object],
    *,
    overall_pick: int,
) -> dict[str, object]:
    original = next(
        pick
        for pick in mock["draft"]["picks"]
        if pick["overall_pick"] == overall_pick
    )
    replacement = _safe_user_player(client, str(mock["draft"]["id"]))
    corrected = client.patch(
        f"/api/v1/draft-sessions/{mock['draft']['id']}/picks/{overall_pick}",
        json={
            "revision": mock["draft"]["revision"],
            "expected_current_player_id": original["player_id"],
            "replacement_player_id": replacement,
        },
    )
    assert corrected.status_code == 200, corrected.text
    undone = client.post(
        f"/api/v1/draft-sessions/{mock['draft']['id']}/undo",
        json={"revision": corrected.json()["revision"]},
    )
    assert undone.status_code == 200, undone.text
    restored = _read_mock(client, str(mock["draft"]["id"]))
    assert restored["draft"]["current_pick"]["overall_pick"] == overall_pick
    if original["selecting_slot"] == USER_SLOT:
        restored, replayed_player = _make_user_pick(
            client,
            restored,
            player_id=original["player_id"],
        )
        assert replayed_player == original["player_id"]
    else:
        restored = _advance_cpu(client, restored)
        assert restored["last_cpu_decision"]["chosen_player_id"] == original["player_id"]
    restored_pick = next(
        pick
        for pick in restored["draft"]["picks"]
        if pick["overall_pick"] == overall_pick
    )
    assert restored_pick["player_id"] == original["player_id"]
    return restored


def test_full_phase5_entropy_shaped_offline_workflow(
    runtime_settings: RuntimeSettings,
) -> None:
    setup_app = create_app(runtime_settings)
    with TestClient(setup_app, headers=TRUSTED_HEADERS) as client:
        board, profile, _players = _seed_workspace(client)
        _expand_board_for_full_mock(client, board_id=str(board["id"]))
        snapshot = _commit_live_evidence(client)

        enabled = _create_mock(
            client,
            str(board["id"]),
            name="Phase 5 Enabled Full Workflow",
            seed="2026072901",
            league_profile_id=str(profile["id"]),
        )
        disabled = _create_mock(
            client,
            str(board["id"]),
            name="Phase 5 Disabled Replay",
            seed="2026072901",
            league_profile_id=str(profile["id"]),
        )
        enabled_id = str(enabled["draft"]["id"])
        disabled_id = str(disabled["draft"]["id"])
        _deprioritize_alert_targets(client, enabled_id, disabled_id)

        for mock in (enabled, disabled):
            attached = _attach(client, mock["draft"], str(snapshot["id"]))
            assert attached["revision"] == 0
            assert attached["format_compatibility"] == "exact"
        disabled_configuration = client.patch(
            f"/api/v1/draft-sessions/{disabled_id}/alert-configuration",
            json={
                "draft_revision": 0,
                "configuration_revision": 0,
                "enabled": False,
            },
        )
        assert disabled_configuration.status_code == 200

        enabled, enabled_opening_seconds = _run_until(
            client,
            enabled,
            stop_after=60,
        )
        disabled, disabled_opening_seconds = _run_until(
            client,
            disabled,
            stop_after=60,
        )
        assert _pick_sequence(enabled, through=60) == _pick_sequence(
            disabled,
            through=60,
        )
        assert enabled_opening_seconds < 30
        assert disabled_opening_seconds < 30
        _assert_targets_available(client, enabled_id)

        evaluated = _evaluate(
            client,
            enabled_id,
            draft_revision=60,
            current_pick=61,
        )
        assert evaluated.status_code == 200, evaluated.text
        initial = evaluated.json()
        theo_value = _event(
            initial["alerts"],
            player_name="Theo Banks",
            kind="value_watch",
        )
        theo_return = _event(
            initial["alerts"],
            player_name="Theo Banks",
            kind="return_risk",
        )
        andre_trade = _event(
            initial["alerts"],
            player_name="Andre Vale III",
            kind="trade_up_window",
        )
        assert _event(
            initial["alerts"],
            player_name="Andre Vale III",
            kind="return_risk",
        )
        for event in (theo_value, theo_return, andre_trade):
            assert event["confidence"] in {"low", "medium", "high"}
            assert event["freshness"] in {"fresh", "aging"}
            assert set(event["evidence"]["components"]) == {
                "personal_conviction",
                "dynasty_market",
                "strategy_fit",
                "win_now_production",
                "age_risk",
            }
            assert event["evidence"]["confidence_reasons"]
            assert event["evidence"]["source_as_of"]
        assert andre_trade["evidence"]["target_pick_window"]["high"] < 64
        assert "PRODUCTION_UNAVAILABLE" in andre_trade["limitation_codes"]

        dismissed = _patch_event(
            client,
            draft_id=enabled_id,
            event_id=str(theo_value["id"]),
            configuration_revision=0,
            expected_status="open",
            status="dismissed",
        )
        assert dismissed.status_code == 200
        snoozed = _patch_event(
            client,
            draft_id=enabled_id,
            event_id=str(andre_trade["id"]),
            configuration_revision=0,
            expected_status="open",
            status="snoozed",
        )
        assert snoozed.status_code == 200
        for event_id, expected_status in (
            (theo_value["id"], "dismissed"),
            (andre_trade["id"], "snoozed"),
        ):
            reopened = _patch_event(
                client,
                draft_id=enabled_id,
                event_id=str(event_id),
                configuration_revision=0,
                expected_status=expected_status,
                status="open",
            )
            assert reopened.status_code == 200

        pivoted = client.patch(
            f"/api/v1/mock-sessions/{enabled_id}/strategy",
            json={
                "mock_revision": enabled["mock"]["revision"],
                "expected_current_overall_pick": 61,
                "strategy_key": "wr_heavy",
                "private_user_note": "Private Phase 5 audit pivot",
            },
        )
        assert pivoted.status_code == 200, pivoted.text
        after_pivot = _evaluate(
            client,
            enabled_id,
            draft_revision=60,
            current_pick=61,
            last_evaluation_revision=60,
        )
        assert after_pivot.status_code == 200, after_pivot.text
        pivot_body = after_pivot.json()
        pivot_event = _event(
            pivot_body["alerts"],
            player_name="Theo Banks",
            kind="value_watch",
        )
        assert pivot_event["evidence"]["components"]["strategy_fit"]["band"] == "wr_heavy"
        assert pivot_event["evidence"]["market_gap"] == theo_value["evidence"]["market_gap"]
        assert "Private Phase 5 audit pivot" not in after_pivot.text

        enabled = pivoted.json()
        enabled = _advance_cpu(client, enabled)
        assert enabled["draft"]["revision"] == 61
        first_after_mutation = enabled["last_cpu_decision"]

    restarted_app = create_app(runtime_settings)
    with TestClient(restarted_app, headers=TRUSTED_HEADERS) as client:
        restored = _read_mock(client, enabled_id)
        reconciled = _evaluate(
            client,
            enabled_id,
            draft_revision=61,
            current_pick=62,
            last_evaluation_revision=60,
        )
        assert reconciled.status_code == 200, reconciled.text
        repeated = _evaluate(
            client,
            enabled_id,
            draft_revision=61,
            current_pick=62,
            last_evaluation_revision=61,
        )
        assert repeated.status_code == 200
        assert repeated.json()["evaluation"]["idempotent"] is True
        assert repeated.json()["evaluation"]["id"] == reconciled.json()["evaluation"]["id"]

        restored = _correct_and_undo_pick(
            client,
            restored,
            overall_pick=61,
        )
        restored_pick = next(
            pick
            for pick in restored["draft"]["picks"]
            if pick["overall_pick"] == 61
        )
        assert restored_pick["player_id"] == first_after_mutation["chosen_player_id"]

        restored = _advance_cpu(client, restored)
        restored = _advance_cpu(client, restored)
        assert restored["draft"]["current_pick"]["overall_pick"] == 64
        original_user_player = _safe_user_player(client, enabled_id)
        restored, picked_player = _make_user_pick(
            client,
            restored,
            player_id=original_user_player,
        )
        assert picked_player == original_user_player
        restored = _correct_and_undo_pick(
            client,
            restored,
            overall_pick=64,
        )

        before_toggle = list(restored["draft"]["picks"])
        disabled_response = client.patch(
            f"/api/v1/draft-sessions/{enabled_id}/alert-configuration",
            json={
                "draft_revision": restored["draft"]["revision"],
                "configuration_revision": 0,
                "enabled": False,
            },
        )
        assert disabled_response.status_code == 200
        enabled_response = client.patch(
            f"/api/v1/draft-sessions/{enabled_id}/alert-configuration",
            json={
                "draft_revision": restored["draft"]["revision"],
                "configuration_revision": 1,
                "enabled": True,
            },
        )
        assert enabled_response.status_code == 200
        after_toggle = _read_mock(client, enabled_id)
        assert after_toggle["draft"]["revision"] == restored["draft"]["revision"]
        assert after_toggle["draft"]["picks"] == before_toggle

        completed, completion_seconds = _run_until(
            client,
            after_toggle,
            stop_after=TOTAL_PICKS,
        )
        assert completed["draft"]["status"] == "completed"
        assert completed["draft"]["active_pick_count"] == TOTAL_PICKS
        assert completed["draft"]["current_pick"] is None
        assert completion_seconds < 120

        blind = client.get(
            f"/api/v1/draft-sessions/{enabled_id}/candidates",
            params={"view": "blind", "include_drafted": True, "limit": 250},
        )
        assert blind.status_code == 200
        for forbidden in (
            "personal_rank",
            "tier_name",
            "tier_color",
            "favorite",
            "board_note",
            "alert",
            "market",
            "expected_selection",
            PRIVATE_WORKFLOW_NOTE,
        ):
            assert forbidden not in blind.text

        history = client.get(
            f"/api/v1/draft-sessions/{enabled_id}/alerts",
            params={"scope": "history", "limit": 100},
        )
        assert history.status_code == 200
        assert history.json()["items"]
        history_text = history.text.casefold()
        for marker in PRIVATE_MARKERS | {
            PRIVATE_WORKFLOW_NOTE,
            "private phase 5 audit pivot",
        }:
            assert marker.casefold() not in history_text

        exported = client.get(f"/api/v1/draft-sessions/{enabled_id}/export.csv")
        assert exported.status_code == 200
        for forbidden in (
            "alert",
            "market",
            "strategy",
            "provider",
            PRIVATE_WORKFLOW_NOTE,
        ):
            assert forbidden.casefold() not in exported.text.casefold()
