from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from friendly_hub.domains.alerts.models import (
    DraftAlertConfigurationRow,
    DraftAlertEventRow,
    DraftAlertTradeReferenceRow,
)
from friendly_hub.domains.drafts.models import DraftSessionRow
from friendly_hub.domains.mocks.definitions import SUPPORTED_STRATEGIES
from friendly_hub.domains.mocks.models import (
    MockConfigurationRow,
    MockGuidanceEventRow,
    MockStrategyRevisionRow,
)
from friendly_hub.domains.reports.engine import render_explanation, strategy_section_state

HistoryState = Literal["valid", "incomplete", "corrupt"]
AlertHistoryState = Literal[
    "not_configured",
    "disabled_at_completion",
    "configured_no_events",
    "available",
    "unavailable_due_to_corruption",
]

MAXIMUM_STRATEGY_REVISIONS = 60
MAXIMUM_GUIDANCE_EVENTS = 60
MAXIMUM_PERSONAL_BOARD_MOMENTS = 10
MAXIMUM_ALERT_SOURCE_EVENTS = 2_000
MAXIMUM_ALERT_MOMENTS = 20

_GUIDANCE_STATES = (
    "on_plan",
    "watch",
    "off_plan_viable",
    "risk_checkpoint",
    "insufficient_evidence",
)
_GUIDANCE_CONFIDENCE = {"unavailable", "low", "medium", "high"}
_GUIDANCE_STATUS = {"open", "acknowledged", "dismissed"}
_ALERT_KINDS = {
    "value_watch",
    "return_risk",
    "trade_up_window",
    "evidence_warning",
}
_ALERT_STATUS = {"open", "snoozed", "dismissed", "superseded"}
_ALERT_CONFIDENCE = {"high", "medium", "low", "unavailable"}
_ALERT_FRESHNESS = {"fresh", "aging", "stale", "expired", "invalid"}
_TARGET_TEXT_FIELDS = {"window"}
_TARGET_LIST_FIELDS = {"affected_positions", "optionality_positions"}
_TARGET_INTEGER_FIELDS = {
    "current_round",
    "early_round",
    "middle_round",
    "starter_coverage_minimum",
    "non_qb_concentration_maximum_percent",
    "distinct_starter_positions_required",
    "early_rb_maximum",
    "early_rb_target",
    "middle_rb_maximum",
    "early_rb_minimum",
    "middle_rb_target",
    "middle_wr_minimum",
    "middle_wr_share_minimum_percent",
    "minimum_supported_rounds",
    "first_ten_percent_qb_minimum",
    "early_qb_minimum",
    "first_ten_percent_round",
}
_COUNT_KEY = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")
_CODE = re.compile(r"^[A-Z][A-Z0-9_.-]{0,99}$")
_VERSION = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_ROUND_PICK_LABEL = re.compile(r"^Round [1-9][0-9]*, pick [1-9][0-9]*$")
_FUTURE_PICK_LABEL = re.compile(r"^Year [1-9][0-9]*, round [1-9][0-9]*$")


@dataclass(frozen=True)
class MomentCandidate:
    player_id: str
    display_name: str
    primary_position: str
    manual_rank: int | None
    tier_order: int | None
    favorite: bool


@dataclass(frozen=True)
class MomentPick:
    overall_pick: int
    selecting_slot: int
    player_id: str


@dataclass(frozen=True)
class HistoryMoment:
    moment_key: str
    moment_kind: str
    overall_pick: int | None
    primary_player_id: str | None
    secondary_player_id: str | None
    safe_summary: dict[str, Any]
    reason_codes: tuple[str, ...]
    limitation_codes: tuple[str, ...]

    def fingerprint_document(self) -> dict[str, Any]:
        return {
            "moment_key": self.moment_key,
            "moment_kind": self.moment_kind,
            "overall_pick": self.overall_pick,
            "primary_player_id": self.primary_player_id,
            "secondary_player_id": self.secondary_player_id,
            "safe_summary": self.safe_summary,
            "reason_codes": list(self.reason_codes),
            "limitation_codes": list(self.limitation_codes),
        }


@dataclass(frozen=True)
class HistoryPart:
    state: str
    metrics: dict[str, Any]
    moments: tuple[HistoryMoment, ...]
    reason_codes: tuple[str, ...]
    limitation_codes: tuple[str, ...]
    source_fingerprint: str

    def fingerprint_document(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "metrics": self.metrics,
            "moments": [moment.fingerprint_document() for moment in self.moments],
            "reason_codes": list(self.reason_codes),
            "limitation_codes": list(self.limitation_codes),
            "source_fingerprint": self.source_fingerprint,
        }


@dataclass(frozen=True)
class HistorySectionResult:
    section_key: str
    availability: str
    confidence: str
    metrics: dict[str, Any]
    reason_codes: tuple[str, ...]
    limitation_codes: tuple[str, ...]
    explanation_template_key: str
    explanation: str


@dataclass(frozen=True)
class DecisionHistoryContext:
    strategy: HistoryPart | None
    personal_board: HistoryPart
    alerts: HistoryPart

    def fingerprint_document(self) -> dict[str, Any]:
        return {
            "decision_history_version": "phase6-saved-decision-history-v1",
            "strategy": (
                self.strategy.fingerprint_document()
                if self.strategy is not None
                else {"state": "not_applicable"}
            ),
            "personal_board": self.personal_board.fingerprint_document(),
            "alerts": self.alerts.fingerprint_document(),
        }

    def moments(self) -> tuple[HistoryMoment, ...]:
        strategy_moments = self.strategy.moments if self.strategy is not None else ()
        return strategy_moments + self.personal_board.moments + self.alerts.moments


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _parse_json(value: str) -> object | None:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def _string_list(value: str) -> tuple[str, ...] | None:
    parsed = _parse_json(value)
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        return None
    return tuple(sorted(set(parsed)))


