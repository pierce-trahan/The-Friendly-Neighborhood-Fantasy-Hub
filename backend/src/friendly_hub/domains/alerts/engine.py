from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from fractions import Fraction
from math import ceil, floor

from friendly_hub.domains.alerts.definitions import (
    DEFAULT_TARGET_SAFETY_BUFFER,
    DEFAULT_VALUE_GAP_MINIMUM,
    MAX_COST_REFERENCES,
    ConfidenceLevel,
    FormatCompatibility,
    FreshnessState,
    ReturnRisk,
)


@dataclass(frozen=True)
class IntegerRange:
    low: int
    high: int

    def __post_init__(self) -> None:
        if not _is_integer(self.low) or not _is_integer(self.high):
            raise ValueError("range endpoints must be integers")
        if self.low > self.high:
            raise ValueError("range low must not exceed high")


@dataclass(frozen=True)
class ConfidenceAssessment:
    level: ConfidenceLevel
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class CurrentPickValue:
    overall_pick: int
    value: IntegerRange

    def __post_init__(self) -> None:
        _validate_positive_integer(self.overall_pick, "overall_pick")
        _validate_non_negative_range(self.value, "pick value")


@dataclass(frozen=True)
class PickAssetValue:
    asset_key: str
    season_offset: int
    round_number: int
    value: IntegerRange

    def __post_init__(self) -> None:
        if not isinstance(self.asset_key, str) or not self.asset_key:
            raise ValueError("asset_key must not be empty")
        _validate_positive_integer(self.season_offset, "season_offset")
        _validate_positive_integer(self.round_number, "round_number")
        _validate_non_negative_range(self.value, "asset value")


def market_gap_range(
    *,
    current_overall_pick: int,
    expected_pick: IntegerRange,
) -> IntegerRange:
    _validate_positive_integer(current_overall_pick, "current_overall_pick")
    _validate_positive_range(expected_pick, "expected pick")
    return IntegerRange(
        low=current_overall_pick - expected_pick.high,
        high=current_overall_pick - expected_pick.low,
    )


def personal_qualifies(
    *,
    tier_order: int | None,
    favorite: bool,
    eligible_tier_count: int = 2,
) -> bool:
    if not isinstance(favorite, bool):
        raise ValueError("favorite must be a boolean")
    if not _is_integer(eligible_tier_count) or eligible_tier_count < 0:
        raise ValueError("eligible_tier_count must be a non-negative integer")
    if tier_order is not None:
        _validate_positive_integer(tier_order, "tier_order")
    return favorite or (
        tier_order is not None
        and eligible_tier_count > 0
        and tier_order <= eligible_tier_count
    )


def value_alert_eligible(
    *,
    personal_qualified: bool,
    gap: IntegerRange,
    confidence: ConfidenceLevel,
    minimum_gap: int = DEFAULT_VALUE_GAP_MINIMUM,
) -> bool:
    if not isinstance(personal_qualified, bool):
        raise ValueError("personal_qualified must be a boolean")
    if not _is_integer(minimum_gap) or minimum_gap < 0:
        raise ValueError("minimum_gap must be a non-negative integer")
    if confidence not in ("high", "medium", "low", "unavailable"):
        raise ValueError("confidence is not supported")
    return (
        personal_qualified
        and confidence != "unavailable"
        and gap.low >= minimum_gap
    )


def return_risk_band(
    *,
    expected_pick: IntegerRange | None,
    next_user_pick: int | None,
) -> ReturnRisk:
    if expected_pick is None or next_user_pick is None:
        return "unavailable"
    _validate_positive_range(expected_pick, "expected pick")
    _validate_positive_integer(next_user_pick, "next_user_pick")
    if expected_pick.low >= next_user_pick:
        return "likely_to_return"
    if expected_pick.high < next_user_pick:
        return "unlikely_to_return"
    return "uncertain"


def elapsed_freshness(
    *,
    evidence_as_of: datetime,
    evaluated_at: datetime,
    fresh_through_days: int,
    aging_through_days: int,
    stale_through_days: int,
) -> FreshnessState:
    evidence_utc = _aware_utc(evidence_as_of, "evidence_as_of")
    evaluated_utc = _aware_utc(evaluated_at, "evaluated_at")
    _validate_freshness_thresholds(
        fresh_through_days,
        aging_through_days,
        stale_through_days,
    )
    age_days = (evaluated_utc.date() - evidence_utc.date()).days
    if age_days < 0:
        return "invalid"
    if age_days <= fresh_through_days:
        return "fresh"
    if age_days <= aging_through_days:
        return "aging"
    if age_days <= stale_through_days:
        return "stale"
    return "expired"


