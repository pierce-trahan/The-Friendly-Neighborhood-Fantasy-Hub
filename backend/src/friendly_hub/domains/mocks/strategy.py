from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import ceil
from typing import Literal

from friendly_hub.domains.mocks.definitions import SUPPORTED_STRATEGIES

GuidanceState = Literal[
    "on_plan",
    "watch",
    "off_plan_viable",
    "risk_checkpoint",
    "insufficient_evidence",
]
GuidanceConfidence = Literal["unavailable", "low", "medium", "high"]

EXPLANATION_TEMPLATES = {
    "strategy.on_plan": (
        "Your current position counts remain inside this strategy's guide range."
    ),
    "strategy.watch": (
        "The next checkpoint is approaching, so watch the listed position counts."
    ),
    "strategy.off_plan_viable": (
        "You moved outside the guide range, but the roster still has a coherent path."
    ),
    "strategy.risk_checkpoint": (
        "A documented roster target is now behind pace or overly concentrated."
    ),
    "strategy.insufficient_evidence": (
        "The available data cannot support a stronger strategy conclusion."
    ),
}
PIVOT_TEMPLATES = {
    "strategy.viable_pivot": (
        "You can keep the current roster or pivot the guide for later picks; "
        "earlier selections will not change."
    )
}


@dataclass(frozen=True)
class StrategyEvaluation:
    state: GuidanceState
    confidence: GuidanceConfidence
    observed_counts: dict[str, int]
    target_ranges: dict[str, object]
    reason_codes: tuple[str, ...]
    limitation_codes: tuple[str, ...]
    affected_positions: tuple[str, ...]
    explanation_template_key: str
    pivot_template_key: str | None


def explanation_text(template_key: str) -> str:
    try:
        return EXPLANATION_TEMPLATES[template_key]
    except KeyError as exc:
        raise ValueError("unknown explanation template") from exc


def pivot_text(template_key: str | None) -> str | None:
    if template_key is None:
        return None
    try:
        return PIVOT_TEMPLATES[template_key]
    except KeyError as exc:
        raise ValueError("unknown pivot template") from exc


def user_roster_counts(
    roster: Sequence[tuple[str, bool]],
) -> dict[str, int]:
    counts = {"QB": 0, "RB": 0, "WR": 0, "TE": 0, "TOTAL": 0, "ROOKIE": 0}
    for position, is_rookie in roster:
        normalized = position.strip().upper()
        if normalized:
            counts[normalized] = counts.get(normalized, 0) + 1
        counts["TOTAL"] += 1
        if is_rookie:
            counts["ROOKIE"] += 1
    return counts


