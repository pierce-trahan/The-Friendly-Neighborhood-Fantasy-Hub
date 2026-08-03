from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient
from sqlalchemy import select

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.domains.drafts.models import DraftCandidateRow
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}


def test_single_player_personal_board_uses_offline_market_baseline(
    runtime_settings: RuntimeSettings,
) -> None:
    project_root = runtime_settings.project_root
    settings = replace(
        runtime_settings,
        bundled_player_snapshot_path=project_root
        / "data"
        / "player_universe"
        / "nflverse-players-2026.json",
        bundled_market_snapshot_path=project_root
        / "data"
        / "market_baseline"
        / "dynasty-superflex-ecr-2026-07-31.json",
    )
    app = create_app(settings)
    with TestClient(app, headers=TRUSTED_HEADERS) as client:
        players = client.get(
            "/api/v1/players",
            params={"search": "Bijan Robinson", "limit": 10},
        )
        assert players.status_code == 200, players.text
        bijan = next(
            player
            for player in players.json()["items"]
            if player["display_name"] == "Bijan Robinson"
        )
        board_response = client.post(
            "/api/v1/boards",
            json={"name": "One-player conviction board", "scope": "overall"},
        )
        assert board_response.status_code == 201, board_response.text
        board_id = board_response.json()["id"]
        ranked = client.post(
            f"/api/v1/boards/{board_id}/entries",
            json={"player_id": bijan["id"]},
        )
        assert ranked.status_code == 200, ranked.text
        assert ranked.json()["entries"][0]["rank"] == 1

        league = client.post("/api/v1/league-profiles/samples/entropy")
        assert league.status_code == 201, league.text
        created = client.post(
            f"/api/v1/boards/{board_id}/mock-sessions",
            json={
                "name": "Market correction rehearsal",
                "league_profile_id": league.json()["id"],
                "draft_format": "snake",
                "third_round_reversal": True,
                "team_count": 10,
                "round_count": 24,
                "user_slot": 1,
                "seed": "20260803",
                "randomness": 0,
                "strategy_key": "balanced",
                "include_in_learning": False,
            },
        )
        assert created.status_code == 201, created.text
        mock = created.json()
        baseline = mock["mock"]["market_baseline"]
        assert mock["mock"]["cpu_engine_version"] == "market-board-v1"
        assert baseline["evidence_kind"] == "expert_consensus"
        assert baseline["rank_type"] == "dynasty_2qb_ecr"
        assert baseline["source_name"] == "DynastyProcess"
        assert baseline["source_as_of"] == "2026-07-31"
        assert baseline["matched_candidate_count"] >= 600
        assert baseline["player_count"] == 621
        assert "ECR_NOT_ADP" in baseline["limitations"]

        session_id = mock["draft"]["id"]
        user_pick = client.post(
            f"/api/v1/draft-sessions/{session_id}/picks",
            json={
                "revision": 0,
                "expected_overall_pick": 1,
                "player_id": bijan["id"],
            },
        )
        assert user_pick.status_code == 200, user_pick.text
        current = client.get(f"/api/v1/mock-sessions/{session_id}").json()
        cpu_pick = client.post(
            f"/api/v1/mock-sessions/{session_id}/cpu-pick",
            json={
                "draft_revision": current["draft"]["revision"],
                "mock_revision": current["mock"]["revision"],
                "expected_overall_pick": 2,
                "expected_selecting_slot": 2,
            },
        )
        assert cpu_pick.status_code == 200, cpu_pick.text
        decision = cpu_pick.json()["last_cpu_decision"]
        assert decision["chosen_player_display_name"] == "Josh Allen"
        assert decision["reason_codes"][0] == "MARKET_ECR_BASELINE"
        assert "ECR_NOT_ADP" in decision["limitation_codes"]

        with app.state.session_factory() as session:
            frozen = list(
                session.scalars(
                    select(DraftCandidateRow).where(
                        DraftCandidateRow.session_id == session_id,
                        DraftCandidateRow.market_rank.is_not(None),
                    )
                )
            )
            assert len(frozen) >= 600
            josh = next(row for row in frozen if row.display_name == "Josh Allen")
            assert josh.market_rank == 1