def season_label_freshness(
    *,
    current_season: int,
    evidence_season: int | None,
) -> FreshnessState:
    _validate_positive_integer(current_season, "current_season")
    if evidence_season is None:
        return "expired"
    _validate_positive_integer(evidence_season, "evidence_season")
    season_age = current_season - evidence_season
    if season_age < 0:
        return "invalid"
    if season_age == 0:
        return "fresh"
    if season_age == 1:
        return "aging"
    return "stale"


def age_risk_freshness(validity: str) -> FreshnessState:
    states: dict[str, FreshnessState] = {
        "valid": "fresh",
        "source_conflict": "stale",
        "missing_or_invalid": "expired",
    }
    try:
        return states[validity]
    except (KeyError, TypeError) as exc:
        raise ValueError("age-risk validity is not supported") from exc


def assess_confidence(
    *,
    exact_mapping: bool,
    freshness: FreshnessState,
    format_compatibility: FormatCompatibility,
    expected_pick: IntegerRange | None,
    critical_limitations: Iterable[str] = (),
) -> ConfidenceAssessment:
    if not isinstance(exact_mapping, bool):
        raise ValueError("exact_mapping must be a boolean")
    if freshness not in ("fresh", "aging", "stale", "expired", "invalid"):
        raise ValueError("freshness is not supported")
    if format_compatibility not in (
        "exact",
        "family",
        "partial",
        "incompatible",
        "unknown",
    ):
        raise ValueError("format compatibility is not supported")
    limitations = _normalized_codes(critical_limitations)

    unavailable_reasons: list[str] = []
    if not exact_mapping:
        unavailable_reasons.append("MAPPING_NOT_EXACT")
    if expected_pick is None:
        unavailable_reasons.append("EXPECTED_SELECTION_UNAVAILABLE")
    else:
        _validate_positive_range(expected_pick, "expected pick")
    if freshness in ("expired", "invalid"):
        unavailable_reasons.append(f"FRESHNESS_{freshness.upper()}")
    if format_compatibility in ("incompatible", "unknown"):
        unavailable_reasons.append(
            f"FORMAT_{format_compatibility.upper()}"
        )
    if unavailable_reasons:
        return ConfidenceAssessment(
            level="unavailable",
            reason_codes=tuple(sorted(unavailable_reasons)),
        )

    assert expected_pick is not None
    width = expected_pick.high - expected_pick.low
    if (
        freshness == "fresh"
        and format_compatibility == "exact"
        and width <= 8
        and not limitations
    ):
        return ConfidenceAssessment("high", ("CONFIDENCE_HIGH",))
    if (
        freshness in ("fresh", "aging")
        and format_compatibility in ("exact", "family")
        and width <= 20
        and not limitations
    ):
        reasons = ["CONFIDENCE_MEDIUM"]
        if freshness == "aging":
            reasons.append("FRESHNESS_AGING")
        if format_compatibility == "family":
            reasons.append("FORMAT_FAMILY")
        if width > 8:
            reasons.append("EXPECTED_WINDOW_WIDER_THAN_HIGH")
        return ConfidenceAssessment("medium", tuple(sorted(reasons)))

    reasons = ["CONFIDENCE_LOW"]
    if freshness == "stale":
        reasons.append("FRESHNESS_STALE")
    if format_compatibility == "partial":
        reasons.append("FORMAT_PARTIAL")
    if width > 20:
        reasons.append("EXPECTED_WINDOW_BROAD")
    if limitations:
        reasons.extend(limitations)
        reasons.append("CRITICAL_LIMITATION_PRESENT")
    return ConfidenceAssessment("low", tuple(sorted(reasons)))


def target_pick_window(
    *,
    current_overall_pick: int,
    next_user_pick: int,
    expected_pick: IntegerRange,
    safety_buffer: int = DEFAULT_TARGET_SAFETY_BUFFER,
) -> IntegerRange | None:
    _validate_positive_integer(current_overall_pick, "current_overall_pick")
    _validate_positive_integer(next_user_pick, "next_user_pick")
    _validate_positive_range(expected_pick, "expected pick")
    if next_user_pick <= current_overall_pick:
        raise ValueError("next_user_pick must be after the current pick")
    if not _is_integer(safety_buffer) or safety_buffer < 0:
        raise ValueError("safety_buffer must be a non-negative integer")
    if (
        return_risk_band(
            expected_pick=expected_pick,
            next_user_pick=next_user_pick,
        )
        != "unlikely_to_return"
    ):
        return None

    intersection_low = max(current_overall_pick, expected_pick.low)
    intersection_high = min(next_user_pick - 1, expected_pick.high)
    if intersection_low > intersection_high:
        return None
    target_low = max(current_overall_pick, intersection_low - safety_buffer)
    target_high = max(target_low, intersection_high - safety_buffer)
    return IntegerRange(target_low, min(target_high, next_user_pick - 1))


