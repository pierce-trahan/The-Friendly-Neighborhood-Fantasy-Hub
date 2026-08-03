from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from friendly_hub.domains.reports.definitions import SECTION_KEYS, SECTION_TITLES
from friendly_hub.domains.reports.engine import render_explanation

ComparisonState = Literal["comparable", "not_comparable"]

_SAFE_FIELDS: dict[str, tuple[str, ...]] = {
    "draft_summary": (
        "mode",
        "draft_format",
        "third_round_reversal",
        "team_count",
        "round_count",
        "total_user_picks",
        "starter_slots",
        "bench_slots",
    ),
    "position_inventory": ("position_counts",),
    "starter_coverage": (
        "starter_slots_total",
        "starter_slots_filled",
        "unfilled_slot_keys",
        "depth_counts",
    ),
    "roster_concentration": (
        "position_share_basis_points",
        "bands",
        "starter_position_gaps",
        "surplus_after_starter_assignment",
    ),
    "year_one_production_context": (
        "roster_players",
        "covered_players",
        "uncovered_players",
        "coverage_basis_points",
        "band_distribution",
        "freshness_counts",
    ),
    "dynasty_market_context": (
        "roster_players",
        "covered_players",
        "uncovered_players",
        "coverage_basis_points",
        "band_distribution",
        "freshness_counts",
    ),
    "age_risk_profile": (
        "roster_players",
        "covered_players",
        "uncovered_players",
        "coverage_basis_points",
        "band_distribution",
        "freshness_counts",
    ),
    "long_term_value": (),
    "liquidity": (),
    "player_fragility": (),
    "strategy_story": (
        "initial_strategy",
        "final_strategy",
        "strategy_definition_version",
        "pivot_count",
        "guidance_event_count",
        "guidance_state_counts",
        "guidance_status_counts",
    ),
    "personal_board_choice_moments": (
        "moment_count",
        "qualifying_moment_count",
        "truncated",
    ),
    "recorded_alert_moments": (
        "history_state",
        "event_count",
        "included_event_count",
        "truncated",
        "event_kind_counts",
        "event_status_counts",
    ),
    "evidence_limits": ("limited_or_unavailable_sections",),
}

_DELTA_FIELDS: dict[str, tuple[str, ...]] = {
    "position_inventory": ("position_counts",),
    "starter_coverage": ("starter_slots_filled", "depth_counts"),
    "year_one_production_context": ("band_distribution",),
    "dynasty_market_context": ("band_distribution",),
    "age_risk_profile": ("band_distribution",),
    "strategy_story": ("pivot_count", "guidance_state_counts"),
    "personal_board_choice_moments": ("moment_count",),
    "recorded_alert_moments": ("event_count",),
}

_ALWAYS_NOT_COMPARABLE = {"long_term_value", "liquidity", "player_fragility"}
_BASE_LIMITATIONS = (
    "DESCRIPTIVE_COMPARISON_ONLY",
    "FIRST_REPORT_IS_DISPLAY_BASELINE",
    "NO_WINNER_OR_RANKING",
)
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")


@dataclass(frozen=True)
class ComparisonSectionSource:
    report_id: str
    draft_mode: str
    availability: str
    confidence: str
    metrics: dict[str, Any]


@dataclass(frozen=True)
class ComparisonValue:
    report_id: str
    availability: str
    confidence: str
    metrics: dict[str, Any]
    delta_from_first: dict[str, Any]


@dataclass(frozen=True)
class ComparisonSectionResult:
    section_key: str
    title: str
    comparison_state: ComparisonState
    values: tuple[ComparisonValue, ...]
    reason_codes: tuple[str, ...]
    limitation_codes: tuple[str, ...]
    explanation_template_key: str
    explanation: str


def _safe_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        if _SAFE_LABEL.fullmatch(value) is None:
            raise ValueError("comparison text metrics must be generated labels")
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if value < 0:
            raise ValueError("comparison count metrics cannot be negative")
        return value
    if isinstance(value, list):
        if len(value) > 100 or any(
            not isinstance(item, str) or _SAFE_LABEL.fullmatch(item) is None
            for item in value
        ):
            raise ValueError("comparison list metrics must contain non-empty strings")
        return list(value)
    if isinstance(value, dict):
        if len(value) > 100:
            raise ValueError("comparison mapping metrics exceed the safe limit")
        result: dict[str, int] = {}
        for key, item in value.items():
            if (
                not isinstance(key, str)
                or _SAFE_LABEL.fullmatch(key) is None
                or not isinstance(item, int)
                or isinstance(item, bool)
                or item < 0
            ):
                raise ValueError("comparison mapping metrics must contain safe counts")
            result[key] = item
        return dict(sorted(result.items()))
    raise ValueError("comparison metric type is not allowlisted")


