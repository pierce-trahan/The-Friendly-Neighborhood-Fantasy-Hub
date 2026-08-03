from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.domains.drafts.models import (
    DraftCandidateRow,
    DraftPickRevisionRow,
    DraftPickRow,
    DraftSessionRow,
    DraftTeamRow,
)
from friendly_hub.domains.mocks.models import (
    MockGuidanceEventRow,
    MockStrategyRevisionRow,
)
from friendly_hub.domains.reports import service as report_service
from friendly_hub.domains.reports.models import (
    PostDraftReportMomentRow,
    PostDraftReportPlayerRow,
    PostDraftReportRow,
    PostDraftReportSectionRow,
)
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}
SECTION_KEYS = [
    "draft_summary",
    "position_inventory",
    "starter_coverage",
    "roster_concentration",
    "year_one_production_context",
    "dynasty_market_context",
    "age_risk_profile",
    "long_term_value",
    "liquidity",
    "player_fragility",
    "strategy_story",
    "personal_board_choice_moments",
    "recorded_alert_moments",
    "evidence_limits",
]


def _seed_context(
    client: TestClient,
) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
    preview = client.post("/api/v1/player-imports/fixture/preview")
    assert preview.status_code == 201
    committed = client.post(f"/api/v1/player-imports/{preview.json()['id']}/commit")
    assert committed.status_code == 200
    players_response = client.get("/api/v1/players", params={"limit": 100})
    assert players_response.status_code == 200
    players = players_response.json()["items"]

    board_response = client.post(
        "/api/v1/boards",
        json={"name": "Report Board", "scope": "overall"},
    )
    assert board_response.status_code == 201
    board = board_response.json()
    for player in players[:4]:
        entry_response = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": player["id"]},
        )
        assert entry_response.status_code == 200
        board = entry_response.json()
    private_entry = board["entries"][0]
    private_response = client.patch(
        f"/api/v1/boards/{board['id']}/entries/{private_entry['id']}",
        json={"note": "PRIVATE REPORT TEST NOTE", "favorite": True},
    )
    assert private_response.status_code == 200
    board = private_response.json()

    league_response = client.post("/api/v1/league-profiles/samples/entropy")
    assert league_response.status_code == 201
    return board, players, league_response.json()


