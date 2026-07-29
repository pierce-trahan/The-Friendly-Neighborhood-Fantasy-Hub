from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from friendly_hub.domains.alerts.definitions import (
    ALERT_ENGINE_VERSION,
    ALERT_RULE_VERSION,
)
from friendly_hub.domains.alerts.engine import (
    CurrentPickValue,
    IntegerRange,
    PickAssetValue,
    age_risk_freshness,
    assess_confidence,
    elapsed_freshness,
    incremental_trade_cost,
    interpolate_current_pick_value,
    market_gap_range,
    match_pick_cost_references,
    personal_qualifies,
    return_risk_band,
    season_label_freshness,
    target_pick_window,
    value_alert_eligible,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _engine_fixture() -> dict[str, Any]:
    return _read_json(
        _project_root()
        / "tests"
        / "fixtures"
        / "alert_engine"
        / "phase-5-engine-v1.expected.json"
    )


def _evidence_fixture() -> dict[str, Any]:
    return _read_json(
        _project_root()
        / "tests"
        / "fixtures"
        / "alert_evidence"
        / "entropy-alert-evidence.synthetic.json"
    )


def _curve_and_assets() -> tuple[
    tuple[CurrentPickValue, ...],
    tuple[PickAssetValue, ...],
]:
    current: list[CurrentPickValue] = []
    future: list[PickAssetValue] = []
    for row in _evidence_fixture()["pick_values"]:
        value = IntegerRange(row["value_low"], row["value_high"])
        if row["asset_type"] == "current_draft_pick":
            current.append(CurrentPickValue(row["overall_pick"], value))
        else:
            future.append(
                PickAssetValue(
                    asset_key=row["asset_key"],
                    season_offset=row["season_offset"],
                    round_number=row["round"],
                    value=value,
                )
            )
    return tuple(current), tuple(future)


def test_versioned_market_gap_fixture_and_personal_gate() -> None:
    fixture = _engine_fixture()
    assert fixture["engine_version"] == ALERT_ENGINE_VERSION
    assert fixture["rule_version"] == ALERT_RULE_VERSION

    for case in fixture["market_gap_cases"]:
        gap = market_gap_range(
            current_overall_pick=case["current_pick"],
            expected_pick=IntegerRange(
                case["expected_low"],
                case["expected_high"],
            ),
        )
        assert gap == IntegerRange(case["gap_low"], case["gap_high"])
        assert value_alert_eligible(
            personal_qualified=True,
            gap=gap,
            confidence="high",
        ) is case["default_alert"]

    assert personal_qualifies(tier_order=1, favorite=False)
    assert personal_qualifies(tier_order=2, favorite=False)
    assert not personal_qualifies(tier_order=3, favorite=False)
    assert personal_qualifies(
        tier_order=None,
        favorite=True,
        eligible_tier_count=0,
    )
    assert not value_alert_eligible(
        personal_qualified=False,
        gap=IntegerRange(20, 30),
        confidence="high",
    )
    assert not value_alert_eligible(
        personal_qualified=True,
        gap=IntegerRange(20, 30),
        confidence="unavailable",
    )
    assert not value_alert_eligible(
        personal_qualified=True,
        gap=IntegerRange(5, 12),
        confidence="medium",
    )
    assert value_alert_eligible(
        personal_qualified=True,
        gap=IntegerRange(6, 12),
        confidence="low",
    )


def test_return_risk_fixture_and_missing_inputs() -> None:
    for case in _engine_fixture()["return_risk_cases"]:
        assert return_risk_band(
            expected_pick=IntegerRange(
                case["expected_low"],
                case["expected_high"],
            ),
            next_user_pick=case["next_user_pick"],
        ) == case["result"]
    assert return_risk_band(
        expected_pick=None,
        next_user_pick=40,
    ) == "unavailable"
    assert return_risk_band(
        expected_pick=IntegerRange(30, 39),
        next_user_pick=None,
    ) == "unavailable"


def test_freshness_fixture_and_non_elapsed_policies() -> None:
    policy = _read_json(
        _project_root()
        / "docs"
        / "requirements"
        / "alert-freshness-policy.v1.json"
    )
    rule = policy["elapsed_day_rules"]["expected_selection"]
    for case in _engine_fixture()["freshness_cases"]:
        assert elapsed_freshness(
            evidence_as_of=_utc(case["evidence_as_of"]),
            evaluated_at=_utc(case["evaluated_at"]),
            fresh_through_days=rule["fresh_through_days"],
            aging_through_days=rule["aging_through_days"],
            stale_through_days=rule["stale_through_days"],
        ) == case["result"]

    assert season_label_freshness(
        current_season=2026,
        evidence_season=2026,
    ) == "fresh"
    assert season_label_freshness(
        current_season=2026,
        evidence_season=2025,
    ) == "aging"
    assert season_label_freshness(
        current_season=2026,
        evidence_season=2024,
    ) == "stale"
    assert season_label_freshness(
        current_season=2026,
        evidence_season=None,
    ) == "expired"
    assert season_label_freshness(
        current_season=2026,
        evidence_season=2027,
    ) == "invalid"
    assert age_risk_freshness("valid") == "fresh"
    assert age_risk_freshness("source_conflict") == "stale"
    assert age_risk_freshness("missing_or_invalid") == "expired"


def test_confidence_paths_are_bounded_and_explainable() -> None:
    high = assess_confidence(
        exact_mapping=True,
        freshness="fresh",
        format_compatibility="exact",
        expected_pick=IntegerRange(4, 12),
    )
    assert high.level == "high"
    assert high.reason_codes == ("CONFIDENCE_HIGH",)

    aging = assess_confidence(
        exact_mapping=True,
        freshness="aging",
        format_compatibility="exact",
        expected_pick=IntegerRange(4, 12),
    )
    assert aging.level == "medium"
    assert "FRESHNESS_AGING" in aging.reason_codes

    family = assess_confidence(
        exact_mapping=True,
        freshness="fresh",
        format_compatibility="family",
        expected_pick=IntegerRange(10, 30),
    )
    assert family.level == "medium"
    assert family.reason_codes == (
        "CONFIDENCE_MEDIUM",
        "EXPECTED_WINDOW_WIDER_THAN_HIGH",
        "FORMAT_FAMILY",
    )

    broad = assess_confidence(
        exact_mapping=True,
        freshness="fresh",
        format_compatibility="exact",
        expected_pick=IntegerRange(10, 31),
    )
    assert broad.level == "low"
    assert "EXPECTED_WINDOW_BROAD" in broad.reason_codes

    stale = assess_confidence(
        exact_mapping=True,
        freshness="stale",
        format_compatibility="exact",
        expected_pick=IntegerRange(10, 18),
    )
    assert stale.level == "low"
    assert "FRESHNESS_STALE" in stale.reason_codes

    limited = assess_confidence(
        exact_mapping=True,
        freshness="fresh",
        format_compatibility="exact",
        expected_pick=IntegerRange(10, 18),
        critical_limitations=("SOURCE_PARTIAL", "SOURCE_PARTIAL"),
    )
    assert limited.level == "low"
    assert limited.reason_codes == (
        "CONFIDENCE_LOW",
        "CRITICAL_LIMITATION_PRESENT",
        "SOURCE_PARTIAL",
    )

    for unavailable in (
        assess_confidence(
            exact_mapping=False,
            freshness="fresh",
            format_compatibility="exact",
            expected_pick=IntegerRange(10, 18),
        ),
        assess_confidence(
            exact_mapping=True,
            freshness="fresh",
            format_compatibility="exact",
            expected_pick=None,
        ),
        assess_confidence(
            exact_mapping=True,
            freshness="expired",
            format_compatibility="exact",
            expected_pick=IntegerRange(10, 18),
        ),
        assess_confidence(
            exact_mapping=True,
            freshness="fresh",
            format_compatibility="incompatible",
            expected_pick=IntegerRange(10, 18),
        ),
    ):
        assert unavailable.level == "unavailable"


def test_target_window_fixture_and_absent_ranges() -> None:
    for case in _engine_fixture()["target_window_cases"]:
        assert target_pick_window(
            current_overall_pick=case["current_pick"],
            next_user_pick=case["next_user_pick"],
            expected_pick=IntegerRange(
                case["expected_low"],
                case["expected_high"],
            ),
            safety_buffer=case["safety_buffer"],
        ) == IntegerRange(case["target_low"], case["target_high"])

    assert target_pick_window(
        current_overall_pick=35,
        next_user_pick=50,
        expected_pick=IntegerRange(50, 60),
    ) is None
    assert target_pick_window(
        current_overall_pick=49,
        next_user_pick=50,
        expected_pick=IntegerRange(42, 48),
    ) is None


def test_pick_curve_interpolation_and_validation() -> None:
    curve, _ = _curve_and_assets()
    assert interpolate_current_pick_value(
        overall_pick=40,
        curve=curve,
    ) == IntegerRange(540, 590)
    assert interpolate_current_pick_value(
        overall_pick=46,
        curve=curve,
    ) == IntegerRange(501, 548)
    assert interpolate_current_pick_value(
        overall_pick=241,
        curve=curve,
    ) is None

    duplicate = (*curve, curve[0])
    with pytest.raises(ValueError, match="unique"):
        interpolate_current_pick_value(overall_pick=40, curve=duplicate)
    non_monotonic = (
        CurrentPickValue(1, IntegerRange(100, 110)),
        CurrentPickValue(2, IntegerRange(120, 130)),
    )
    with pytest.raises(ValueError, match="monotonic"):
        interpolate_current_pick_value(
            overall_pick=1,
            curve=non_monotonic,
        )


def test_trade_cost_fixture_is_pick_only_bounded_and_deterministic() -> None:
    curve, assets = _curve_and_assets()
    case = _engine_fixture()["trade_cost_case"]
    incremental = incremental_trade_cost(
        user_next_pick=case["user_next_pick"],
        target_window=IntegerRange(
            case["target_low"],
            case["target_high"],
        ),
        curve=curve,
    )
    assert incremental == IntegerRange(
        case["increment_low"],
        case["increment_high"],
    )
    assert incremental is not None
    references = match_pick_cost_references(
        incremental_cost=incremental,
        assets=assets,
    )
    assert [reference.asset_key for reference in references] == case["asset_keys"]
    assert all(not hasattr(reference, "player_id") for reference in references)

    capped = match_pick_cost_references(
        incremental_cost=IntegerRange(0, 1000),
        assets=assets,
    )
    assert len(capped) == 3
    assert capped == match_pick_cost_references(
        incremental_cost=IntegerRange(0, 1000),
        assets=tuple(reversed(assets)),
    )
    with pytest.raises(ValueError, match="unique"):
        match_pick_cost_references(
            incremental_cost=IntegerRange(0, 1000),
            assets=(*assets, assets[0]),
        )


def test_invalid_coordinates_and_categories_fail_closed() -> None:
    with pytest.raises(ValueError, match="range low"):
        IntegerRange(2, 1)
    with pytest.raises(ValueError, match="positive"):
        market_gap_range(
            current_overall_pick=0,
            expected_pick=IntegerRange(1, 2),
        )
    with pytest.raises(ValueError, match="favorite"):
        personal_qualifies(tier_order=1, favorite=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timezone-aware"):
        elapsed_freshness(
            evidence_as_of=datetime(2026, 7, 28),
            evaluated_at=_utc("2026-07-28T00:00:00Z"),
            fresh_through_days=7,
            aging_through_days=21,
            stale_through_days=45,
        )
    with pytest.raises(ValueError, match="increase"):
        elapsed_freshness(
            evidence_as_of=_utc("2026-07-28T00:00:00Z"),
            evaluated_at=_utc("2026-07-28T00:00:00Z"),
            fresh_through_days=7,
            aging_through_days=7,
            stale_through_days=45,
        )
    with pytest.raises(ValueError, match="validity"):
        age_risk_freshness("guessed")
    with pytest.raises(ValueError, match="after the current"):
        target_pick_window(
            current_overall_pick=50,
            next_user_pick=50,
            expected_pick=IntegerRange(40, 45),
        )
    with pytest.raises(ValueError, match="end before"):
        incremental_trade_cost(
            user_next_pick=50,
            target_window=IntegerRange(40, 50),
            curve=(CurrentPickValue(40, IntegerRange(100, 110)),),
        )
    with pytest.raises(ValueError, match="between 1 and 3"):
        match_pick_cost_references(
            incremental_cost=IntegerRange(0, 10),
            assets=(),
            limit=4,
        )