def _code_list(value: str) -> tuple[str, ...] | None:
    parsed = _string_list(value)
    if parsed is None or any(_CODE.fullmatch(item) is None for item in parsed):
        return None
    return parsed


def _ordered_string_list(value: str) -> tuple[str, ...] | None:
    parsed = _parse_json(value)
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        return None
    return tuple(parsed)


def _safe_counts(value: str) -> dict[str, int] | None:
    parsed = _parse_json(value)
    if not isinstance(parsed, dict):
        return None
    result: dict[str, int] = {}
    for key, count in parsed.items():
        if (
            not isinstance(key, str)
            or _COUNT_KEY.fullmatch(key) is None
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
        ):
            return None
        result[key] = count
    return dict(sorted(result.items()))


def _safe_targets(value: str) -> dict[str, Any] | None:
    parsed = _parse_json(value)
    if not isinstance(parsed, dict) or set(parsed) - (
        _TARGET_TEXT_FIELDS | _TARGET_LIST_FIELDS | _TARGET_INTEGER_FIELDS
    ):
        return None
    result: dict[str, Any] = {}
    for key, item in parsed.items():
        if key in _TARGET_TEXT_FIELDS:
            if item not in {"early", "middle", "late"}:
                return None
            result[key] = item
        elif key in _TARGET_LIST_FIELDS:
            if (
                not isinstance(item, list)
                or any(
                    not isinstance(entry, str) or _COUNT_KEY.fullmatch(entry) is None
                    for entry in item
                )
                or len(item) != len(set(item))
            ):
                return None
            result[key] = list(item)
        else:
            if not isinstance(item, int) or isinstance(item, bool) or item < 0:
                return None
            result[key] = item
    return dict(sorted(result.items()))


