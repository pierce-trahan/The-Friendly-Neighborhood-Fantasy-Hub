from __future__ import annotations

import json
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.boards.models import BoardEntryRow
from friendly_hub.domains.players.models import PlayerRow
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}
PRIVATE_AUDIT_NOTE = "private-live-audit-board-note"
TOTAL_PLAYERS = 260
TOTAL_PICKS = 240
USER_SLOT = 7
PIVOT_PICK = 61


def _seed_entropy_board(
    client: TestClient,
    app: Any,
) -> tuple[str, str, dict[str, int]]:
    profile_response = client.post("/api/v1/league-profiles/samples/entropy")
    assert profile_response.status_code == 201, profile_response.text
    profile_id = profile_response.json()["id"]
    board_response = client.post(
        "/api/v1/boards",
        json={
            "name": "Phase 4 Full Workflow Board",
            "description": "Fictional offline acceptance-audit board",
            "league_profile_id": profile_id,
            "scope": "overall",
        },
    )
    assert board_response.status_code == 201, board_response.text
    board_id = board_response.json()["id"]

    positions = ("QB", "RB", "WR", "WR", "TE")
    now = utc_now_text()
    rank_by_player_id: dict[str, int] = {}
    entries: list[BoardEntryRow] = []
    with app.state.session_factory() as database:
        for index in range(TOTAL_PLAYERS):
            rank = index + 1
            player_id = str(uuid4())
            position = positions[index % len(positions)]
            display_name = f"Audit Player {rank:03d}"
            rank_by_player_id[player_id] = rank
            database.add(
                PlayerRow(
                    id=player_id,
                    display_name=display_name,
                    first_name="Audit",
                    last_name=f"Player {rank:03d}",
                    suffix=None,
                    search_name=display_name.casefold(),
                    team=f"T{index % 32:02d}",
                    primary_position=position,
                    fantasy_positions_json=json.dumps([position]),
                    status="active",
                    rookie_class=2026 if index % 7 == 0 else 2024,
                    is_rookie=index % 7 == 0,
                    created_at=now,
                    updated_at=now,
                )
            )
            entries.append(
                BoardEntryRow(
                    id=str(uuid4()),
                    board_id=board_id,
                    player_id=player_id,
                    tier_id=None,
                    manual_order=rank,
                    note=PRIVATE_AUDIT_NOTE if rank == 1 else None,
                    favorite=rank <= 12,
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        database.flush()
        database.add_all(entries)
        database.commit()
    return board_id, profile_id, rank_by_player_id


def _mock_payload(
    *,
    name: str,
    seed: str,
    league_profile_id: str,
) -> dict[str, object]:
    return {
        "name": name,
        "league_profile_id": league_profile_id,
        "draft_format": "snake",
        "third_round_reversal": True,
        "team_count": 10,
        "round_count": 24,
        "user_slot": USER_SLOT,
        "team_names": [
            "CPU 1",
            "CPU 2",
            "CPU 3",
            "CPU 4",
            "CPU 5",
            "CPU 6",
            "Your Team",
            "CPU 8",
            "CPU 9",
            "CPU 10",
        ],
        "seed": seed,
        "randomness": 100,
        "strategy_key": "balanced",
        "fallback_archetypes": {
            str(slot): "chaotic"
            for slot in range(1, 11)
            if slot != USER_SLOT
        },
        "include_in_learning": False,
    }


def _create_mock(
    client: TestClient,
    board_id: str,
    *,
    name: str,
    seed: str,
    league_profile_id: str,
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/boards/{board_id}/mock-sessions",
        json=_mock_payload(
            name=name,
            seed=seed,
            league_profile_id=league_profile_id,
        ),
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["draft"]["candidate_total"] == TOTAL_PLAYERS
    assert created["mock"]["include_in_learning"] is False
    assert created["mock"]["strategy_compatibility"] == "compatible"
    return created


def _read_mock(client: TestClient, session_id: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/mock-sessions/{session_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _advance_cpu(
    client: TestClient,
    mock: dict[str, Any],
) -> dict[str, Any]:
    current = mock["draft"]["current_pick"]
    assert current is not None
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


def _available_candidates(
    client: TestClient,
    session_id: str,
    *,
    limit: int = 2,
    include_drafted: bool = False,
) -> list[dict[str, Any]]:
    response = client.get(
        f"/api/v1/draft-sessions/{session_id}/candidates",
        params={
            "view": "blind",
            "include_drafted": include_drafted,
            "limit": limit,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _make_user_pick(
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


def _pivot_if_due(
    client: TestClient,
    mock: dict[str, Any],
    *,
    pivoted: bool,
) -> tuple[dict[str, Any], bool]:
    current = mock["draft"]["current_pick"]
    if pivoted or current is None or current["overall_pick"] < PIVOT_PICK:
        return mock, pivoted
    response = client.patch(
        f"/api/v1/mock-sessions/{mock['draft']['id']}/strategy",
        json={
            "mock_revision": mock["mock"]["revision"],
            "expected_current_overall_pick": current["overall_pick"],
            "strategy_key": "wr_heavy",
            "private_user_note": "Fictional audit pivot",
        },
    )
    assert response.status_code == 200, response.text
    pivoted_mock = response.json()
    assert pivoted_mock["mock"]["current_strategy_key"] == "wr_heavy"
    assert pivoted_mock["current_strategy_revision"]["reason"] == "user_pivot"
    assert pivoted_mock["current_strategy_revision"]["effective_overall_pick"] == (
        current["overall_pick"]
    )
    return pivoted_mock, True


def _run_mock(
    client: TestClient,
    mock: dict[str, Any],
    *,
    stop_after: int = TOTAL_PICKS,
    pivot: bool,
) -> tuple[dict[str, Any], float]:
    started = perf_counter()
    pivoted = False
    while mock["draft"]["current_pick"] is not None:
        current = mock["draft"]["current_pick"]
        if current["overall_pick"] > stop_after:
            break
        if pivot:
            mock, pivoted = _pivot_if_due(
                client,
                mock,
                pivoted=pivoted,
            )
            current = mock["draft"]["current_pick"]
        if current["selecting_slot"] == USER_SLOT:
            mock, _ = _make_user_pick(client, mock)
        else:
            mock = _advance_cpu(client, mock)
    return mock, perf_counter() - started


def _exercise_cpu_correction_and_replay(
    client: TestClient,
    mock: dict[str, Any],
) -> dict[str, Any]:
    original_decision = mock["last_cpu_decision"]
    assert original_decision["overall_pick"] == 1
    replacement = _available_candidates(
        client,
        mock["draft"]["id"],
        limit=1,
    )[0]["player_id"]
    correction = client.patch(
        f"/api/v1/draft-sessions/{mock['draft']['id']}/picks/1",
        json={
            "revision": mock["draft"]["revision"],
            "expected_current_player_id": original_decision["chosen_player_id"],
            "replacement_player_id": replacement,
        },
    )
    assert correction.status_code == 200, correction.text
    corrected_audit = client.get(
        f"/api/v1/mock-sessions/{mock['draft']['id']}/decisions/1"
    ).json()
    assert corrected_audit["decision_status"] == "historical"
    assert corrected_audit["manually_corrected"] is True

    undo = client.post(
        f"/api/v1/draft-sessions/{mock['draft']['id']}/undo",
        json={"revision": correction.json()["revision"]},
    )
    assert undo.status_code == 200, undo.text
    replayed = _advance_cpu(client, _read_mock(client, mock["draft"]["id"]))
    assert replayed["last_cpu_decision"]["chosen_player_id"] == (
        original_decision["chosen_player_id"]
    )
    assert replayed["last_cpu_decision"]["component_scores"] == (
        original_decision["component_scores"]
    )
    return replayed


def _exercise_user_correction_and_undo(
    client: TestClient,
    mock: dict[str, Any],
) -> dict[str, Any]:
    while mock["draft"]["current_pick"]["selecting_slot"] != USER_SLOT:
        mock = _advance_cpu(client, mock)
    original_options = _available_candidates(
        client,
        mock["draft"]["id"],
        limit=2,
    )
    original_id = original_options[0]["player_id"]
    mock, selected_id = _make_user_pick(
        client,
        mock,
        player_id=original_id,
    )
    assert selected_id == original_id
    replacement_id = _available_candidates(
        client,
        mock["draft"]["id"],
        limit=1,
    )[0]["player_id"]
    correction = client.patch(
        f"/api/v1/draft-sessions/{mock['draft']['id']}/picks/7",
        json={
            "revision": mock["draft"]["revision"],
            "expected_current_player_id": original_id,
            "replacement_player_id": replacement_id,
        },
    )
    assert correction.status_code == 200, correction.text
    undo = client.post(
        f"/api/v1/draft-sessions/{mock['draft']['id']}/undo",
        json={"revision": correction.json()["revision"]},
    )
    assert undo.status_code == 200, undo.text
    restored = _read_mock(client, mock["draft"]["id"])
    restored, repicked_id = _make_user_pick(
        client,
        restored,
        player_id=original_id,
    )
    assert repicked_id == original_id
    return restored


def _pick_sequence(mock: dict[str, Any], *, through: int = TOTAL_PICKS) -> list[str]:
    return [
        pick["player_id"]
        for pick in mock["draft"]["picks"]
        if pick["overall_pick"] <= through
    ]


def test_full_entropy_shaped_mock_live_workflow(
    runtime_settings: RuntimeSettings,
) -> None:
    setup_app = create_app(runtime_settings)
    with TestClient(setup_app, headers=TRUSTED_HEADERS) as client:
        board_id, profile_id, rank_by_player_id = _seed_entropy_board(
            client,
            setup_app,
        )
        primary = _create_mock(
            client,
            board_id,
            name="Primary Full Workflow",
            seed="2026072801",
            league_profile_id=profile_id,
        )
        replay = _create_mock(
            client,
            board_id,
            name="Equivalent Replay",
            seed="2026072801",
            league_profile_id=profile_id,
        )
        changed_seed = _create_mock(
            client,
            board_id,
            name="Changed Seed",
            seed="2026072802",
            league_profile_id=profile_id,
        )
        assert primary["mock"]["content_fingerprint"] == (
            replay["mock"]["content_fingerprint"]
        )
        primary = _advance_cpu(client, primary)
        first_decision = primary["last_cpu_decision"]
        primary_id = primary["draft"]["id"]
        replay_id = replay["draft"]["id"]
        changed_seed_id = changed_seed["draft"]["id"]

    restarted_app = create_app(runtime_settings)
    with TestClient(restarted_app, headers=TRUSTED_HEADERS) as client:
        restored = _read_mock(client, primary_id)
        assert restored["draft"]["active_pick_count"] == 1
        assert restored["last_cpu_decision"]["id"] == first_decision["id"]
        primary = _exercise_cpu_correction_and_replay(client, restored)
        primary = _exercise_user_correction_and_undo(client, primary)
        primary, primary_seconds = _run_mock(
            client,
            primary,
            pivot=True,
        )
        assert primary["draft"]["status"] == "completed"
        assert primary["draft"]["active_pick_count"] == TOTAL_PICKS
        assert primary["draft"]["current_pick"] is None
        assert primary["current_strategy_revision"]["next_strategy_key"] == "wr_heavy"
        assert primary_seconds < 120

        replay = _read_mock(client, replay_id)
        replay, replay_seconds = _run_mock(
            client,
            replay,
            pivot=True,
        )
        assert replay["draft"]["status"] == "completed"
        assert replay_seconds < 120
        assert _pick_sequence(primary) == _pick_sequence(replay)

        changed_seed = _read_mock(client, changed_seed_id)
        changed_seed, changed_seed_seconds = _run_mock(
            client,
            changed_seed,
            stop_after=40,
            pivot=False,
        )
        assert changed_seed["draft"]["active_pick_count"] == 40
        assert changed_seed_seconds < 30
        primary_opening = _pick_sequence(primary, through=40)
        changed_opening = _pick_sequence(changed_seed, through=40)
        assert len(set(changed_opening)) == 40
        first_difference = next(
            index
            for index, (original, changed) in enumerate(
                zip(primary_opening, changed_opening, strict=True),
            )
            if original != changed
        )
        original_rank = rank_by_player_id[primary_opening[first_difference]]
        changed_rank = rank_by_player_id[changed_opening[first_difference]]
        assert abs(original_rank - changed_rank) <= 20

        blind_response = client.get(
            f"/api/v1/draft-sessions/{primary_id}/candidates",
            params={
                "view": "blind",
                "include_drafted": True,
                "limit": 250,
            },
        )
        assert blind_response.status_code == 200
        blind_text = blind_response.text
        for private_field in (
            "personal_rank",
            "tier_name",
            "tier_color",
            "favorite",
            "board_note",
            "snapshot_source",
            PRIVATE_AUDIT_NOTE,
        ):
            assert private_field not in blind_text

        export_response = client.get(
            f"/api/v1/draft-sessions/{primary_id}/export.csv"
        )
        assert export_response.status_code == 200
        export_text = export_response.text.casefold()
        for mock_private_field in (
            "seed",
            "randomness",
            "strategy",
            "content_fingerprint",
            "internal_manager_reference",
            "provider",
            PRIVATE_AUDIT_NOTE,
        ):
            assert mock_private_field.casefold() not in export_text

        opted_in = client.patch(
            f"/api/v1/mock-sessions/{primary_id}/learning",
            json={
                "mock_revision": primary["mock"]["revision"],
                "include_in_learning": True,
            },
        )
        assert opted_in.status_code == 200, opted_in.text
        opted_out = client.patch(
            f"/api/v1/mock-sessions/{primary_id}/learning",
            json={
                "mock_revision": opted_in.json()["mock"]["revision"],
                "include_in_learning": False,
            },
        )
        assert opted_out.status_code == 200, opted_out.text
        assert opted_out.json()["mock"]["include_in_learning"] is False
        assert opted_out.json()["draft"]["picks"] == primary["draft"]["picks"]

        history = client.get(
            f"/api/v1/boards/{board_id}/mock-sessions",
            params={"limit": 20},
        )
        assert history.status_code == 200
        summary = next(
            item
            for item in history.json()["items"]
            if item["session_id"] == primary_id
        )
        assert summary["completion_state"] == "completed"
        assert summary["pivot_count"] == 1
        assert summary["include_in_learning"] is False