def _project(section_key: str, metrics: dict[str, Any]) -> dict[str, Any]:
    fields = _SAFE_FIELDS[section_key]
    return {
        field: _safe_value(metrics[field])
        for field in fields
        if field in metrics
    }


def _mapping_delta(current: dict[str, int], baseline: dict[str, int]) -> dict[str, int]:
    return {
        key: current.get(key, 0) - baseline.get(key, 0)
        for key in sorted(set(current) | set(baseline))
    }


def _deltas(
    section_key: str,
    projected: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...] | None:
    fields = _DELTA_FIELDS.get(section_key, ())
    if not fields:
        return tuple({} for _ in projected)
    if any(any(field not in value for field in fields) for value in projected):
        return None
    baseline = projected[0]
    result: list[dict[str, Any]] = []
    for value in projected:
        document: dict[str, Any] = {}
        for field in fields:
            current_value = value[field]
            baseline_value = baseline[field]
            if (
                isinstance(current_value, int)
                and not isinstance(current_value, bool)
                and isinstance(baseline_value, int)
                and not isinstance(baseline_value, bool)
            ):
                document[field] = current_value - baseline_value
            elif isinstance(current_value, dict) and isinstance(baseline_value, dict):
                document[field] = _mapping_delta(current_value, baseline_value)
            else:
                return None
        result.append(document)
    return tuple(result)


def build_comparison_sections(
    sections: dict[str, tuple[ComparisonSectionSource, ...]],
    *,
    report_count: int,
) -> tuple[ComparisonSectionResult, ...]:
    if set(sections) != set(SECTION_KEYS):
        raise ValueError("comparison section registry is incomplete")
    results: list[ComparisonSectionResult] = []
    compatible_explanation = render_explanation(
        template_key="comparison.compatible",
        values={"report_count": report_count},
    )
    unavailable_explanation = render_explanation(
        template_key="comparison.not_comparable",
        values={},
    )
    for section_key in SECTION_KEYS:
        sources = sections[section_key]
        if len(sources) != report_count:
            raise ValueError("comparison section report count is incomplete")
        projected = tuple(_project(section_key, source.metrics) for source in sources)
        comparable = section_key not in _ALWAYS_NOT_COMPARABLE and all(
            source.availability in {"supported", "limited"} for source in sources
        )
        limitations = set(_BASE_LIMITATIONS)
        if section_key == "strategy_story":
            versions = {
                value.get("strategy_definition_version") for value in projected
            }
            if (
                any(source.draft_mode != "mock" for source in sources)
                or None in versions
                or len(versions) != 1
            ):
                comparable = False
                limitations.add("STRATEGY_COMPARISON_REQUIRES_COMPATIBLE_MOCKS")
        deltas = _deltas(section_key, projected) if comparable else None
        if comparable and deltas is None:
            comparable = False
            limitations.add("COMPARISON_METRIC_INCOMPLETE")
        if comparable:
            state: ComparisonState = "comparable"
            reason_codes = ("REPORT_SECTION_COMPARABLE",)
            explanation_key = "comparison.compatible"
            explanation = compatible_explanation
            assert deltas is not None
            delta_values = deltas
        else:
            state = "not_comparable"
            reason_codes = ("REPORT_SECTION_NOT_COMPARABLE",)
            limitations.add("SECTION_UNSUPPORTED_IN_SELECTED_REPORT")
            explanation_key = "comparison.not_comparable"
            explanation = unavailable_explanation
            delta_values = tuple({} for _ in sources)
        results.append(
            ComparisonSectionResult(
                section_key=section_key,
                title=SECTION_TITLES[section_key],
                comparison_state=state,
                values=tuple(
                    ComparisonValue(
                        report_id=source.report_id,
                        availability=source.availability,
                        confidence=source.confidence,
                        metrics=metrics,
                        delta_from_first=delta,
                    )
                    for source, metrics, delta in zip(
                        sources, projected, delta_values, strict=True
                    )
                ),
                reason_codes=reason_codes,
                limitation_codes=tuple(sorted(limitations)),
                explanation_template_key=explanation_key,
                explanation=explanation,
            )
        )
    return tuple(results)


def comparison_limitations() -> tuple[str, ...]:
    return _BASE_LIMITATIONS