def _parse_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _strategy_history(
    session: Session,
    *,
    configuration: MockConfigurationRow,
    draft_total_picks: int,
    completed_at: datetime,
) -> HistoryPart:
    revisions = tuple(
        session.scalars(
            select(MockStrategyRevisionRow)
            .where(MockStrategyRevisionRow.mock_configuration_id == configuration.id)
            .order_by(MockStrategyRevisionRow.sequence_number, MockStrategyRevisionRow.id)
        )
    )
    guidance = tuple(
        session.scalars(
            select(MockGuidanceEventRow)
            .where(MockGuidanceEventRow.mock_configuration_id == configuration.id)
            .order_by(
                MockGuidanceEventRow.effective_overall_pick,
                MockGuidanceEventRow.created_at,
                MockGuidanceEventRow.id,
            )
        )
    )
    if len(revisions) > MAXIMUM_STRATEGY_REVISIONS or len(guidance) > MAXIMUM_GUIDANCE_EVENTS:
        return _corrupt_strategy("STRATEGY_HISTORY_LIMIT_EXCEEDED")
    if not revisions:
        return HistoryPart(
            state="incomplete",
            metrics={
                "saved_history_loaded": False,
                "initial_strategy": None,
                "pivot_count": 0,
                "guidance_event_count": len(guidance),
            },
            moments=(),
            reason_codes=("MOCK_STRATEGY_HISTORY_LIMITED",),
            limitation_codes=("SAVED_EVENTS_ONLY", "STRATEGY_REVISION_MISSING"),
            source_fingerprint=_fingerprint({"revisions": [], "guidance_count": len(guidance)}),
        )

    revision_by_id = {row.id: row for row in revisions}
    revision_documents: list[dict[str, Any]] = []
    previous_strategy: str | None = None
    previous_effective_pick = 0
    for index, row in enumerate(revisions, start=1):
        counts = _safe_counts(row.user_roster_counts_json)
        created_at = _parse_utc(row.created_at)
        if (
            row.sequence_number != index
            or row.effective_overall_pick < 1
            or row.effective_overall_pick > draft_total_picks
            or row.effective_overall_pick < previous_effective_pick
            or counts is None
            or row.next_strategy_key not in SUPPORTED_STRATEGIES
            or (
                row.previous_strategy_key is not None
                and row.previous_strategy_key not in SUPPORTED_STRATEGIES
            )
            or (index == 1 and row.previous_strategy_key is not None)
            or (index > 1 and row.previous_strategy_key != previous_strategy)
            or created_at is None
            or created_at > completed_at
        ):
            return _corrupt_strategy("STRATEGY_REVISION_CORRUPT")
        revision_documents.append(
            {
                "sequence_number": row.sequence_number,
                "previous_strategy": row.previous_strategy_key,
                "next_strategy": row.next_strategy_key,
                "effective_overall_pick": row.effective_overall_pick,
                "roster_counts": counts,
            }
        )
        previous_strategy = row.next_strategy_key
        previous_effective_pick = row.effective_overall_pick

    guidance_documents: list[dict[str, Any]] = []
    inherited_limitations: set[str] = {"SAVED_EVENTS_ONLY", "PIVOT_IS_NOT_FAILURE"}
    state_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    for row in guidance:
        revision = revision_by_id.get(row.strategy_revision_id)
        observed = _safe_counts(row.observed_counts_json)
        targets = _safe_targets(row.target_ranges_json)
        reasons = _code_list(row.reason_codes_json)
        limitations = _code_list(row.limitation_codes_json)
        created_at = _parse_utc(row.created_at)
        resolved_at = _parse_utc(row.resolved_at) if row.resolved_at is not None else None
        if (
            revision is None
            or observed is None
            or targets is None
            or reasons is None
            or limitations is None
            or row.state not in _GUIDANCE_STATES
            or row.confidence not in _GUIDANCE_CONFIDENCE
            or row.status not in _GUIDANCE_STATUS
            or row.effective_overall_pick < 1
            or row.effective_overall_pick > draft_total_picks
            or row.effective_overall_pick < revision.effective_overall_pick
            or created_at is None
            or (row.resolved_at is not None and resolved_at is None)
            or (row.status == "open" and row.resolved_at is not None)
            or (row.status != "open" and row.resolved_at is None)
            or row.explanation_template_key != f"strategy.{row.state}"
            or (
                row.pivot_template_key is not None
                and row.pivot_template_key != "strategy.viable_pivot"
            )
        ):
            return _corrupt_strategy("STRATEGY_GUIDANCE_CORRUPT")
        document = {
            "source_id": row.id,
            "strategy": revision.next_strategy_key,
            "effective_overall_pick": row.effective_overall_pick,
            "state": row.state,
            "confidence": row.confidence,
            "observed_counts": observed,
            "target_ranges": targets,
            "status": row.status,
            "explanation_template_key": row.explanation_template_key,
            "pivot_template_key": row.pivot_template_key,
            "reason_codes": list(reasons),
            "limitation_codes": list(limitations),
        }
        guidance_documents.append(document)
        state_counts[row.state] += 1
        status_counts[row.status] += 1
        inherited_limitations.update(limitations)

    state: HistoryState = "valid" if guidance else "incomplete"
    limitation_codes = set(inherited_limitations)
    if not guidance:
        limitation_codes.add("STRATEGY_GUIDANCE_MISSING")
    moments: list[HistoryMoment] = []
    display_order = 0
    for revision in revision_documents[1:]:
        display_order += 1
        moments.append(
            HistoryMoment(
                moment_key=f"strategy-pivot:{revision['sequence_number']}",
                moment_kind="strategy_pivot",
                overall_pick=revision["effective_overall_pick"],
                primary_player_id=None,
                secondary_player_id=None,
                safe_summary={
                    "display_order": display_order,
                    "previous_strategy": revision["previous_strategy"],
                    "next_strategy": revision["next_strategy"],
                    "effective_overall_pick": revision["effective_overall_pick"],
                    "roster_counts_at_pivot": revision["roster_counts"],
                },
                reason_codes=("SAVED_STRATEGY_PIVOT",),
                limitation_codes=("PIVOT_IS_NOT_FAILURE", "SAVED_EVENTS_ONLY"),
            )
        )
    for document in guidance_documents:
        display_order += 1
        moments.append(
            HistoryMoment(
                moment_key=f"strategy-guidance:{document['source_id']}",
                moment_kind="strategy_guidance",
                overall_pick=document["effective_overall_pick"],
                primary_player_id=None,
                secondary_player_id=None,
                safe_summary={
                    "display_order": display_order,
                    **{key: value for key, value in document.items() if key != "source_id"},
                },
                reason_codes=tuple(document["reason_codes"]),
                limitation_codes=tuple(
                    sorted(set(document["limitation_codes"]) | {"SAVED_EVENTS_ONLY"})
                ),
            )
        )
    metrics = {
        "saved_history_loaded": state == "valid",
        "initial_strategy": revision_documents[0]["next_strategy"],
        "final_strategy": revision_documents[-1]["next_strategy"],
        "pivot_count": len(revision_documents) - 1,
        "pivots": revision_documents[1:],
        "guidance_event_count": len(guidance_documents),
        "guidance_state_counts": {
            state_key: state_counts[state_key] for state_key in _GUIDANCE_STATES
        },
        "guidance_status_counts": {
            status: status_counts[status] for status in sorted(_GUIDANCE_STATUS)
        },
    }
    source = {"revisions": revision_documents, "guidance": guidance_documents}
    return HistoryPart(
        state=state,
        metrics=metrics,
        moments=tuple(moments),
        reason_codes=(
            ("MOCK_STRATEGY_HISTORY_AVAILABLE",)
            if state == "valid"
            else ("MOCK_STRATEGY_HISTORY_LIMITED",)
        ),
        limitation_codes=tuple(sorted(limitation_codes)),
        source_fingerprint=_fingerprint(source),
    )


def _corrupt_strategy(code: str) -> HistoryPart:
    return HistoryPart(
        state="corrupt",
        metrics={"saved_history_loaded": False, "pivot_count": 0, "guidance_event_count": 0},
        moments=(),
        reason_codes=("MOCK_STRATEGY_HISTORY_CORRUPT",),
        limitation_codes=("SAVED_EVENTS_ONLY", code),
        source_fingerprint=_fingerprint({"state": "corrupt", "code": code}),
    )


