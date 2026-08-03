from __future__ import annotations

import json
import socket
from pathlib import Path
from time import perf_counter
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
from jsonschema import validate
from test_phase4_live_workflow import (
    TOTAL_PICKS,
    _advance_cpu,
    _available_candidates,
    _read_mock,
    _seed_entropy_board,
)

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}
USER_SLOT = 1
TEAM_NAMES = ["Your Team", *(f"CPU {slot}" for slot in range(2, 11))]


def _create_slot_one_mock(
    client: TestClient,
    *,
    board_id: str,
    league_profile_id: str,
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/boards/{board_id}/mock-sessions",
        json={
            "name": "V1 Slot 1 Release Rehearsal",
            "league_profile_id": league_profile_id,
            "draft_format": "snake",
            "third_round_reversal": True,
            "team_count": 10,
            "round_count": 24,
            "user_slot": USER_SLOT,
            "team_names": TEAM_NAMES,
            "seed": "2026080301",
            "randomness": 100,
            "strategy_key": "balanced",
            "fallback_archetypes": {
                str(slot): "chaotic" for slot in range(2, 11)
            },
            "include_in_learning": False,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _user_pick(
    client: TestClient,
    mock: dict[str, Any],
    *,
    player_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    current = mock["draft"]["current_pick"]
    assert current is not None
    assert current["selecting_slot"] == USER_SLOT
    selected_id = player_id or _available_candidates(
        client,
        mock["draft"]["id"],
        limit=1,
    )[0]["player_id"]
    response = client.post(
        f"/api/v1/draft-sessions/{mock['draft']['id']}/picks",
        json={
            "revision": mock["draft"]["revision"],
            "expected_overall_pick": current["overall_pick"],
            "player_id": selected_id,
        },
    )
    assert response.status_code == 200, response.text
    return _read_mock(client, mock["draft"]["id"]), selected_id


def _assert_refreshed_release_fixture(project_root: Path) -> None:
    fixture = json.loads(
        (
            project_root
            / "tests"
            / "fixtures"
            / "league_profiles"
            / "entropy-2026.sanitized.json"
        ).read_text(encoding="utf-8")
    )
    schema = json.loads(
        (project_root / "docs" / "schemas" / "league-profile.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validate(fixture, schema)
    startup = next(draft for draft in fixture["drafts"] if draft["purpose"] == "startup")
    assert fixture["league"]["team_count"] == 10
    assert startup["rounds"] == 24
    assert startup["pick_timer_seconds"] == 120
    assert startup["reversal_round"] == 3
    assert startup["user_slot"] == USER_SLOT
    assert startup["draft_order"] == TEAM_NAMES
    assert fixture["provenance"]["source_as_of"] == "2026-08-03T13:39:45Z"
    scoring = {
        rule["provider_key"]: rule["points"] for rule in fixture["scoring"]["rules"]
    }
    assert scoring["bonus_rec_te"] == 0.5
    assert scoring["bonus_fd_te"] == 0.5


def test_v1_slot_one_offline_recovery_and_export_rehearsal(
    runtime_settings: RuntimeSettings,
) -> None:
    _assert_refreshed_release_fixture(runtime_settings.project_root)
    first_app = create_app(runtime_settings)
    with TestClient(first_app, headers=TRUSTED_HEADERS) as client:
        board_id, league_profile_id, _ = _seed_entropy_board(client, first_app)
        mock = _create_slot_one_mock(
            client,
            board_id=board_id,
            league_profile_id=league_profile_id,
        )
        assert mock["draft"]["user_slot"] == USER_SLOT
        assert mock["draft"]["current_pick"]["overall_pick"] == 1
        assert mock["draft"]["current_pick"]["selecting_team"] == "Your Team"
        mock, original_id = _user_pick(client, mock)

        replacement_id = _available_candidates(
            client,
            mock["draft"]["id"],
            limit=1,
        )[0]["player_id"]
        correction = client.patch(
            f"/api/v1/draft-sessions/{mock['draft']['id']}/picks/1",
            json={
                "revision": mock["draft"]["revision"],
                "expected_current_player_id": original_id,
                "replacement_player_id": replacement_id,
            },
        )
        assert correction.status_code == 200, correction.text
        corrected = correction.json()
        undo = client.post(
            f"/api/v1/draft-sessions/{mock['draft']['id']}/undo",
            json={"revision": corrected["revision"]},
        )
        assert undo.status_code == 200, undo.text
        mock = _read_mock(client, mock["draft"]["id"])
        mock, repicked_id = _user_pick(client, mock, player_id=original_id)
        assert repicked_id == original_id
        saved_draft_id = mock["draft"]["id"]
        saved_revision = mock["draft"]["revision"]
        saved_picks = mock["draft"]["picks"]

    restarted_app = create_app(runtime_settings)
    with TestClient(restarted_app, headers=TRUSTED_HEADERS) as client:
        restored = _read_mock(client, saved_draft_id)
        assert restored["draft"]["revision"] == saved_revision
        assert restored["draft"]["picks"] == saved_picks
        assert restored["draft"]["current_pick"]["overall_pick"] == 2

        started = perf_counter()
        with patch.object(
            socket.socket,
            "connect",
            side_effect=AssertionError("network access attempted during V1 rehearsal"),
        ):
            while restored["draft"]["current_pick"] is not None:
                if restored["draft"]["current_pick"]["selecting_slot"] == USER_SLOT:
                    restored, _ = _user_pick(client, restored)
                else:
                    restored = _advance_cpu(client, restored)

            board_export = client.get(f"/api/v1/boards/{board_id}/export.csv")
            draft_export = client.get(
                f"/api/v1/draft-sessions/{saved_draft_id}/export.csv"
            )
            report_response = client.post(
                f"/api/v1/draft-sessions/{saved_draft_id}/post-draft-reports",
                json={
                    "draft_revision": restored["draft"]["revision"],
                    "expected_completed_at": restored["draft"]["completed_at"],
                },
            )
            assert report_response.status_code == 201, report_response.text
            report_id = report_response.json()["report"]["id"]
            report_export = client.get(
                f"/api/v1/post-draft-reports/{report_id}/export.html"
            )
        elapsed = perf_counter() - started

        assert elapsed < 120
        assert restored["draft"]["status"] == "completed"
        assert restored["draft"]["active_pick_count"] == TOTAL_PICKS
        assert board_export.status_code == 200
        assert draft_export.status_code == 200
        assert report_export.status_code == 200
        assert "text/csv" in board_export.headers["content-type"]
        assert "text/csv" in draft_export.headers["content-type"]
        assert "text/html" in report_export.headers["content-type"]
        draft_text = draft_export.text.casefold()
        for private_marker in (
            "private-live-audit-board-note",
            "seed",
            "randomness",
            "content_fingerprint",
            "provider",
        ):
            assert private_marker not in draft_text
        html_text = report_export.text.casefold()
        for remote_or_active_fragment in ("<script", "http://", "https://", "src="):
            assert remote_or_active_fragment not in html_text