def evaluate_strategy(
    *,
    strategy_key: str,
    round_count: int,
    team_count: int,
    effective_overall_pick: int,
    roster: Sequence[tuple[str, bool]],
    league_shape: Mapping[str, object],
) -> StrategyEvaluation:
    if strategy_key not in SUPPORTED_STRATEGIES:
        raise ValueError("strategy_key is not supported")
    if round_count < 1 or team_count < 2 or effective_overall_pick < 1:
        raise ValueError("draft coordinates must be positive")

    counts = user_roster_counts(roster)
    early_round = ceil(round_count * 0.25)
    middle_round = ceil(round_count * 0.60)
    first_ten_percent_round = ceil(round_count * 0.10)
    current_round = min(
        round_count,
        ceil(effective_overall_pick / team_count),
    )
    window = (
        "early"
        if current_round <= early_round
        else "middle"
        if current_round <= middle_round
        else "late"
    )
    starter_positions, starter_total, starter_covered = _starter_coverage(
        league_shape,
        counts,
    )
    counts["STARTER_COVERED"] = starter_covered
    counts["STARTER_TOTAL"] = starter_total
    league_limitations = {
        value
        for value in league_shape.get("limitations", [])
        if isinstance(value, str)
    }
    base_targets: dict[str, object] = {
        "window": window,
        "current_round": current_round,
        "early_round": early_round,
        "middle_round": middle_round,
        "affected_positions": [],
    }

    state: GuidanceState
    reasons: list[str]
    affected: tuple[str, ...]
    pivot = False

    if strategy_key == "balanced":
        affected = tuple(position for position in ("RB", "WR", "TE") if position)
        required_coverage = ceil(starter_total * 0.75) if starter_total else 0
        non_qb_max = max((counts[position] for position in affected), default=0)
        concentration = (
            non_qb_max / counts["TOTAL"] if counts["TOTAL"] else 0.0
        )
        base_targets.update(
            {
                "starter_coverage_minimum": required_coverage,
                "non_qb_concentration_maximum_percent": 40,
            }
        )
        if (
            current_round > middle_round
            and starter_total
            and starter_covered < required_coverage
        ):
            state, reasons = "risk_checkpoint", ["STARTER_COVERAGE_BEHIND"]
        elif counts["TOTAL"] and concentration > 0.40:
            state, reasons = "watch", ["NON_QB_CONCENTRATION_WATCH"]
        else:
            state, reasons = "on_plan", ["BALANCED_RANGE_MET"]
    elif strategy_key == "win_now":
        affected = starter_positions
        league_limitations.add("TIMELINE_EVIDENCE_UNAVAILABLE")
        distinct_filled = sum(1 for position in starter_positions if counts.get(position))
        base_targets["distinct_starter_positions_required"] = len(starter_positions)
        if (
            current_round > middle_round
            and starter_positions
            and distinct_filled < len(starter_positions)
        ):
            state, reasons = "risk_checkpoint", ["DISTINCT_STARTER_POSITION_MISSING"]
        else:
            state, reasons = "insufficient_evidence", ["TIMELINE_EVIDENCE_MISSING"]
    elif strategy_key == "productive_struggle":
        affected = ("QB", "RB", "WR", "TE")
        league_limitations.add("TIMELINE_EVIDENCE_UNAVAILABLE")
        base_targets.update(
            {
                "early_rb_maximum": 1,
                "optionality_positions": ["QB", "WR", "TE"],
            }
        )
        if current_round <= early_round and counts["RB"] > 1:
            state, reasons, pivot = (
                "off_plan_viable",
                ["EARLY_RB_MAXIMUM_EXCEEDED"],
                True,
            )
        elif counts["TOTAL"] == 0:
            state, reasons = "insufficient_evidence", ["TIMELINE_EVIDENCE_MISSING"]
        elif not any(counts[position] for position in ("QB", "WR", "TE")):
            state, reasons = "watch", ["OPTIONALITY_POSITION_WATCH"]
        else:
            state, reasons = "on_plan", ["POSITIONAL_OPTIONALITY_PRESENT"]
    elif strategy_key == "hero_rb":
        affected = ("RB",)
        base_targets.update({"early_rb_target": 1, "middle_rb_maximum": 2})
        if current_round <= early_round and counts["RB"] == 0:
            state, reasons = "watch", ["HERO_RB_TARGET_OPEN"]
        elif counts["RB"] > 2 and current_round <= middle_round:
            state, reasons, pivot = (
                "off_plan_viable",
                ["MIDDLE_RB_MAXIMUM_EXCEEDED"],
                True,
            )
        elif current_round > early_round and counts["RB"] == 0:
            state, reasons = "risk_checkpoint", ["EARLY_RB_TARGET_MISSED"]
        else:
            state, reasons = "on_plan", ["HERO_RB_RANGE_MET"]
    elif strategy_key == "robust_rb":
        affected = ("QB", "RB", "TE")
        base_targets.update({"early_rb_minimum": 2, "middle_rb_target": 3})
        if current_round > early_round and counts["RB"] < 2:
            state, reasons = "risk_checkpoint", ["EARLY_RB_MINIMUM_MISSED"]
        elif current_round > middle_round and counts["RB"] < 3:
            state, reasons = "risk_checkpoint", ["MIDDLE_RB_TARGET_BEHIND"]
        elif counts["RB"] >= 3 and (
            counts["QB"] == 0 or counts["TE"] == 0
        ):
            state, reasons, pivot = (
                "off_plan_viable",
                ["STARTER_COVERAGE_PIVOT_AVAILABLE"],
                True,
            )
        elif counts["RB"] < 2:
            state, reasons = "watch", ["ROBUST_RB_TARGET_OPEN"]
        else:
            state, reasons = "on_plan", ["ROBUST_RB_RANGE_MET"]
    elif strategy_key == "wr_heavy":
        affected = ("WR",)
        base_targets.update(
            {
                "middle_wr_minimum": 3,
                "middle_wr_share_minimum_percent": 35,
                "minimum_supported_rounds": 6,
            }
        )
        if round_count < 6:
            league_limitations.add("DRAFT_TOO_SHORT_FOR_WR_HEAVY_TARGET")
            state, reasons = "insufficient_evidence", ["DRAFT_WINDOW_TOO_SHORT"]
        else:
            wr_share = counts["WR"] / counts["TOTAL"] if counts["TOTAL"] else 0.0
            if current_round > middle_round and (
                counts["WR"] < 3 or wr_share < 0.35
            ):
                state, reasons = "risk_checkpoint", ["MIDDLE_WR_TARGET_BEHIND"]
            elif counts["WR"] < 3 or (counts["TOTAL"] and wr_share < 0.35):
                state, reasons = "watch", ["WR_SHARE_WATCH"]
            else:
                state, reasons = "on_plan", ["WR_HEAVY_RANGE_MET"]
    else:
        affected = ("QB",)
        base_targets.update(
            {
                "first_ten_percent_qb_minimum": 1,
                "early_qb_minimum": 2,
                "first_ten_percent_round": first_ten_percent_round,
            }
        )
        if (
            league_shape.get("superflex") is not True
            and int(league_shape.get("qb_eligible_starter_slots", 0) or 0) < 2
        ):
            league_limitations.add("SUPERFLEX_SHAPE_REQUIRED")
            state, reasons = "insufficient_evidence", ["LEAGUE_SHAPE_INCOMPATIBLE"]
        elif current_round > early_round and counts["QB"] < 2:
            state, reasons = "risk_checkpoint", ["EARLY_QB_TARGET_BEHIND"]
        elif current_round > first_ten_percent_round and counts["QB"] < 1:
            state, reasons = "risk_checkpoint", ["FIRST_QB_TARGET_MISSED"]
        elif counts["QB"] < 2:
            state, reasons = "watch", ["EARLY_QB_TARGET_OPEN"]
        else:
            state, reasons = "on_plan", ["EARLY_QB_RANGE_MET"]

    base_targets["affected_positions"] = list(affected)
    limitations = tuple(sorted(league_limitations))
    confidence: GuidanceConfidence = (
        "low"
        if limitations
        or strategy_key in {"win_now", "productive_struggle"}
        else "medium"
    )
    return StrategyEvaluation(
        state=state,
        confidence=confidence,
        observed_counts=counts,
        target_ranges=base_targets,
        reason_codes=tuple(reasons),
        limitation_codes=limitations,
        affected_positions=affected,
        explanation_template_key=f"strategy.{state}",
        pivot_template_key="strategy.viable_pivot" if pivot else None,
    )


def _starter_coverage(
    league_shape: Mapping[str, object],
    counts: Mapping[str, int],
) -> tuple[tuple[str, ...], int, int]:
    raw_slots = league_shape.get("starter_slots", [])
    if not isinstance(raw_slots, list):
        return (), 0, 0
    slots: list[tuple[str, ...]] = []
    distinct_positions: set[str] = set()
    for raw_slot in raw_slots:
        if not isinstance(raw_slot, dict):
            continue
        raw_positions = raw_slot.get("eligible_positions", [])
        if not isinstance(raw_positions, list):
            continue
        positions = tuple(
            sorted(
                {
                    position.strip().upper()
                    for position in raw_positions
                    if isinstance(position, str) and position.strip()
                }
            )
        )
        if positions:
            slots.append(positions)
            distinct_positions.update(positions)
    remaining = dict(counts)
    covered = 0
    for positions in sorted(slots, key=lambda value: (len(value), value)):
        available = sorted(
            (remaining.get(position, 0), position)
            for position in positions
            if remaining.get(position, 0) > 0
        )
        if available:
            _, selected = available[-1]
            remaining[selected] -= 1
            covered += 1
    return tuple(sorted(distinct_positions)), len(slots), covered