def reconstruct_personal_board_history(
    *,
    candidates: tuple[MomentCandidate, ...],
    picks: tuple[MomentPick, ...],
    user_slot: int,
) -> HistoryPart:
    ranks = [candidate.manual_rank for candidate in candidates if candidate.manual_rank is not None]
    tiers = [candidate.tier_order for candidate in candidates if candidate.tier_order is not None]
    if (
        any(rank < 1 for rank in ranks)
        or any(tier < 1 for tier in tiers)
        or len(ranks) != len(set(ranks))
    ):
        return HistoryPart(
            state="corrupt",
            metrics={"moment_count": 0, "qualifying_moment_count": 0},
            moments=(),
            reason_codes=("PERSONAL_BOARD_HISTORY_CORRUPT",),
            limitation_codes=(
                "PERSONAL_BOARD_OBSERVATION_ONLY",
                "PERSONAL_BOARD_RANKS_CORRUPT",
            ),
            source_fingerprint=_fingerprint({"state": "corrupt"}),
        )
    candidate_by_id = {candidate.player_id: candidate for candidate in candidates}
    pick_by_player = {pick.player_id: pick for pick in picks}
    selected_before: set[str] = set()
    observations: dict[str, dict[str, Any]] = {}
    user_pick_count = 0
    for pick in picks:
        if pick.selecting_slot == user_slot:
            user_pick_count += 1
            for passed_id, observation in observations.items():
                if passed_id not in selected_before:
                    observation["last_available_user_pick"] = pick.overall_pick
            selected = candidate_by_id[pick.player_id]
            available_ranked = [
                candidate
                for candidate in candidates
                if candidate.player_id not in selected_before
                and candidate.manual_rank is not None
            ]
            if selected.manual_rank is not None and available_ranked:
                passed = min(
                    available_ranked,
                    key=lambda candidate: (candidate.manual_rank or 1_000_000, candidate.player_id),
                )
                rank_delta = selected.manual_rank - (passed.manual_rank or selected.manual_rank)
                tier_difference = (
                    selected.tier_order - passed.tier_order
                    if selected.tier_order is not None
                    and passed.tier_order is not None
                    and selected.tier_order > passed.tier_order
                    else 0
                )
                qualifies = (
                    passed.player_id != selected.player_id
                    and rank_delta > 0
                    and (rank_delta >= 5 or passed.favorite or tier_difference > 0)
                )
                if qualifies and passed.player_id not in observations:
                    observations[passed.player_id] = {
                        "selected": selected,
                        "passed": passed,
                        "rank_delta": rank_delta,
                        "tier_difference": tier_difference,
                        "first_user_pick": pick.overall_pick,
                        "last_available_user_pick": pick.overall_pick,
                    }
        selected_before.add(pick.player_id)

    ordered = sorted(
        observations.values(),
        key=lambda item: (
            -int(item["passed"].favorite),
            -item["tier_difference"],
            -item["rank_delta"],
            item["first_user_pick"],
            item["passed"].player_id,
        ),
    )
    retained = ordered[:MAXIMUM_PERSONAL_BOARD_MOMENTS]
    moments: list[HistoryMoment] = []
    for display_order, item in enumerate(retained, start=1):
        selected: MomentCandidate = item["selected"]
        passed: MomentCandidate = item["passed"]
        later_pick = pick_by_player.get(passed.player_id)
        if later_pick is None:
            drafted_outcome = {"state": "not_drafted", "overall_pick": None}
        else:
            drafted_outcome = {
                "state": (
                    "drafted_by_user"
                    if later_pick.selecting_slot == user_slot
                    else "drafted_by_other_slot"
                ),
                "overall_pick": later_pick.overall_pick,
            }
        first_pick = item["first_user_pick"]
        moments.append(
            HistoryMoment(
                moment_key=f"personal-board:{first_pick}:{passed.player_id}",
                moment_kind="personal_board_choice",
                overall_pick=first_pick,
                primary_player_id=selected.player_id,
                secondary_player_id=passed.player_id,
                safe_summary={
                    "display_order": display_order,
                    "first_user_pick": first_pick,
                    "last_available_user_pick": item["last_available_user_pick"],
                    "selected_player": {
                        "display_name": selected.display_name,
                        "primary_position": selected.primary_position,
                        "saved_rank": selected.manual_rank,
                        "saved_tier_order": selected.tier_order,
                    },
                    "passed_player": {
                        "display_name": passed.display_name,
                        "primary_position": passed.primary_position,
                        "saved_rank": passed.manual_rank,
                        "saved_tier_order": passed.tier_order,
                        "saved_favorite": passed.favorite,
                    },
                    "rank_delta": item["rank_delta"],
                    "tier_difference": item["tier_difference"],
                    "passed_player_draft_outcome": drafted_outcome,
                },
                reason_codes=("PERSONAL_BOARD_CHOICE_OBSERVED",),
                limitation_codes=("PERSONAL_BOARD_OBSERVATION_ONLY",),
            )
        )
    metrics = {
        "moment_count": len(moments),
        "qualifying_moment_count": len(ordered),
        "truncated": len(ordered) > len(moments),
        "ranked_candidate_count": len(ranks),
        "user_pick_count": user_pick_count,
    }
    limitations = {"PERSONAL_BOARD_OBSERVATION_ONLY"}
    if len(ranks) < len(candidates):
        limitations.add("PERSONAL_BOARD_RANKS_INCOMPLETE")
    return HistoryPart(
        state="valid",
        metrics=metrics,
        moments=tuple(moments),
        reason_codes=(
            "PERSONAL_BOARD_MOMENTS_AVAILABLE"
            if moments
            else "PERSONAL_BOARD_NO_QUALIFYING_MOMENTS",
        ),
        limitation_codes=tuple(sorted(limitations)),
        source_fingerprint=_fingerprint(
            {"metrics": metrics, "moments": [moment.fingerprint_document() for moment in moments]}
        ),
    )