def interpolate_current_pick_value(
    *,
    overall_pick: int,
    curve: Sequence[CurrentPickValue],
) -> IntegerRange | None:
    _validate_positive_integer(overall_pick, "overall_pick")
    ordered = _validated_curve(curve)
    if overall_pick < ordered[0].overall_pick or overall_pick > ordered[-1].overall_pick:
        return None
    for point in ordered:
        if point.overall_pick == overall_pick:
            return point.value
    for left, right in zip(ordered, ordered[1:], strict=False):
        if left.overall_pick < overall_pick < right.overall_pick:
            offset = overall_pick - left.overall_pick
            span = right.overall_pick - left.overall_pick
            low = Fraction(left.value.low) + (
                Fraction(right.value.low - left.value.low) * offset / span
            )
            high = Fraction(left.value.high) + (
                Fraction(right.value.high - left.value.high) * offset / span
            )
            return IntegerRange(floor(low), ceil(high))
    raise AssertionError("validated curve did not bracket the requested pick")


def incremental_trade_cost(
    *,
    user_next_pick: int,
    target_window: IntegerRange,
    curve: Sequence[CurrentPickValue],
) -> IntegerRange | None:
    _validate_positive_integer(user_next_pick, "user_next_pick")
    _validate_positive_range(target_window, "target window")
    if target_window.high >= user_next_pick:
        raise ValueError("target window must end before the user pick")
    user_value = interpolate_current_pick_value(
        overall_pick=user_next_pick,
        curve=curve,
    )
    earliest_target = interpolate_current_pick_value(
        overall_pick=target_window.low,
        curve=curve,
    )
    latest_target = interpolate_current_pick_value(
        overall_pick=target_window.high,
        curve=curve,
    )
    if user_value is None or earliest_target is None or latest_target is None:
        return None
    return IntegerRange(
        low=max(0, latest_target.low - user_value.high),
        high=max(0, earliest_target.high - user_value.low),
    )


def match_pick_cost_references(
    *,
    incremental_cost: IntegerRange,
    assets: Sequence[PickAssetValue],
    limit: int = MAX_COST_REFERENCES,
) -> tuple[PickAssetValue, ...]:
    _validate_non_negative_range(incremental_cost, "incremental cost")
    if not _is_integer(limit) or limit < 1 or limit > MAX_COST_REFERENCES:
        raise ValueError(f"limit must be between 1 and {MAX_COST_REFERENCES}")
    asset_keys = [asset.asset_key for asset in assets]
    if len(asset_keys) != len(set(asset_keys)):
        raise ValueError("pick asset keys must be unique")
    overlapping = [
        asset
        for asset in assets
        if asset.value.low <= incremental_cost.high
        and asset.value.high >= incremental_cost.low
    ]
    return tuple(
        sorted(
            overlapping,
            key=lambda asset: (
                asset.value.low + asset.value.high,
                asset.season_offset,
                asset.round_number,
                asset.asset_key,
            ),
        )[:limit]
    )


def _validated_curve(
    curve: Sequence[CurrentPickValue],
) -> tuple[CurrentPickValue, ...]:
    if not curve:
        raise ValueError("pick curve must not be empty")
    picks = [point.overall_pick for point in curve]
    if len(picks) != len(set(picks)):
        raise ValueError("pick curve overall picks must be unique")
    ordered = tuple(sorted(curve, key=lambda point: point.overall_pick))
    for left, right in zip(ordered, ordered[1:], strict=False):
        if (
            left.value.low < right.value.low
            or left.value.high < right.value.high
        ):
            raise ValueError("pick curve must be monotonic")
    return ordered


def _normalized_codes(codes: Iterable[str]) -> tuple[str, ...]:
    normalized: set[str] = set()
    for code in codes:
        if not isinstance(code, str) or not code:
            raise ValueError("limitation codes must not be empty")
        normalized.add(code)
    return tuple(sorted(normalized))


def _validate_freshness_thresholds(
    fresh: int,
    aging: int,
    stale: int,
) -> None:
    if any(not _is_integer(value) or value < 0 for value in (fresh, aging, stale)):
        raise ValueError("freshness thresholds must be non-negative integers")
    if not fresh < aging < stale:
        raise ValueError("freshness thresholds must increase")


def _aware_utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _validate_positive_range(value: IntegerRange, name: str) -> None:
    if not isinstance(value, IntegerRange) or value.low < 1:
        raise ValueError(f"{name} endpoints must be positive")


def _validate_non_negative_range(value: IntegerRange, name: str) -> None:
    if not isinstance(value, IntegerRange) or value.low < 0:
        raise ValueError(f"{name} endpoints must not be negative")


def _validate_positive_integer(value: int, name: str) -> None:
    if not _is_integer(value) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
