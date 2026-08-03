from __future__ import annotations

import pytest

from friendly_hub.domains.reports.comparison import (
    ComparisonSectionSource,
    build_comparison_sections,
)
from friendly_hub.domains.reports.definitions import SECTION_KEYS


def _metrics(section_key: str, *, second: bool = False) -> dict[str, object]:
    count = 3 if second else 2
    values: dict[str, dict[str, object]] = {
        "draft_summary": {
            "mode": "mock",
            "draft_format": "snake",
            "third_round_reversal": False,
            "team_count": 2,
            "round_count": 2,
            "total_user_picks": 2,
            "starter_slots": 1,
            "bench_slots": 1,
        },
        "position_inventory": {"position_counts": {"WR": count}},
        "starter_coverage": {
            "starter_slots_total": 1,
            "starter_slots_filled": 1,
            "unfilled_slot_keys": [],
            "depth_counts": {"WR": count - 1},
        },
        "roster_concentration": {
            "position_share_basis_points": {"WR": 10_000},
            "bands": ["highly_concentrated"],
            "starter_position_gaps": [],
            "surplus_after_starter_assignment": {"WR": count - 1},
        },
        "year_one_production_context": {
            "roster_players": count,
            "covered_players": count,
            "uncovered_players": 0,
            "coverage_basis_points": 10_000,
            "band_distribution": {"high": count},
            "freshness_counts": {"fresh": count},
        },
        "dynasty_market_context": {
            "roster_players": count,
            "covered_players": count,
            "uncovered_players": 0,
            "coverage_basis_points": 10_000,
            "band_distribution": {"strong": count},
            "freshness_counts": {"fresh": count},
        },
        "age_risk_profile": {
            "roster_players": count,
            "covered_players": count,
            "uncovered_players": 0,
            "coverage_basis_points": 10_000,
            "band_distribution": {"middle": count},
            "freshness_counts": {"fresh": count},
        },
        "long_term_value": {},
        "liquidity": {},
        "player_fragility": {},
        "strategy_story": {
            "initial_strategy": "balanced",
            "final_strategy": "balanced",
            "strategy_definition_version": "strategy-v1",
            "pivot_count": 1 if second else 0,
            "guidance_event_count": count,
            "guidance_state_counts": {"on_plan": count},
            "guidance_status_counts": {"open": count},
        },
        "personal_board_choice_moments": {
            "moment_count": count,
            "qualifying_moment_count": count,
            "truncated": False,
        },
        "recorded_alert_moments": {
            "history_state": "available",
            "event_count": count,
            "included_event_count": count,
            "truncated": False,
            "event_kind_counts": {"value_watch": count},
            "event_status_counts": {"open": count},
        },
        "evidence_limits": {"limited_or_unavailable_sections": []},
    }
    return values[section_key]


def _sources(*, second_mode: str = "mock"):
    unavailable = {"long_term_value", "liquidity", "player_fragility"}
    return {
        section_key: (
            ComparisonSectionSource(
                report_id="report-a",
                draft_mode="mock",
                availability="unavailable" if section_key in unavailable else "supported",
                confidence="high",
                metrics=_metrics(section_key),
            ),
            ComparisonSectionSource(
                report_id="report-b",
                draft_mode=second_mode,
                availability="unavailable" if section_key in unavailable else "supported",
                confidence="high",
                metrics=_metrics(section_key, second=True),
            ),
        )
        for section_key in SECTION_KEYS
    }


def test_comparison_projects_only_safe_fields_and_exact_signed_deltas() -> None:
    results = build_comparison_sections(_sources(), report_count=2)

    assert [result.section_key for result in results] == list(SECTION_KEYS)
    inventory = next(result for result in results if result.section_key == "position_inventory")
    assert inventory.comparison_state == "comparable"
    assert inventory.values[0].delta_from_first == {"position_counts": {"WR": 0}}
    assert inventory.values[1].delta_from_first == {"position_counts": {"WR": 1}}
    assert set(inventory.values[0].metrics) == {"position_counts"}
    unsupported = next(result for result in results if result.section_key == "liquidity")
    assert unsupported.comparison_state == "not_comparable"
    assert all(value.delta_from_first == {} for value in unsupported.values)


def test_mixed_modes_keep_global_comparison_but_not_strategy_deltas() -> None:
    results = build_comparison_sections(_sources(second_mode="live"), report_count=2)

    strategy = next(result for result in results if result.section_key == "strategy_story")
    inventory = next(result for result in results if result.section_key == "position_inventory")
    assert strategy.comparison_state == "not_comparable"
    assert "STRATEGY_COMPARISON_REQUIRES_COMPATIBLE_MOCKS" in strategy.limitation_codes
    assert inventory.comparison_state == "comparable"


def test_comparison_projection_rejects_free_form_or_negative_saved_metrics() -> None:
    for invalid in (
        {"position_counts": {"WR": -1}},
        {"position_counts": {"PRIVATE NOTE": 1}},
    ):
        sources = _sources()
        first, second = sources["position_inventory"]
        sources["position_inventory"] = (
            ComparisonSectionSource(
                report_id=first.report_id,
                draft_mode=first.draft_mode,
                availability=first.availability,
                confidence=first.confidence,
                metrics=invalid,
            ),
            second,
        )
        with pytest.raises(ValueError):
            build_comparison_sections(sources, report_count=2)