def _safe_range(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    low = value.get("low")
    high = value.get("high")
    if (
        not isinstance(low, int)
        or isinstance(low, bool)
        or not isinstance(high, int)
        or isinstance(high, bool)
        or low < 0
        or high < low
    ):
        return None
    return {"low": low, "high": high}


def _safe_alert_evidence(value: str) -> dict[str, Any] | None:
    parsed = _parse_json(value)
    if not isinstance(parsed, dict):
        return None
    components = parsed.get("components")
    personal = parsed.get("personal_reason")
    if not isinstance(components, dict) or not isinstance(personal, dict):
        return None
    safe_components: dict[str, Any] = {}
    for key in (
        "personal_conviction",
        "dynasty_market",
        "win_now_production",
        "age_risk",
        "strategy_fit",
    ):
        component = components.get(key)
        if not isinstance(component, dict):
            return None
        reasons = component.get("reasons")
        if (
            not isinstance(reasons, list)
            or any(
                not isinstance(code, str) or _CODE.fullmatch(code) is None
                for code in reasons
            )
        ):
            return None
        state = component.get("state")
        band = component.get("band")
        allowed_bands: dict[str, set[str]] = {
            "personal_conviction": {"favorite", "qualified"},
            "dynasty_market": {
                "premium",
                "strong",
                "standard",
                "depth",
                "fringe",
                "expected_selection",
            },
            "win_now_production": {"high", "medium", "low"},
            "age_risk": {"lower", "middle", "higher"},
            "strategy_fit": set(SUPPORTED_STRATEGIES),
        }
        band_valid = (
            band is None
            or band in allowed_bands[key]
            or (
                key == "personal_conviction"
                and isinstance(band, str)
                and re.fullmatch(r"tier_[1-9][0-9]*", band) is not None
            )
        )
        if state not in {"available", "unavailable"} or not band_valid:
            return None
        safe_components[key] = {
            "state": state,
            "band": band,
            "reasons": sorted(set(reasons)),
        }
    confidence_reasons = parsed.get("confidence_reasons")
    limitation_codes = parsed.get("limitation_codes")
    if (
        not isinstance(confidence_reasons, list)
        or any(
            not isinstance(code, str) or _CODE.fullmatch(code) is None
            for code in confidence_reasons
        )
        or not isinstance(limitation_codes, list)
        or any(
            not isinstance(code, str) or _CODE.fullmatch(code) is None
            for code in limitation_codes
        )
    ):
        return None
    personal_values = {
        "manual_rank": personal.get("manual_rank"),
        "tier_order": personal.get("tier_order"),
        "favorite": personal.get("favorite"),
        "qualifier_mode": personal.get("qualifier_mode"),
        "qualified": personal.get("qualified"),
    }
    if (
        (
            personal_values["manual_rank"] is not None
            and (
                not isinstance(personal_values["manual_rank"], int)
                or isinstance(personal_values["manual_rank"], bool)
                or personal_values["manual_rank"] < 1
            )
        )
        or (
            personal_values["tier_order"] is not None
            and (
                not isinstance(personal_values["tier_order"], int)
                or isinstance(personal_values["tier_order"], bool)
                or personal_values["tier_order"] < 1
            )
        )
        or not isinstance(personal_values["favorite"], bool)
        or not isinstance(personal_values["qualifier_mode"], str)
        or not isinstance(personal_values["qualified"], bool)
        or personal_values["qualifier_mode"]
        not in {"tier_or_favorite", "tier_only", "favorite_only"}
    ):
        return None
    range_fields = {
        key: (_safe_range(parsed.get(key)) if parsed.get(key) is not None else None)
        for key in ("expected_selection", "market_gap", "target_pick_window")
    }
    if any(
        parsed.get(key) is not None and range_fields[key] is None for key in range_fields
    ):
        return None
    integer_fields = (
        "current_overall_pick",
        "next_user_pick",
        "configuration_revision",
        "draft_revision",
    )
    for key in integer_fields:
        item = parsed.get(key)
        if item is not None and (not isinstance(item, int) or isinstance(item, bool) or item < 0):
            return None
    for key in ("current_overall_pick", "next_user_pick"):
        if parsed.get(key) is not None and parsed[key] < 1:
            return None
    if parsed.get("configuration_revision") is None or parsed.get("draft_revision") is None:
        return None
    source_label = parsed.get("source_label")
    source_as_of = parsed.get("source_as_of")
    if (
        not isinstance(source_label, str)
        or not source_label
        or len(source_label) > 120
        or not isinstance(source_as_of, str)
        or _parse_utc(source_as_of) is None
        or parsed.get("format_compatibility")
        not in {"exact", "family", "partial", "incompatible", "unknown"}
        or parsed.get("return_risk")
        not in {"likely_to_return", "uncertain", "unlikely_to_return", "unavailable"}
        or parsed.get("cost_availability")
        not in {"available", "unavailable", "not_applicable"}
        or any(
            not isinstance(parsed.get(key), str)
            or _VERSION.fullmatch(parsed[key]) is None
            for key in ("engine_version", "rule_version", "freshness_policy_version")
        )
    ):
        return None
    return {
        "source_label": source_label,
        "source_as_of": source_as_of,
        "format_compatibility": parsed["format_compatibility"],
        "return_risk": parsed["return_risk"],
        "cost_availability": parsed["cost_availability"],
        "engine_version": parsed["engine_version"],
        "rule_version": parsed["rule_version"],
        "freshness_policy_version": parsed["freshness_policy_version"],
        **range_fields,
        **{key: parsed.get(key) for key in integer_fields},
        "personal_reason": personal_values,
        "components": safe_components,
        "confidence_reasons": sorted(set(confidence_reasons)),
        "limitation_codes": sorted(set(limitation_codes)),
    }


def _safe_trade_reference(row: DraftAlertTradeReferenceRow) -> dict[str, Any] | None:
    labels = _ordered_string_list(row.target_round_pick_labels_json)
    limitations = _code_list(row.limitation_codes_json)
    cost = _parse_json(row.cost_range_json)
    if (
        labels is None
        or len(labels) > MAXIMUM_STRATEGY_REVISIONS
        or any(_ROUND_PICK_LABEL.fullmatch(label) is None for label in labels)
        or limitations is None
        or not isinstance(cost, dict)
        or not isinstance(row.target_overall_pick_low, int)
        or isinstance(row.target_overall_pick_low, bool)
        or not isinstance(row.target_overall_pick_high, int)
        or isinstance(row.target_overall_pick_high, bool)
        or row.target_overall_pick_low < 1
        or row.target_overall_pick_high < row.target_overall_pick_low
        or _parse_utc(row.created_at) is None
    ):
        return None
    incremental = cost.get("incremental_cost")
    safe_incremental = _safe_range(incremental) if incremental is not None else None
    if incremental is not None and safe_incremental is None:
        return None
    references = cost.get("pick_only_references")
    if not isinstance(references, list) or len(references) > 40:
        return None
    safe_references: list[dict[str, Any]] = []
    for reference in references:
        if not isinstance(reference, dict):
            return None
        label = reference.get("label")
        season_offset = reference.get("season_offset")
        round_number = reference.get("round")
        value = _safe_range(reference.get("value"))
        if (
            not isinstance(label, str)
            or _FUTURE_PICK_LABEL.fullmatch(label) is None
            or not isinstance(season_offset, int)
            or isinstance(season_offset, bool)
            or not isinstance(round_number, int)
            or isinstance(round_number, bool)
            or value is None
            or season_offset < 1
            or round_number < 1
        ):
            return None
        safe_references.append(
            {
                "label": label,
                "season_offset": season_offset,
                "round": round_number,
                "value": value,
            }
        )
    availability = cost.get("cost_availability")
    if availability not in {"available", "unavailable"}:
        return None
    if _CODE.fullmatch(row.explanation_template_key) is None:
        return None
    return {
        "target_pick_window": {
            "low": row.target_overall_pick_low,
            "high": row.target_overall_pick_high,
        },
        "target_round_pick_labels": list(labels),
        "incremental_cost": safe_incremental,
        "pick_only_references": safe_references,
        "cost_availability": availability,
        "explanation_template_key": row.explanation_template_key,
        "limitation_codes": list(limitations),
    }


def _alert_history(
    session: Session,
    *,
    draft: DraftSessionRow,
    candidates: tuple[MomentCandidate, ...],
    picks: tuple[MomentPick, ...],
    completed_at: datetime,
) -> HistoryPart:
    configuration = session.scalar(
        select(DraftAlertConfigurationRow).where(
            DraftAlertConfigurationRow.draft_session_id == draft.id
        )
    )
    if configuration is None:
        return HistoryPart(
            state="not_configured",
            metrics={
                "history_state": "not_configured",
                "event_count": 0,
                "included_event_count": 0,
                "truncated": False,
            },
            moments=(),
            reason_codes=("ALERTS_NOT_CONFIGURED",),
            limitation_codes=("SAVED_EVENTS_ONLY",),
            source_fingerprint=_fingerprint({"state": "not_configured"}),
        )
    events = tuple(
        session.scalars(
            select(DraftAlertEventRow)
            .where(DraftAlertEventRow.configuration_id == configuration.id)
            .order_by(
                DraftAlertEventRow.first_confirmed_draft_revision,
                DraftAlertEventRow.alert_kind,
                DraftAlertEventRow.id,
            )
        )
    )
    if len(events) > MAXIMUM_ALERT_SOURCE_EVENTS:
        return _corrupt_alerts("ALERT_HISTORY_LIMIT_EXCEEDED")
    updated_at = _parse_utc(configuration.updated_at)
    candidate_by_id = {candidate.player_id: candidate for candidate in candidates}
    pick_by_player = {pick.player_id: pick for pick in picks}
    ranked_trade_ids = (
        select(
            DraftAlertTradeReferenceRow.id.label("trade_id"),
            func.row_number()
            .over(
                partition_by=DraftAlertTradeReferenceRow.event_id,
                order_by=(
                    DraftAlertTradeReferenceRow.created_at.desc(),
                    DraftAlertTradeReferenceRow.id.desc(),
                ),
            )
            .label("trade_rank"),
        )
        .join(
            DraftAlertEventRow,
            DraftAlertTradeReferenceRow.event_id == DraftAlertEventRow.id,
        )
        .where(DraftAlertEventRow.configuration_id == configuration.id)
        .subquery()
    )
    trade_rows = tuple(
        session.scalars(
            select(DraftAlertTradeReferenceRow)
            .join(
                ranked_trade_ids,
                DraftAlertTradeReferenceRow.id == ranked_trade_ids.c.trade_id,
            )
            .where(ranked_trade_ids.c.trade_rank == 1)
            .order_by(DraftAlertTradeReferenceRow.event_id)
        )
    )
    trade_by_event: dict[str, DraftAlertTradeReferenceRow] = {}
    for trade in trade_rows:
        trade_by_event[trade.event_id] = trade
    if updated_at is None or updated_at > completed_at:
        return _corrupt_alerts("ALERT_CONFIGURATION_TIMESTAMP_INVALID")
    source_documents: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    for event in events:
        evidence = _safe_alert_evidence(event.current_evidence_json)
        explanations = _code_list(event.explanation_template_keys_json)
        limitations = _code_list(event.limitation_codes_json)
        candidate = candidate_by_id.get(event.player_id)
        trade = trade_by_event.get(event.id)
        safe_trade = _safe_trade_reference(trade) if trade is not None else None
        created_at = _parse_utc(event.created_at)
        updated_at = _parse_utc(event.updated_at)
        dismissed_at = (
            _parse_utc(event.dismissed_at) if event.dismissed_at is not None else None
        )
        superseded_at = (
            _parse_utc(event.superseded_at) if event.superseded_at is not None else None
        )
        if (
            evidence is None
            or explanations is None
            or limitations is None
            or candidate is None
            or event.alert_kind not in _ALERT_KINDS
            or event.status not in _ALERT_STATUS
            or event.confidence not in _ALERT_CONFIDENCE
            or event.freshness not in _ALERT_FRESHNESS
            or event.first_confirmed_draft_revision < 0
            or event.last_confirmed_draft_revision < event.first_confirmed_draft_revision
            or event.last_confirmed_draft_revision > draft.revision
            or evidence["draft_revision"] != event.last_confirmed_draft_revision
            or (trade is not None and safe_trade is None)
            or created_at is None
            or updated_at is None
            or updated_at < created_at
            or (event.dismissed_at is not None and dismissed_at is None)
            or (event.superseded_at is not None and superseded_at is None)
            or (event.status == "snoozed" and event.snooze_boundary is None)
            or (event.status == "dismissed" and dismissed_at is None)
            or (event.status == "superseded" and superseded_at is None)
            or (
                event.snooze_boundary is not None
                and (
                    not isinstance(event.snooze_boundary, int)
                    or isinstance(event.snooze_boundary, bool)
                    or event.snooze_boundary < 1
                )
            )
            or evidence["draft_revision"] > draft.revision
            or evidence["configuration_revision"] > configuration.revision
        ):
            return _corrupt_alerts("ALERT_EVENT_HISTORY_CORRUPT")
        drafted_pick = pick_by_player.get(event.player_id)
        drafted_outcome = (
            {"state": "not_drafted", "overall_pick": None}
            if drafted_pick is None
            else {
                "state": (
                    "drafted_by_user"
                    if drafted_pick.selecting_slot == draft.user_slot
                    else "drafted_by_other_slot"
                ),
                "overall_pick": drafted_pick.overall_pick,
            }
        )
        source_documents.append(
            {
                "event_id": event.id,
                "player_id": event.player_id,
                "player": {
                    "display_name": candidate.display_name,
                    "primary_position": candidate.primary_position,
                },
                "kind": event.alert_kind,
                "status": event.status,
                "confidence": event.confidence,
                "freshness": event.freshness,
                "first_confirmed_draft_revision": event.first_confirmed_draft_revision,
                "last_confirmed_draft_revision": event.last_confirmed_draft_revision,
                "snooze_boundary": event.snooze_boundary,
                "dismissed_at": event.dismissed_at,
                "superseded_at": event.superseded_at,
                "evidence": evidence,
                "explanation_template_keys": list(explanations),
                "limitation_codes": list(limitations),
                "trade_reference": safe_trade,
                "drafted_outcome": drafted_outcome,
            }
        )
        status_counts[event.status] += 1
        kind_counts[event.alert_kind] += 1
    if not configuration.enabled:
        state: AlertHistoryState = "disabled_at_completion"
        reason = "ALERTS_DISABLED_AT_COMPLETION"
    elif events:
        state = "available"
        reason = "RECORDED_ALERT_EVENTS_AVAILABLE"
    else:
        state = "configured_no_events"
        reason = "ALERTS_CONFIGURED_NO_EVENTS"
    retained = source_documents[:MAXIMUM_ALERT_MOMENTS]
    moments: list[HistoryMoment] = []
    for display_order, document in enumerate(retained, start=1):
        limitations = set(document["limitation_codes"]) | {
            "ALERT_CAUSATION_NOT_INFERRED",
            "SAVED_EVENTS_ONLY",
        }
        if document["kind"] == "trade_up_window":
            limitations.add("NO_TRADE_EXECUTION_CLAIM")
        moments.append(
            HistoryMoment(
                moment_key=f"alert:{document['event_id']}",
                moment_kind="alert_event",
                overall_pick=document["evidence"].get("current_overall_pick"),
                primary_player_id=document["player_id"],
                secondary_player_id=None,
                safe_summary={
                    "display_order": display_order,
                    **{
                        key: value
                        for key, value in document.items()
                        if key not in {"event_id", "player_id", "limitation_codes"}
                    },
                },
                reason_codes=(f"SAVED_{document['kind'].upper()}_EVENT",),
                limitation_codes=tuple(sorted(limitations)),
            )
        )
    metrics = {
        "history_state": state,
        "configuration_enabled_at_completion": configuration.enabled,
        "configuration_revision": configuration.revision,
        "event_count": len(source_documents),
        "included_event_count": len(moments),
        "truncated": len(source_documents) > len(moments),
        "event_kind_counts": {
            kind: kind_counts[kind] for kind in sorted(_ALERT_KINDS)
        },
        "event_status_counts": {
            status: status_counts[status] for status in sorted(_ALERT_STATUS)
        },
    }
    limitations = {"SAVED_EVENTS_ONLY", "ALERT_CAUSATION_NOT_INFERRED"}
    if not configuration.enabled:
        limitations.add("ALERTS_DISABLED")
    return HistoryPart(
        state=state,
        metrics=metrics,
        moments=tuple(moments),
        reason_codes=(reason,),
        limitation_codes=tuple(sorted(limitations)),
        source_fingerprint=_fingerprint(source_documents),
    )


def _corrupt_alerts(code: str) -> HistoryPart:
    return HistoryPart(
        state="unavailable_due_to_corruption",
        metrics={
            "history_state": "unavailable_due_to_corruption",
            "event_count": 0,
            "included_event_count": 0,
            "truncated": False,
        },
        moments=(),
        reason_codes=("RECORDED_ALERT_HISTORY_CORRUPT",),
        limitation_codes=("SAVED_EVENTS_ONLY", code),
        source_fingerprint=_fingerprint({"state": "corrupt", "code": code}),
    )


def load_decision_history(
    session: Session,
    *,
    draft: DraftSessionRow,
    mock_configuration: MockConfigurationRow | None,
    candidates: tuple[MomentCandidate, ...],
    picks: tuple[MomentPick, ...],
    completed_at: datetime,
) -> DecisionHistoryContext:
    strategy = (
        _strategy_history(
            session,
            configuration=mock_configuration,
            draft_total_picks=draft.team_count * draft.round_count,
            completed_at=completed_at,
        )
        if mock_configuration is not None
        else None
    )
    return DecisionHistoryContext(
        strategy=strategy,
        personal_board=reconstruct_personal_board_history(
            candidates=candidates,
            picks=picks,
            user_slot=draft.user_slot,
        ),
        alerts=_alert_history(
            session,
            draft=draft,
            candidates=candidates,
            picks=picks,
            completed_at=completed_at,
        ),
    )


def build_history_sections(
    context: DecisionHistoryContext,
    *,
    draft_mode: str,
    final_position_counts: dict[str, int],
    strategy_definition_version: str | None,
) -> tuple[HistorySectionResult, HistorySectionResult, HistorySectionResult]:
    if draft_mode == "live":
        strategy_state = strategy_section_state(draft_mode="live")
        strategy_section = HistorySectionResult(
            section_key="strategy_story",
            availability=strategy_state.availability,
            confidence=strategy_state.confidence,
            metrics={"saved_history_loaded": False},
            reason_codes=strategy_state.reason_codes,
            limitation_codes=("SAVED_EVENTS_ONLY",),
            explanation_template_key="strategy.not_applicable",
            explanation=render_explanation(
                template_key="strategy.not_applicable", values={}
            ),
        )
    else:
        assert context.strategy is not None
        strategy_state = strategy_section_state(
            draft_mode="mock",
            history_state=context.strategy.state,  # type: ignore[arg-type]
        )
        metrics = {
            **context.strategy.metrics,
            "final_position_counts": dict(sorted(final_position_counts.items())),
            "strategy_definition_version": strategy_definition_version,
        }
        if context.strategy.state == "valid":
            template_key = "strategy.summary"
            explanation = render_explanation(
                template_key=template_key,
                values={
                    "initial_strategy": str(metrics["initial_strategy"]),
                    "pivot_count": int(metrics["pivot_count"]),
                },
            )
        elif context.strategy.state == "incomplete":
            template_key = "strategy.limited"
            explanation = render_explanation(template_key=template_key, values={})
        else:
            template_key = "strategy.unavailable"
            explanation = render_explanation(template_key=template_key, values={})
        strategy_section = HistorySectionResult(
            section_key="strategy_story",
            availability=strategy_state.availability,
            confidence=strategy_state.confidence,
            metrics=metrics,
            reason_codes=strategy_state.reason_codes,
            limitation_codes=context.strategy.limitation_codes,
            explanation_template_key=template_key,
            explanation=explanation,
        )

    board = context.personal_board
    board_available = board.state == "valid"
    board_template = "personal_board.summary" if board_available else "personal_board.unavailable"
    board_section = HistorySectionResult(
        section_key="personal_board_choice_moments",
        availability="supported" if board_available else "unavailable",
        confidence="high" if board_available else "unavailable",
        metrics=board.metrics,
        reason_codes=board.reason_codes,
        limitation_codes=board.limitation_codes,
        explanation_template_key=board_template,
        explanation=render_explanation(
            template_key=board_template,
            values=(
                {"moment_count": int(board.metrics["moment_count"])}
                if board_available
                else {}
            ),
        ),
    )

    alerts = context.alerts
    alerts_available = alerts.state != "unavailable_due_to_corruption"
    alerts_template = "alerts.summary" if alerts_available else "alerts.unavailable"
    alert_section = HistorySectionResult(
        section_key="recorded_alert_moments",
        availability="supported" if alerts_available else "unavailable",
        confidence="high" if alerts_available else "unavailable",
        metrics=alerts.metrics,
        reason_codes=alerts.reason_codes,
        limitation_codes=alerts.limitation_codes,
        explanation_template_key=alerts_template,
        explanation=render_explanation(
            template_key=alerts_template,
            values=(
                {"alert_event_count": int(alerts.metrics["event_count"])}
                if alerts_available
                else {}
            ),
        ),
    )
    return strategy_section, board_section, alert_section