def _start_live(
    client: TestClient,
    board_id: str,
    league_profile_id: str | None,
    *,
    round_count: int = 2,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/boards/{board_id}/draft-sessions",
        json={
            "name": "Completed Report Draft",
            "mode": "live",
            "league_profile_id": league_profile_id,
            "draft_format": "snake",
            "third_round_reversal": False,
            "team_count": 2,
            "round_count": round_count,
            "user_slot": 1,
            "team_names": ["Your Team", "Fictional Rival"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _complete_draft(
    client: TestClient,
    draft: dict[str, object],
    players: list[dict[str, object]],
) -> dict[str, object]:
    current = draft
    for player in players[: current["total_picks"]]:
        current_pick = current["current_pick"]
        assert isinstance(current_pick, dict)
        response = client.post(
            f"/api/v1/draft-sessions/{current['id']}/picks",
            json={
                "revision": current["revision"],
                "expected_overall_pick": current_pick["overall_pick"],
                "player_id": player["id"],
            },
        )
        assert response.status_code == 200, response.text
        current = response.json()
    assert current["status"] == "completed"
    return current


def _source_state(client: TestClient, draft_id: str) -> dict[str, object]:
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        draft = session.get(DraftSessionRow, draft_id)
        assert draft is not None
        return {
            "draft": (
                draft.status,
                draft.revision,
                draft.updated_at,
                draft.completed_at,
            ),
            "picks": list(
                session.execute(
                    select(
                        DraftPickRow.id,
                        DraftPickRow.player_id,
                        DraftPickRow.recorded_at,
                        DraftPickRow.correction_count,
                    )
                    .where(DraftPickRow.session_id == draft_id)
                    .order_by(DraftPickRow.overall_pick)
                )
            ),
            "revisions": list(
                session.execute(
                    select(
                        DraftPickRevisionRow.id,
                        DraftPickRevisionRow.session_revision,
                        DraftPickRevisionRow.next_player_id,
                    )
                    .where(DraftPickRevisionRow.session_id == draft_id)
                    .order_by(DraftPickRevisionRow.session_revision)
                )
            ),
            "candidates": list(
                session.execute(
                    select(
                        DraftCandidateRow.id,
                        DraftCandidateRow.player_id,
                        DraftCandidateRow.board_note,
                    )
                    .where(DraftCandidateRow.session_id == draft_id)
                    .order_by(DraftCandidateRow.player_id)
                )
            ),
            "teams": list(
                session.execute(
                    select(
                        DraftTeamRow.id,
                        DraftTeamRow.draft_slot,
                        DraftTeamRow.display_name,
                    )
                    .where(DraftTeamRow.session_id == draft_id)
                    .order_by(DraftTeamRow.draft_slot)
                )
            ),
        }


def _generation_payload(draft: dict[str, object]) -> dict[str, object]:
    return {
        "draft_revision": draft["revision"],
        "expected_completed_at": draft["completed_at"],
    }


def _generate(client: TestClient, draft: dict[str, object]):
    return client.post(
        f"/api/v1/draft-sessions/{draft['id']}/post-draft-reports",
        json=_generation_payload(draft),
    )


def test_completed_live_report_is_atomic_idempotent_private_and_restart_safe(
    runtime_settings: RuntimeSettings,
) -> None:
    report_id: str
    expected_report: dict[str, object]
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, players, league = _seed_context(client)
        active = _start_live(client, board["id"], league["id"])
        active_response = client.post(
            f"/api/v1/draft-sessions/{active['id']}/post-draft-reports",
            json={
                "draft_revision": active["revision"],
                "expected_completed_at": "2026-08-02T00:00:00Z",
            },
        )
        assert active_response.status_code == 409
        assert active_response.json()["error"]["code"] == "REPORT_DRAFT_NOT_COMPLETE"

        completed = _complete_draft(client, active, players)
        source_before = _source_state(client, completed["id"])
        stale = client.post(
            f"/api/v1/draft-sessions/{completed['id']}/post-draft-reports",
            json={
                "draft_revision": completed["revision"] - 1,
                "expected_completed_at": completed["completed_at"],
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "REPORT_DRAFT_STALE_REVISION"

        generated = client.post(
            f"/api/v1/draft-sessions/{completed['id']}/post-draft-reports",
            json=_generation_payload(completed),
        )
        assert generated.status_code == 201, generated.text
        assert generated.json()["idempotent"] is False
        report = generated.json()["report"]
        report_id = report["id"]
        expected_report = report
        assert report["draft_mode"] == "live"
        assert report["draft_revision"] == completed["revision"]
        assert report["summary"]["total_user_picks"] == 2
        assert [section["section_key"] for section in report["sections"]] == SECTION_KEYS
        assert report["section_summary"]["draft_summary"] == "supported"
        assert report["section_summary"]["long_term_value"] == "unavailable"
        assert report["section_summary"]["strategy_story"] == "not_applicable"
        assert report["section_summary"]["personal_board_choice_moments"] == "supported"
        assert report["section_summary"]["recorded_alert_moments"] == "supported"
        for key in (
            "year_one_production_context",
            "dynasty_market_context",
            "age_risk_profile",
        ):
            section = next(
                item for item in report["sections"] if item["section_key"] == key
            )
            assert section["availability"] == "unavailable"
            assert "EVIDENCE_SNAPSHOT_NOT_ATTACHED" in section["limitation_codes"]
        assert report["moments"] == []
        assert report["comparison_eligible"] is True
        assert report["export_available"] is False
        assert report["available_actions"] == ["compare"]
        assert len(report["roster"]) == 2
        assert "PRIVATE REPORT TEST NOTE" not in generated.text
        assert "input_fingerprint" not in generated.text
        assert "provider_id" not in generated.text
        assert "PHASE6_STEP6_EVIDENCE_ENRICHMENT_DEFERRED" not in generated.text
        assert "PHASE6_STEP7" not in generated.text

        assert _source_state(client, completed["id"]) == source_before
        session_factory = client.app.state.session_factory
        with session_factory() as session:
            assert session.scalar(select(func.count()).select_from(PostDraftReportRow)) == 1
            assert (
                session.scalar(select(func.count()).select_from(PostDraftReportPlayerRow))
                == 2
            )
            assert (
                session.scalar(select(func.count()).select_from(PostDraftReportSectionRow))
                == 14
            )
            assert (
                session.scalar(select(func.count()).select_from(PostDraftReportMomentRow))
                == 0
            )

        repeated = client.post(
            f"/api/v1/draft-sessions/{completed['id']}/post-draft-reports",
            json=_generation_payload(completed),
        )
        assert repeated.status_code == 200
        assert repeated.json()["idempotent"] is True
        assert repeated.json()["report"] == expected_report

        listed = client.get(
            f"/api/v1/draft-sessions/{completed['id']}/post-draft-reports"
        )
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        assert listed.json()["items"][0]["id"] == report_id
        assert "input_fingerprint" not in listed.text

    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        restored = client.get(f"/api/v1/post-draft-reports/{report_id}")
        assert restored.status_code == 200
        assert restored.json() == expected_report


def test_paused_and_missing_league_shape_reject_without_report_rows(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, players, _ = _seed_context(client)
        draft = _start_live(client, board["id"], None, round_count=1)
        paused = client.patch(
            f"/api/v1/draft-sessions/{draft['id']}",
            json={"revision": draft["revision"], "status": "paused"},
        )
        assert paused.status_code == 200
        rejected = client.post(
            f"/api/v1/draft-sessions/{draft['id']}/post-draft-reports",
            json={
                "draft_revision": paused.json()["revision"],
                "expected_completed_at": "2026-08-02T00:00:00Z",
            },
        )
        assert rejected.status_code == 409
        assert rejected.json()["error"]["code"] == "REPORT_DRAFT_NOT_COMPLETE"

        resumed = client.patch(
            f"/api/v1/draft-sessions/{draft['id']}",
            json={"revision": paused.json()["revision"], "status": "active"},
        )
        assert resumed.status_code == 200
        completed = _complete_draft(client, resumed.json(), players)
        missing_shape = client.post(
            f"/api/v1/draft-sessions/{draft['id']}/post-draft-reports",
            json=_generation_payload(completed),
        )
        assert missing_shape.status_code == 409
        assert (
            missing_shape.json()["error"]["code"]
            == "REPORT_LEAGUE_SHAPE_UNAVAILABLE"
        )
        session_factory = client.app.state.session_factory
        with session_factory() as session:
            assert session.scalar(select(func.count()).select_from(PostDraftReportRow)) == 0


def test_completed_mock_replays_saved_strategy_history(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, players, league = _seed_context(client)
        created = client.post(
            f"/api/v1/boards/{board['id']}/mock-sessions",
            json={
                "name": "Completed Report Mock",
                "league_profile_id": league["id"],
                "draft_format": "snake",
                "third_round_reversal": False,
                "team_count": 2,
                "round_count": 1,
                "user_slot": 1,
                "team_names": ["Your Team", "Fictional CPU"],
                "seed": "4242",
                "randomness": 0,
                "strategy_key": "balanced",
                "fallback_archetypes": {"2": "balanced"},
            },
        )
        assert created.status_code == 201, created.text
        mock = created.json()
        draft = mock["draft"]
        user_pick = client.post(
            f"/api/v1/draft-sessions/{draft['id']}/picks",
            json={
                "revision": draft["revision"],
                "expected_overall_pick": 1,
                "player_id": players[0]["id"],
            },
        )
        assert user_pick.status_code == 200, user_pick.text
        refreshed = client.get(f"/api/v1/mock-sessions/{draft['id']}")
        assert refreshed.status_code == 200
        mock = refreshed.json()
        current = mock["draft"]["current_pick"]
        cpu_pick = client.post(
            f"/api/v1/mock-sessions/{draft['id']}/cpu-pick",
            json={
                "draft_revision": mock["draft"]["revision"],
                "mock_revision": mock["mock"]["revision"],
                "expected_overall_pick": current["overall_pick"],
                "expected_selecting_slot": current["selecting_slot"],
            },
        )
        assert cpu_pick.status_code == 200, cpu_pick.text
        completed = cpu_pick.json()["draft"]
        assert completed["status"] == "completed"

        generated = client.post(
            f"/api/v1/draft-sessions/{draft['id']}/post-draft-reports",
            json=_generation_payload(completed),
        )
        assert generated.status_code == 201, generated.text
        report = generated.json()["report"]
        assert report["draft_mode"] == "mock"
        strategy = next(
            section
            for section in report["sections"]
            if section["section_key"] == "strategy_story"
        )
        assert strategy["availability"] == "supported", strategy["limitation_codes"]
        assert strategy["confidence"] == "high"
        assert strategy["metrics"]["saved_history_loaded"] is True
        assert strategy["metrics"]["guidance_event_count"] >= 1
        assert any(moment["moment_kind"] == "strategy_guidance" for moment in report["moments"])
        assert "PHASE6_STEP7_STRATEGY_STORY_DEFERRED" not in generated.text


def test_mock_strategy_pivot_and_guidance_are_safe_saved_observations(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, players, league = _seed_context(client)
        created = client.post(
            f"/api/v1/boards/{board['id']}/mock-sessions",
            json={
                "name": "Strategy Pivot Report Mock",
                "league_profile_id": league["id"],
                "draft_format": "snake",
                "third_round_reversal": False,
                "team_count": 2,
                "round_count": 2,
                "user_slot": 1,
                "team_names": ["Your Team", "Fictional CPU"],
                "seed": "4243",
                "randomness": 0,
                "strategy_key": "balanced",
                "fallback_archetypes": {"2": "balanced"},
            },
        )
        assert created.status_code == 201, created.text
        mock = created.json()
        picked = client.post(
            f"/api/v1/draft-sessions/{mock['draft']['id']}/picks",
            json={
                "revision": mock["draft"]["revision"],
                "expected_overall_pick": 1,
                "player_id": players[0]["id"],
            },
        )
        assert picked.status_code == 200, picked.text
        refreshed = client.get(f"/api/v1/mock-sessions/{mock['draft']['id']}")
        assert refreshed.status_code == 200
        mock = refreshed.json()
        pivoted = client.patch(
            f"/api/v1/mock-sessions/{mock['draft']['id']}/strategy",
            json={
                "mock_revision": mock["mock"]["revision"],
                "expected_current_overall_pick": 2,
                "strategy_key": "hero_rb",
                "private_user_note": "PRIVATE PIVOT REPORT NOTE",
            },
        )
        assert pivoted.status_code == 200, pivoted.text
        mock = pivoted.json()

        for expected_pick in (2, 3):
            current = mock["draft"]["current_pick"]
            assert current["overall_pick"] == expected_pick
            cpu = client.post(
                f"/api/v1/mock-sessions/{mock['draft']['id']}/cpu-pick",
                json={
                    "draft_revision": mock["draft"]["revision"],
                    "mock_revision": mock["mock"]["revision"],
                    "expected_overall_pick": current["overall_pick"],
                    "expected_selecting_slot": current["selecting_slot"],
                },
            )
            assert cpu.status_code == 200, cpu.text
            mock = cpu.json()

        drafted_ids = {pick["player_id"] for pick in mock["draft"]["picks"]}
        final_player = next(player for player in players if player["id"] not in drafted_ids)
        completed_response = client.post(
            f"/api/v1/draft-sessions/{mock['draft']['id']}/picks",
            json={
                "revision": mock["draft"]["revision"],
                "expected_overall_pick": 4,
                "player_id": final_player["id"],
            },
        )
        assert completed_response.status_code == 200, completed_response.text
        completed = completed_response.json()
        assert completed["status"] == "completed"

        session_factory = client.app.state.session_factory
        with session_factory() as session:
            source_before = (
                tuple(
                    session.execute(
                        select(
                            MockStrategyRevisionRow.id,
                            MockStrategyRevisionRow.sequence_number,
                            MockStrategyRevisionRow.private_user_note,
                        ).order_by(MockStrategyRevisionRow.sequence_number)
                    )
                ),
                tuple(
                    session.execute(
                        select(
                            MockGuidanceEventRow.id,
                            MockGuidanceEventRow.state,
                            MockGuidanceEventRow.status,
                        ).order_by(MockGuidanceEventRow.id)
                    )
                ),
            )
        generated = _generate(client, completed)
        assert generated.status_code == 201, generated.text
        report = generated.json()["report"]
        strategy = next(
            section
            for section in report["sections"]
            if section["section_key"] == "strategy_story"
        )
        assert strategy["availability"] == "supported", strategy["limitation_codes"]
        assert strategy["metrics"]["initial_strategy"] == "balanced"
        assert strategy["metrics"]["final_strategy"] == "hero_rb"
        assert strategy["metrics"]["pivot_count"] == 1
        assert strategy["metrics"]["guidance_event_count"] >= 2
        pivot_moments = [
            moment for moment in report["moments"] if moment["moment_kind"] == "strategy_pivot"
        ]
        guidance_moments = [
            moment
            for moment in report["moments"]
            if moment["moment_kind"] == "strategy_guidance"
        ]
        assert len(pivot_moments) == 1
        assert guidance_moments
        assert pivot_moments[0]["safe_summary"]["previous_strategy"] == "balanced"
        assert pivot_moments[0]["safe_summary"]["next_strategy"] == "hero_rb"
        assert "PRIVATE PIVOT REPORT NOTE" not in generated.text
        assert "random_audit" not in generated.text
        assert "seed" not in generated.text

        with session_factory() as session:
            source_after = (
                tuple(
                    session.execute(
                        select(
                            MockStrategyRevisionRow.id,
                            MockStrategyRevisionRow.sequence_number,
                            MockStrategyRevisionRow.private_user_note,
                        ).order_by(MockStrategyRevisionRow.sequence_number)
                    )
                ),
                tuple(
                    session.execute(
                        select(
                            MockGuidanceEventRow.id,
                            MockGuidanceEventRow.state,
                            MockGuidanceEventRow.status,
                        ).order_by(MockGuidanceEventRow.id)
                    )
                ),
            )
        assert source_after == source_before


def test_live_report_reconstructs_and_deduplicates_frozen_board_choice(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, players, league = _seed_context(client)
        draft = _start_live(
            client,
            board["id"],
            league["id"],
            round_count=3,
        )
        session_factory = client.app.state.session_factory
        rank_by_player = {
            player["id"]: rank for rank, player in enumerate(players[:6], start=1)
        }
        with session_factory() as session:
            candidates = tuple(
                session.scalars(
                    select(DraftCandidateRow).where(
                        DraftCandidateRow.session_id == draft["id"]
                    )
                )
            )
            for candidate in candidates:
                if candidate.player_id in rank_by_player:
                    candidate.manual_rank = rank_by_player[candidate.player_id]
                    candidate.tier_order = 1 if candidate.player_id == players[0]["id"] else 2
                    candidate.favorite = candidate.player_id == players[0]["id"]
            session.commit()

        current = draft
        pick_order = [players[index] for index in (5, 1, 2, 4, 3, 0)]
        for player in pick_order:
            current_pick = current["current_pick"]
            picked = client.post(
                f"/api/v1/draft-sessions/{draft['id']}/picks",
                json={
                    "revision": current["revision"],
                    "expected_overall_pick": current_pick["overall_pick"],
                    "player_id": player["id"],
                },
            )
            assert picked.status_code == 200, picked.text
            current = picked.json()
        assert current["status"] == "completed"
        source_before = _source_state(client, draft["id"])

        generated = _generate(client, current)
        assert generated.status_code == 201, generated.text
        report = generated.json()["report"]
        section = next(
            item
            for item in report["sections"]
            if item["section_key"] == "personal_board_choice_moments"
        )
        assert section["availability"] == "supported"
        assert section["confidence"] == "high"
        assert section["metrics"]["moment_count"] == 1
        moments = [
            moment
            for moment in report["moments"]
            if moment["moment_kind"] == "personal_board_choice"
        ]
        assert len(moments) == 1
        summary = moments[0]["safe_summary"]
        assert summary["first_user_pick"] == 1
        assert summary["last_available_user_pick"] == 5
        assert summary["rank_delta"] == 5
        assert summary["passed_player"]["saved_favorite"] is True
        assert summary["passed_player_draft_outcome"] == {
            "state": "drafted_by_other_slot",
            "overall_pick": 6,
        }
        assert "PRIVATE REPORT TEST NOTE" not in generated.text
        assert "board_note" not in generated.text
        assert "mistake" not in generated.text.casefold()
        assert _source_state(client, draft["id"]) == source_before


def test_late_section_failure_rolls_back_every_new_report_row(
    runtime_settings: RuntimeSettings,
    monkeypatch,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, players, league = _seed_context(client)
        completed = _complete_draft(
            client,
            _start_live(client, board["id"], league["id"], round_count=1),
            players,
        )
        source_before = _source_state(client, completed["id"])
        original = report_service._build_sections

        def invalid_sections(*args, **kwargs):
            sections = list(original(*args, **kwargs))
            sections[-1] = replace(sections[-1], availability="invalid")
            return tuple(sections)

        monkeypatch.setattr(report_service, "_build_sections", invalid_sections)
        failed = client.post(
            f"/api/v1/draft-sessions/{completed['id']}/post-draft-reports",
            json=_generation_payload(completed),
        )
        assert failed.status_code == 500
        assert failed.json()["error"]["code"] == "REPORT_GENERATION_FAILED"
        assert _source_state(client, completed["id"]) == source_before

        session_factory = client.app.state.session_factory
        with session_factory() as session:
            for model in (
                PostDraftReportRow,
                PostDraftReportPlayerRow,
                PostDraftReportSectionRow,
                PostDraftReportMomentRow,
            ):
                assert session.scalar(select(func.count()).select_from(model)) == 0


def test_compatible_report_preview_is_descriptive_ordered_and_read_only(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, players, league = _seed_context(client)
        first_draft = _complete_draft(
            client,
            _start_live(client, board["id"], league["id"]),
            players,
        )
        second_order = [players[1], players[0], players[3], players[2], *players[4:]]
        second_draft = _complete_draft(
            client,
            _start_live(client, board["id"], league["id"]),
            second_order,
        )
        first_report = _generate(client, first_draft).json()["report"]
        second_report = _generate(client, second_draft).json()["report"]
        session_factory = client.app.state.session_factory
        with session_factory() as session:
            counts_before = tuple(
                int(session.scalar(select(func.count()).select_from(model)) or 0)
                for model in (
                    PostDraftReportRow,
                    PostDraftReportPlayerRow,
                    PostDraftReportSectionRow,
                    PostDraftReportMomentRow,
                )
            )

        response = client.post(
            "/api/v1/post-draft-report-comparisons/preview",
            json={"report_ids": [first_report["id"], second_report["id"]]},
        )
        assert response.status_code == 200, response.text
        comparison = response.json()
        assert comparison["baseline_report_id"] == first_report["id"]
        assert [report["report_id"] for report in comparison["reports"]] == [
            first_report["id"],
            second_report["id"],
        ]
        assert [section["section_key"] for section in comparison["sections"]] == SECTION_KEYS
        inventory = next(
            section
            for section in comparison["sections"]
            if section["section_key"] == "position_inventory"
        )
        assert inventory["comparison_state"] == "comparable"
        second_delta = inventory["values"][1]["delta_from_first"]["position_counts"]
        assert any(delta != 0 for delta in second_delta.values())
        strategy = next(
            section
            for section in comparison["sections"]
            if section["section_key"] == "strategy_story"
        )
        assert strategy["comparison_state"] == "not_comparable"
        unsupported = next(
            section
            for section in comparison["sections"]
            if section["section_key"] == "long_term_value"
        )
        assert all(value["delta_from_first"] == {} for value in unsupported["values"])
        serialized = response.text.casefold()
        assert "private report test note" not in serialized
        assert "best roster" not in serialized
        assert "draft grade" not in serialized

        with session_factory() as session:
            counts_after = tuple(
                int(session.scalar(select(func.count()).select_from(model)) or 0)
                for model in (
                    PostDraftReportRow,
                    PostDraftReportPlayerRow,
                    PostDraftReportSectionRow,
                    PostDraftReportMomentRow,
                )
            )
        assert counts_after == counts_before

        duplicate = client.post(
            "/api/v1/post-draft-report-comparisons/preview",
            json={"report_ids": [first_report["id"], first_report["id"]]},
        )
        assert duplicate.status_code == 422
        missing = client.post(
            "/api/v1/post-draft-report-comparisons/preview",
            json={"report_ids": [first_report["id"], "missing-report"]},
        )
        assert missing.status_code == 404

        incompatible_draft = _complete_draft(
            client,
            _start_live(client, board["id"], league["id"], round_count=1),
            players,
        )
        incompatible_report = _generate(client, incompatible_draft).json()["report"]
        incompatible = client.post(
            "/api/v1/post-draft-report-comparisons/preview",
            json={"report_ids": [first_report["id"], incompatible_report["id"]]},
        )
        assert incompatible.status_code == 409
        assert incompatible.json()["error"]["code"] == "REPORT_COMPARISON_INCOMPATIBLE"
