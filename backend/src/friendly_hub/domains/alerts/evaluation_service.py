from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from friendly_hub.core.errors import HubError
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.alerts.configuration_service import (
    assess_snapshot_compatibility,
)
from friendly_hub.domains.alerts.engine import (
    CurrentPickValue,
    IntegerRange,
    PickAssetValue,
    assess_confidence,
    elapsed_freshness,
    incremental_trade_cost,
    market_gap_range,
    match_pick_cost_references,
    personal_qualifies,
    return_risk_band,
    target_pick_window,
    value_alert_eligible,
)
from friendly_hub.domains.alerts.models import (
    AlertEvidenceSnapshotRow,
    AlertPickValueSignalRow,
    AlertPlayerSignalRow,
    DraftAlertConfigurationRow,
    DraftAlertEvaluationRow,
    DraftAlertEventRow,
    DraftAlertTradeReferenceRow,
)
from friendly_hub.domains.alerts.schemas import (
    AlertDetailRead,
    AlertEventRead,
    AlertGroupRead,
    AlertPlayerRead,
    AlertTradeReferenceRead,
    DraftAlertEvaluationRead,
    DraftAlertEvaluationRequest,
    DraftAlertEvaluationResponse,
    DraftAlertListResponse,
)
from friendly_hub.domains.drafts.models import (
    DraftCandidateRow,
    DraftPickRow,
    DraftSessionRow,
)
from friendly_hub.domains.mocks.models import (
    MockConfigurationRow,
    MockStrategyRevisionRow,
)

_CONFIG_REVISION_CODE_PREFIX = "INTERNAL_CONFIGURATION_REVISION_"
_EXPECTED_FRESHNESS = (7, 21, 45)
_PICK_FRESHNESS = (30, 60, 90)
_MAX_CANDIDATES = 500


@dataclass(frozen=True)
class EvaluationState:
    draft: DraftSessionRow
    configuration: DraftAlertConfigurationRow
    snapshot: AlertEvidenceSnapshotRow
    candidates: tuple[DraftCandidateRow, ...]
    available_candidates: tuple[DraftCandidateRow, ...]
    picks: tuple[DraftPickRow, ...]
    current_pick: DraftPickRow | None
    next_user_pick: DraftPickRow | None
    user_roster_counts: dict[str, int]
    strategy: dict[str, object]
    fingerprint: str


@dataclass(frozen=True)
class DesiredEvent:
    candidate: DraftCandidateRow
    kind: str
    confidence: str
    freshness: str
    evidence: dict[str, object]
    explanation_template_keys: tuple[str, ...]
    limitation_codes: tuple[str, ...]
    trade_reference: dict[str, object] | None = None


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _load_json(value: str) -> object:
    return json.loads(value)


def _error(
    code: str,
    message: str,
    action: str,
    *,
    status_code: int,
) -> HubError:
    return HubError(
        code=code,
        message=message,
        action=f"{action} Draft picks and mock decisions remain unchanged.",
        status_code=status_code,
    )


def _require_draft(session: Session, session_id: str) -> DraftSessionRow:
    draft = session.get(DraftSessionRow, session_id)
    if draft is None:
        raise _error(
            "DRAFT.SESSION_NOT_FOUND",
            "That draft session does not exist.",
            "Choose an available draft session.",
            status_code=404,
        )
    return draft


def _require_configuration(
    session: Session,
    session_id: str,
) -> DraftAlertConfigurationRow:
    configuration = session.scalar(
        select(DraftAlertConfigurationRow).where(
            DraftAlertConfigurationRow.draft_session_id == session_id
        )
    )
    if configuration is None:
        raise _error(
            "ALERT_CONFIGURATION_NOT_FOUND",
            "This draft does not have an alert configuration.",
            "Attach compatible committed evidence before evaluating alerts.",
            status_code=404,
        )
    return configuration


def _require_revisions(
    draft: DraftSessionRow,
    configuration: DraftAlertConfigurationRow,
    payload: DraftAlertEvaluationRequest,
) -> None:
    if draft.revision != payload.draft_revision:
        raise _error(
            "ALERT_DRAFT_STALE_REVISION",
            (
                "The draft changed before alert evaluation "
                f"(expected revision {payload.draft_revision}, current revision "
                f"{draft.revision})."
            ),
            "Refresh the draft and evaluate its current revision.",
            status_code=409,
        )
    if configuration.revision != payload.configuration_revision:
        raise _error(
            "ALERT_CONFIGURATION_STALE_REVISION",
            (
                "The alert configuration changed before evaluation "
                f"(expected revision {payload.configuration_revision}, current "
                f"revision {configuration.revision})."
            ),
            "Refresh the alert configuration and evaluate its current revision.",
            status_code=409,
        )


def _latest_evaluation(
    session: Session,
    configuration_id: str,
) -> DraftAlertEvaluationRow | None:
    return session.scalar(
        select(DraftAlertEvaluationRow)
        .where(DraftAlertEvaluationRow.configuration_id == configuration_id)
        .order_by(
            DraftAlertEvaluationRow.evaluated_at.desc(),
            DraftAlertEvaluationRow.id.desc(),
        )
        .limit(1)
    )


def _visible_limitation_codes(row: DraftAlertEvaluationRow) -> list[str]:
    raw = _load_json(row.limitation_codes_json)
    if not isinstance(raw, list):
        return []
    return sorted(
        code
        for code in raw
        if isinstance(code, str) and not code.startswith(_CONFIG_REVISION_CODE_PREFIX)
    )


def _evaluation_configuration_revision(row: DraftAlertEvaluationRow) -> int:
    raw = _load_json(row.limitation_codes_json)
    if isinstance(raw, list):
        for code in raw:
            if isinstance(code, str) and code.startswith(_CONFIG_REVISION_CODE_PREFIX):
                suffix = code.removeprefix(_CONFIG_REVISION_CODE_PREFIX)
                if suffix.isdigit():
                    return int(suffix)
    return 0


def _require_client_evaluation_revision(
    latest: DraftAlertEvaluationRow | None,
    expected: int | None,
) -> None:
    current = latest.draft_revision if latest is not None else None
    if current != expected:
        raise _error(
            "ALERT_EVALUATION_STALE",
            (
                "The client alert state is stale "
                f"(expected last evaluation revision {expected}, current "
                f"revision {current})."
            ),
            "Refresh alerts and retry with the visible last evaluation revision.",
            status_code=409,
        )


def _candidate_rows(
    session: Session,
    session_id: str,
) -> tuple[DraftCandidateRow, ...]:
    return tuple(
        session.scalars(
            select(DraftCandidateRow)
            .where(DraftCandidateRow.session_id == session_id)
            .order_by(DraftCandidateRow.player_id)
        )
    )


def _pick_rows(
    session: Session,
    session_id: str,
) -> tuple[DraftPickRow, ...]:
    return tuple(
        session.scalars(
            select(DraftPickRow)
            .where(DraftPickRow.session_id == session_id)
            .order_by(DraftPickRow.overall_pick)
        )
    )


def _strategy_state(
    session: Session,
    draft: DraftSessionRow,
) -> dict[str, object]:
    if draft.mode != "mock":
        return {
            "state": "unavailable",
            "strategy_key": None,
            "strategy_revision": None,
            "roster_counts": {},
        }
    configuration = session.scalar(
        select(MockConfigurationRow).where(MockConfigurationRow.draft_session_id == draft.id)
    )
    if configuration is None:
        return {
            "state": "unavailable",
            "strategy_key": None,
            "strategy_revision": None,
            "roster_counts": {},
        }
    revision = session.scalar(
        select(MockStrategyRevisionRow)
        .where(MockStrategyRevisionRow.mock_configuration_id == configuration.id)
        .order_by(MockStrategyRevisionRow.sequence_number.desc())
        .limit(1)
    )
    roster_counts = _load_json(revision.user_roster_counts_json) if revision is not None else {}
    return {
        "state": "available",
        "strategy_key": configuration.current_strategy_key,
        "strategy_revision": (revision.sequence_number if revision is not None else None),
        "roster_counts": (roster_counts if isinstance(roster_counts, dict) else {}),
    }


def _personal_qualified(
    configuration: DraftAlertConfigurationRow,
    candidate: DraftCandidateRow,
) -> bool:
    if configuration.personal_qualifier_mode == "tier_only":
        return personal_qualifies(
            tier_order=candidate.tier_order,
            favorite=False,
            eligible_tier_count=configuration.eligible_tier_count,
        )
    if configuration.personal_qualifier_mode == "favorite_only":
        return candidate.favorite
    return personal_qualifies(
        tier_order=candidate.tier_order,
        favorite=candidate.favorite,
        eligible_tier_count=configuration.eligible_tier_count,
    )


def _fingerprint_payload(
    *,
    draft: DraftSessionRow,
    configuration: DraftAlertConfigurationRow,
    snapshot: AlertEvidenceSnapshotRow,
    candidates: tuple[DraftCandidateRow, ...],
    available_candidates: tuple[DraftCandidateRow, ...],
    picks: tuple[DraftPickRow, ...],
    current_pick: DraftPickRow | None,
    next_user_pick: DraftPickRow | None,
    user_roster_counts: dict[str, int],
    strategy: dict[str, object],
) -> dict[str, object]:
    return {
        "engine_version": configuration.engine_version,
        "rule_version": configuration.rule_version,
        "draft_session_id": draft.id,
        "draft_revision": draft.revision,
        "active_pick": (
            {
                "overall_pick": current_pick.overall_pick,
                "round_number": current_pick.round_number,
                "pick_in_round": current_pick.pick_in_round,
                "selecting_slot": current_pick.selecting_slot,
            }
            if current_pick is not None
            else None
        ),
        "completed_picks": [
            {
                "overall_pick": pick.overall_pick,
                "player_id": pick.player_id,
                "correction_count": pick.correction_count,
            }
            for pick in picks
            if pick.player_id is not None
        ],
        "available_candidate_ids": [candidate.player_id for candidate in available_candidates],
        "user_roster_counts": user_roster_counts,
        "next_user_pick": (next_user_pick.overall_pick if next_user_pick is not None else None),
        "personal_qualifiers": [
            {
                "player_id": candidate.player_id,
                "manual_rank": candidate.manual_rank,
                "tier_order": candidate.tier_order,
                "favorite": candidate.favorite,
            }
            for candidate in candidates
        ],
        "strategy": strategy,
        "configuration_revision": configuration.revision,
        "evidence_content_hash": snapshot.content_hash,
        "freshness_policy_version": configuration.freshness_policy_version,
    }


def _build_state(
    session: Session,
    draft: DraftSessionRow,
    configuration: DraftAlertConfigurationRow,
) -> EvaluationState:
    snapshot = session.get(
        AlertEvidenceSnapshotRow,
        configuration.evidence_snapshot_id,
    )
    if snapshot is None or snapshot.status != "committed":
        raise _error(
            "ALERT_EVIDENCE_NOT_FOUND",
            "The configured evidence snapshot is no longer available.",
            "Attach an available committed snapshot before evaluating.",
            status_code=404,
        )
    candidates = _candidate_rows(session, draft.id)
    picks = _pick_rows(session, draft.id)
    drafted_ids = {pick.player_id for pick in picks if pick.player_id is not None}
    available = tuple(
        candidate for candidate in candidates if candidate.player_id not in drafted_ids
    )
    if len(available) > _MAX_CANDIDATES:
        raise _error(
            "ALERT_EVALUATION_FAILED",
            "The draft has more than 500 available alert candidates.",
            "Reduce the frozen candidate pool before evaluating alerts.",
            status_code=422,
        )
    current_pick = next(
        (pick for pick in picks if pick.player_id is None),
        None,
    )
    if draft.status in {"completed", "reset"}:
        current_pick = None
    next_user_pick = next(
        (
            pick
            for pick in picks
            if pick.player_id is None
            and pick.selecting_slot == draft.user_slot
            and (current_pick is None or pick.overall_pick >= current_pick.overall_pick)
        ),
        None,
    )
    candidate_by_player = {candidate.player_id: candidate for candidate in candidates}
    user_roster_counts: dict[str, int] = {}
    for pick in picks:
        if pick.player_id is None or pick.selecting_slot != draft.user_slot:
            continue
        candidate = candidate_by_player.get(pick.player_id)
        if candidate is None:
            continue
        position = candidate.primary_position
        user_roster_counts[position] = user_roster_counts.get(position, 0) + 1
    strategy = _strategy_state(session, draft)
    payload = _fingerprint_payload(
        draft=draft,
        configuration=configuration,
        snapshot=snapshot,
        candidates=candidates,
        available_candidates=available,
        picks=picks,
        current_pick=current_pick,
        next_user_pick=next_user_pick,
        user_roster_counts=user_roster_counts,
        strategy=strategy,
    )
    fingerprint = hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()
    return EvaluationState(
        draft=draft,
        configuration=configuration,
        snapshot=snapshot,
        candidates=candidates,
        available_candidates=available,
        picks=picks,
        current_pick=current_pick,
        next_user_pick=next_user_pick,
        user_roster_counts=user_roster_counts,
        strategy=strategy,
        fingerprint=fingerprint,
    )


def _component(
    band: str | None,
    *,
    unavailable_reason: str,
) -> dict[str, object]:
    if band is None:
        return {
            "state": "unavailable",
            "band": None,
            "reasons": [unavailable_reason],
        }
    return {"state": "available", "band": band, "reasons": []}


def _round_pick_label(overall_pick: int, team_count: int) -> str:
    round_number = ((overall_pick - 1) // team_count) + 1
    pick_in_round = ((overall_pick - 1) % team_count) + 1
    return f"Round {round_number}, pick {pick_in_round}"


def _pick_reference(
    session: Session,
    state: EvaluationState,
    *,
    target: IntegerRange,
    evaluated_at: datetime,
) -> tuple[dict[str, object], list[str]]:
    rows = list(
        session.scalars(
            select(AlertPickValueSignalRow).where(
                AlertPickValueSignalRow.evidence_snapshot_id == state.snapshot.id
            )
        )
    )
    limitations: set[str] = set()
    if not rows:
        return {
            "target_pick_window": {"low": target.low, "high": target.high},
            "target_round_pick_labels": [
                _round_pick_label(target.low, state.draft.team_count),
                _round_pick_label(target.high, state.draft.team_count),
            ],
            "incremental_cost": None,
            "pick_only_references": [],
            "cost_availability": "unavailable",
            "explanation_template_key": "PICK_ONLY_COST_UNAVAILABLE_V1",
            "limitation_codes": ["PICK_CURVE_UNAVAILABLE"],
        }, ["PICK_CURVE_UNAVAILABLE"]

    freshness_states = {
        elapsed_freshness(
            evidence_as_of=datetime.fromisoformat(row.evidence_as_of),
            evaluated_at=evaluated_at,
            fresh_through_days=_PICK_FRESHNESS[0],
            aging_through_days=_PICK_FRESHNESS[1],
            stale_through_days=_PICK_FRESHNESS[2],
        )
        for row in rows
    }
    if freshness_states != {"fresh"}:
        limitations.add("PICK_CURVE_NOT_FRESH")
    current_curve = [
        CurrentPickValue(
            overall_pick=row.overall_pick,
            value=IntegerRange(row.value_low, row.value_high),
        )
        for row in rows
        if row.asset_type == "current_draft_pick" and row.overall_pick is not None
    ]
    future_assets = [
        PickAssetValue(
            asset_key=row.asset_key,
            season_offset=row.season_offset,
            round_number=row.round_number,
            value=IntegerRange(row.value_low, row.value_high),
        )
        for row in rows
        if row.asset_type == "future_round"
        and row.season_offset is not None
        and row.round_number is not None
    ]
    incremental = None
    references: tuple[PickAssetValue, ...] = ()
    if not limitations and state.next_user_pick is not None and current_curve:
        incremental = incremental_trade_cost(
            user_next_pick=state.next_user_pick.overall_pick,
            target_window=target,
            curve=current_curve,
        )
        if incremental is not None and future_assets:
            references = match_pick_cost_references(
                incremental_cost=incremental,
                assets=future_assets,
            )
    if incremental is None or not references:
        limitations.add("PICK_ONLY_REFERENCE_UNAVAILABLE")
    available = not limitations
    referenced_keys = {item.asset_key for item in references}
    advisory_codes = {
        code
        for row in rows
        if (row.asset_type == "current_draft_pick" or row.asset_key in referenced_keys)
        for code in _load_json(row.limitation_codes_json)
        if isinstance(code, str)
    }
    visible_limitations = sorted(limitations | advisory_codes)
    reference = {
        "target_pick_window": {"low": target.low, "high": target.high},
        "target_round_pick_labels": [
            _round_pick_label(target.low, state.draft.team_count),
            _round_pick_label(target.high, state.draft.team_count),
        ],
        "incremental_cost": (
            {"low": incremental.low, "high": incremental.high} if incremental is not None else None
        ),
        "pick_only_references": [
            {
                "label": (f"Year {item.season_offset}, round {item.round_number}"),
                "season_offset": item.season_offset,
                "round": item.round_number,
                "value": {"low": item.value.low, "high": item.value.high},
            }
            for item in references
        ],
        "cost_availability": "available" if available else "unavailable",
        "explanation_template_key": (
            "PICK_ONLY_COST_REFERENCE_V1" if available else "PICK_ONLY_COST_UNAVAILABLE_V1"
        ),
        "limitation_codes": visible_limitations,
    }
    return reference, visible_limitations


def _event_evidence(
    state: EvaluationState,
    candidate: DraftCandidateRow,
    signal: AlertPlayerSignalRow,
    *,
    compatibility: str,
    expected: IntegerRange | None,
    gap: IntegerRange | None,
    risk: str,
    freshness: str,
    confidence_reasons: list[str],
    limitations: list[str],
    target: IntegerRange | None = None,
    cost_availability: str = "not_applicable",
) -> dict[str, object]:
    personal_band = (
        f"tier_{candidate.tier_order}"
        if candidate.tier_order is not None
        else ("favorite" if candidate.favorite else "qualified")
    )
    strategy = state.strategy
    return {
        "source_label": state.snapshot.source_label,
        "source_as_of": state.snapshot.source_as_of,
        "format_compatibility": compatibility,
        "expected_selection": (
            {"low": expected.low, "high": expected.high} if expected is not None else None
        ),
        "market_gap": ({"low": gap.low, "high": gap.high} if gap is not None else None),
        "return_risk": risk,
        "current_overall_pick": (
            state.current_pick.overall_pick if state.current_pick is not None else None
        ),
        "next_user_pick": (
            state.next_user_pick.overall_pick if state.next_user_pick is not None else None
        ),
        "personal_reason": {
            "manual_rank": candidate.manual_rank,
            "tier_order": candidate.tier_order,
            "favorite": candidate.favorite,
            "qualifier_mode": state.configuration.personal_qualifier_mode,
            "qualified": True,
        },
        "components": {
            "personal_conviction": _component(
                personal_band,
                unavailable_reason="PERSONAL_CONVICTION_UNAVAILABLE",
            ),
            "dynasty_market": _component(
                signal.market_band or "expected_selection",
                unavailable_reason="DYNASTY_MARKET_UNAVAILABLE",
            ),
            "win_now_production": _component(
                signal.win_now_production_band,
                unavailable_reason="WIN_NOW_PRODUCTION_UNAVAILABLE",
            ),
            "age_risk": _component(
                signal.age_risk_band,
                unavailable_reason="AGE_RISK_UNAVAILABLE",
            ),
            "strategy_fit": {
                "state": strategy["state"],
                "band": strategy["strategy_key"],
                "reasons": (
                    [] if strategy["state"] == "available" else ["STRATEGY_FIT_UNAVAILABLE"]
                ),
            },
        },
        "target_pick_window": (
            {"low": target.low, "high": target.high} if target is not None else None
        ),
        "cost_availability": cost_availability,
        "confidence_reasons": confidence_reasons,
        "limitation_codes": limitations,
        "engine_version": state.configuration.engine_version,
        "rule_version": state.configuration.rule_version,
        "freshness_policy_version": (state.configuration.freshness_policy_version),
        "configuration_revision": state.configuration.revision,
        "draft_revision": state.draft.revision,
    }


def _desired_events(
    session: Session,
    state: EvaluationState,
    *,
    evaluated_at: datetime,
) -> tuple[DesiredEvent, ...]:
    signals = {
        row.player_id: row
        for row in session.scalars(
            select(AlertPlayerSignalRow).where(
                AlertPlayerSignalRow.evidence_snapshot_id == state.snapshot.id
            )
        )
    }
    assessment = assess_snapshot_compatibility(
        session,
        draft=state.draft,
        snapshot=state.snapshot,
    )
    desired: list[DesiredEvent] = []
    for candidate in state.available_candidates:
        signal = signals.get(candidate.player_id)
        if signal is None or not _personal_qualified(
            state.configuration,
            candidate,
        ):
            continue
        expected = (
            IntegerRange(
                signal.expected_pick_low,
                signal.expected_pick_high,
            )
            if signal.expected_pick_low is not None and signal.expected_pick_high is not None
            else None
        )
        freshness = elapsed_freshness(
            evidence_as_of=datetime.fromisoformat(signal.evidence_as_of),
            evaluated_at=evaluated_at,
            fresh_through_days=_EXPECTED_FRESHNESS[0],
            aging_through_days=_EXPECTED_FRESHNESS[1],
            stale_through_days=_EXPECTED_FRESHNESS[2],
        )
        signal_limitations = [
            code for code in _load_json(signal.limitation_codes_json) if isinstance(code, str)
        ]
        confidence = assess_confidence(
            exact_mapping=True,
            freshness=freshness,
            format_compatibility=assessment.state,
            expected_pick=expected,
            critical_limitations=signal_limitations,
        )
        gap = (
            market_gap_range(
                current_overall_pick=state.current_pick.overall_pick,
                expected_pick=expected,
            )
            if state.current_pick is not None and expected is not None
            else None
        )
        risk = return_risk_band(
            expected_pick=expected,
            next_user_pick=(
                state.next_user_pick.overall_pick if state.next_user_pick is not None else None
            ),
        )
        limitations = sorted(
            set(signal_limitations)
            | set(assessment.reasons)
            | (
                {f"EXPECTED_SELECTION_{freshness.upper()}"}
                if freshness in {"stale", "expired", "invalid"}
                else set()
            )
            | (
                {"WIN_NOW_PRODUCTION_UNAVAILABLE"}
                if signal.win_now_production_band is None
                else set()
            )
            | ({"AGE_RISK_UNAVAILABLE"} if signal.age_risk_band is None else set())
        )
        confidence_reasons = list(confidence.reason_codes)
        base_evidence = _event_evidence(
            state,
            candidate,
            signal,
            compatibility=assessment.state,
            expected=expected,
            gap=gap,
            risk=risk,
            freshness=freshness,
            confidence_reasons=confidence_reasons,
            limitations=limitations,
        )
        if confidence.level == "unavailable" or gap is None:
            warning_reasons = sorted(set(limitations) | set(confidence_reasons))
            desired.append(
                DesiredEvent(
                    candidate=candidate,
                    kind="evidence_warning",
                    confidence="unavailable",
                    freshness=freshness,
                    evidence={
                        **base_evidence,
                        "limitation_codes": warning_reasons,
                    },
                    explanation_template_keys=("EVIDENCE_UNAVAILABLE_WARNING_V1",),
                    limitation_codes=tuple(warning_reasons),
                )
            )
            continue
        assert expected is not None
        value_eligible = value_alert_eligible(
            personal_qualified=True,
            gap=gap,
            confidence=confidence.level,
            minimum_gap=state.configuration.minimum_conservative_gap,
        )
        if value_eligible:
            desired.append(
                DesiredEvent(
                    candidate=candidate,
                    kind="value_watch",
                    confidence=confidence.level,
                    freshness=freshness,
                    evidence=base_evidence,
                    explanation_template_keys=("VALUE_WATCH_RANGE_V1",),
                    limitation_codes=tuple(limitations),
                )
            )
        if risk in {"uncertain", "unlikely_to_return"}:
            desired.append(
                DesiredEvent(
                    candidate=candidate,
                    kind="return_risk",
                    confidence=confidence.level,
                    freshness=freshness,
                    evidence=base_evidence,
                    explanation_template_keys=(f"RETURN_RISK_{risk.upper()}_V1",),
                    limitation_codes=tuple(limitations),
                )
            )
        if (
            risk == "unlikely_to_return"
            and state.current_pick is not None
            and state.next_user_pick is not None
        ):
            target = target_pick_window(
                current_overall_pick=state.current_pick.overall_pick,
                next_user_pick=state.next_user_pick.overall_pick,
                expected_pick=expected,
            )
            if target is not None:
                reference, cost_limitations = _pick_reference(
                    session,
                    state,
                    target=target,
                    evaluated_at=evaluated_at,
                )
                trade_limitations = sorted(set(limitations) | set(cost_limitations))
                trade_evidence = _event_evidence(
                    state,
                    candidate,
                    signal,
                    compatibility=assessment.state,
                    expected=expected,
                    gap=gap,
                    risk=risk,
                    freshness=freshness,
                    confidence_reasons=confidence_reasons,
                    limitations=trade_limitations,
                    target=target,
                    cost_availability=str(reference["cost_availability"]),
                )
                desired.append(
                    DesiredEvent(
                        candidate=candidate,
                        kind="trade_up_window",
                        confidence=confidence.level,
                        freshness=freshness,
                        evidence=trade_evidence,
                        explanation_template_keys=("TRADE_UP_WINDOW_V1",),
                        limitation_codes=tuple(trade_limitations),
                        trade_reference=reference,
                    )
                )
        if freshness == "stale":
            desired.append(
                DesiredEvent(
                    candidate=candidate,
                    kind="evidence_warning",
                    confidence="low",
                    freshness=freshness,
                    evidence=base_evidence,
                    explanation_template_keys=("EVIDENCE_STALE_WARNING_V1",),
                    limitation_codes=tuple(limitations),
                )
            )
    return tuple(desired)


def _event_key(
    configuration: DraftAlertConfigurationRow,
    draft_revision: int,
    player_id: str,
    kind: str,
) -> str:
    raw = f"{configuration.id}:{configuration.revision}:{draft_revision}:{player_id}:{kind}"
    return f"alert-v1:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def _active_event_map(
    rows: list[DraftAlertEventRow],
    configuration_revision: int,
) -> dict[tuple[str, str], DraftAlertEventRow]:
    result: dict[tuple[str, str], DraftAlertEventRow] = {}
    for row in rows:
        if row.status == "superseded":
            continue
        evidence = _load_json(row.current_evidence_json)
        if (
            isinstance(evidence, dict)
            and evidence.get("configuration_revision") == configuration_revision
        ):
            result[(row.player_id, row.alert_kind)] = row
    return result


def _add_trade_reference(
    session: Session,
    *,
    event: DraftAlertEventRow,
    snapshot_id: str,
    reference: dict[str, object],
    created_at: str,
) -> None:
    target = reference["target_pick_window"]
    incremental = reference["incremental_cost"]
    session.add(
        DraftAlertTradeReferenceRow(
            id=str(uuid4()),
            event_id=event.id,
            target_overall_pick_low=int(target["low"]),
            target_overall_pick_high=int(target["high"]),
            target_round_pick_labels_json=_json(reference["target_round_pick_labels"]),
            cost_range_json=_json(
                {
                    "incremental_cost": incremental,
                    "pick_only_references": reference["pick_only_references"],
                    "cost_availability": reference["cost_availability"],
                }
            ),
            pick_curve_snapshot_id=snapshot_id,
            explanation_template_key=str(reference["explanation_template_key"]),
            limitation_codes_json=_json(reference["limitation_codes"]),
            created_at=created_at,
        )
    )


def _reconcile_events(
    session: Session,
    state: EvaluationState,
    desired: tuple[DesiredEvent, ...],
    *,
    now: str,
) -> tuple[int, int, int]:
    rows = list(
        session.scalars(
            select(DraftAlertEventRow).where(
                DraftAlertEventRow.configuration_id == state.configuration.id
            )
        )
    )
    active = _active_event_map(rows, state.configuration.revision)
    matched_ids: set[str] = set()
    opened = 0
    updated = 0
    for item in desired:
        key = (item.candidate.player_id, item.kind)
        row = active.get(key)
        evidence_json = _json(item.evidence)
        if row is None:
            row = DraftAlertEventRow(
                id=str(uuid4()),
                configuration_id=state.configuration.id,
                player_id=item.candidate.player_id,
                deterministic_event_key=_event_key(
                    state.configuration,
                    state.draft.revision,
                    item.candidate.player_id,
                    item.kind,
                ),
                alert_kind=item.kind,
                status="open",
                confidence=item.confidence,
                freshness=item.freshness,
                first_confirmed_draft_revision=state.draft.revision,
                last_confirmed_draft_revision=state.draft.revision,
                original_evidence_json=evidence_json,
                current_evidence_json=evidence_json,
                explanation_template_keys_json=_json(item.explanation_template_keys),
                limitation_codes_json=_json(item.limitation_codes),
                snooze_boundary=None,
                dismissed_at=None,
                superseded_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            opened += 1
        else:
            row.last_confirmed_draft_revision = state.draft.revision
            row.current_evidence_json = evidence_json
            row.confidence = item.confidence
            row.freshness = item.freshness
            row.explanation_template_keys_json = _json(item.explanation_template_keys)
            row.limitation_codes_json = _json(item.limitation_codes)
            row.updated_at = now
            updated += 1
        matched_ids.add(row.id)
        if item.trade_reference is not None:
            _add_trade_reference(
                session,
                event=row,
                snapshot_id=state.snapshot.id,
                reference=item.trade_reference,
                created_at=now,
            )

    superseded = 0
    available_ids = {candidate.player_id for candidate in state.available_candidates}
    for row in rows:
        if row.status == "superseded" or row.id in matched_ids:
            continue
        evidence = _load_json(row.current_evidence_json)
        old_revision = (
            evidence.get("configuration_revision") if isinstance(evidence, dict) else None
        )
        if old_revision != state.configuration.revision:
            reason = "CONFIGURATION_CHANGED"
        elif row.player_id not in available_ids:
            reason = "PLAYER_UNAVAILABLE"
        else:
            reason = "CONDITION_NO_LONGER_VALID"
        codes = {code for code in _load_json(row.limitation_codes_json) if isinstance(code, str)}
        codes.add(f"SUPERSEDED_{reason}")
        row.status = "superseded"
        row.superseded_at = now
        row.limitation_codes_json = _json(sorted(codes))
        row.updated_at = now
        superseded += 1
    return opened, updated, superseded


def _lock_guards(
    session: Session,
    *,
    draft: DraftSessionRow,
    configuration: DraftAlertConfigurationRow,
) -> None:
    draft_result = session.execute(
        update(DraftSessionRow)
        .where(
            DraftSessionRow.id == draft.id,
            DraftSessionRow.revision == draft.revision,
        )
        .values(updated_at=DraftSessionRow.updated_at)
        .execution_options(synchronize_session=False)
    )
    configuration_result = session.execute(
        update(DraftAlertConfigurationRow)
        .where(
            DraftAlertConfigurationRow.id == configuration.id,
            DraftAlertConfigurationRow.revision == configuration.revision,
        )
        .values(updated_at=DraftAlertConfigurationRow.updated_at)
        .execution_options(synchronize_session=False)
    )
    if draft_result.rowcount != 1 or configuration_result.rowcount != 1:
        session.rollback()
        raise _error(
            "ALERT_EVALUATION_STALE",
            "The draft or alert configuration changed during evaluation.",
            "Refresh both records and retry the evaluation.",
            status_code=409,
        )


def _commit_transaction(session: Session) -> None:
    session.commit()


def _evaluation_read(
    row: DraftAlertEvaluationRow,
    *,
    idempotent: bool,
) -> DraftAlertEvaluationRead:
    return DraftAlertEvaluationRead(
        id=row.id,
        draft_revision=row.draft_revision,
        configuration_revision=_evaluation_configuration_revision(row),
        current_overall_pick=row.current_overall_pick,
        next_user_pick=row.next_user_pick,
        candidate_count=row.candidate_count,
        opened_count=row.opened_count,
        updated_count=row.updated_count,
        superseded_count=row.superseded_count,
        limitation_codes=_visible_limitation_codes(row),
        evaluated_at=row.evaluated_at,
        idempotent=idempotent,
    )


def _event_read(row: DraftAlertEventRow) -> AlertEventRead:
    return AlertEventRead(
        id=row.id,
        kind=row.alert_kind,
        status=row.status,
        confidence=row.confidence,
        freshness=row.freshness,
        first_confirmed_draft_revision=(row.first_confirmed_draft_revision),
        last_confirmed_draft_revision=row.last_confirmed_draft_revision,
        explanation_template_keys=list(_load_json(row.explanation_template_keys_json)),
        limitation_codes=list(_load_json(row.limitation_codes_json)),
        evidence=_load_json(row.current_evidence_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _list_response(
    session: Session,
    *,
    draft: DraftSessionRow,
    configuration: DraftAlertConfigurationRow,
    scope: str,
    limit: int,
    offset: int,
    idempotent_latest: bool = False,
) -> DraftAlertListResponse:
    filters = [DraftAlertEventRow.configuration_id == configuration.id]
    if scope == "current":
        filters.append(DraftAlertEventRow.status.in_(("open", "snoozed")))
    if scope == "current" and not configuration.enabled:
        total = 0
        selected_ids: list[str] = []
    else:
        total = (
            session.scalar(
                select(func.count(func.distinct(DraftAlertEventRow.player_id))).where(*filters)
            )
            or 0
        )
        selected_ids = list(
            session.scalars(
                select(DraftAlertEventRow.player_id)
                .join(
                    DraftCandidateRow,
                    (DraftCandidateRow.session_id == draft.id)
                    & (DraftCandidateRow.player_id == DraftAlertEventRow.player_id),
                )
                .where(*filters)
                .group_by(DraftAlertEventRow.player_id)
                .order_by(
                    func.coalesce(
                        DraftCandidateRow.manual_rank,
                        1_000_000,
                    ),
                    func.coalesce(
                        DraftCandidateRow.tier_order,
                        1_000_000,
                    ),
                    DraftCandidateRow.display_name,
                    DraftAlertEventRow.player_id,
                )
                .offset(offset)
                .limit(limit)
            )
        )
    candidate_by_player = {
        row.player_id: row
        for row in session.scalars(
            select(DraftCandidateRow).where(
                DraftCandidateRow.session_id == draft.id,
                DraftCandidateRow.player_id.in_(selected_ids),
            )
        )
    }
    rows = (
        list(
            session.scalars(
                select(DraftAlertEventRow).where(
                    *filters,
                    DraftAlertEventRow.player_id.in_(selected_ids),
                )
            )
        )
        if selected_ids
        else []
    )
    grouped: dict[str, list[DraftAlertEventRow]] = {}
    for row in rows:
        grouped.setdefault(row.player_id, []).append(row)
    items = []
    kind_order = {
        "value_watch": 0,
        "return_risk": 1,
        "trade_up_window": 2,
        "evidence_warning": 3,
    }
    for player_id in selected_ids:
        candidate = candidate_by_player[player_id]
        event_rows = sorted(
            grouped[player_id],
            key=lambda row: (
                kind_order.get(row.alert_kind, 99),
                row.created_at,
                row.id,
            ),
        )
        items.append(
            AlertGroupRead(
                player=AlertPlayerRead(
                    id=candidate.player_id,
                    display_name=candidate.display_name,
                    primary_position=candidate.primary_position,
                    team=candidate.team,
                ),
                events=[_event_read(row) for row in event_rows],
            )
        )
    latest = _latest_evaluation(session, configuration.id)
    if latest is None:
        evaluation_state = "missing"
    else:
        try:
            current_state = _build_state(session, draft, configuration)
            evaluation_state = (
                "current" if latest.input_fingerprint == current_state.fingerprint else "stale"
            )
        except HubError:
            evaluation_state = "stale"
    return DraftAlertListResponse(
        scope=scope,
        evaluation_state=evaluation_state,
        draft_revision=draft.revision,
        configuration_revision=configuration.revision,
        alerts_enabled=configuration.enabled,
        latest_evaluation=(
            _evaluation_read(latest, idempotent=idempotent_latest) if latest is not None else None
        ),
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


def evaluate_draft_alerts(
    session: Session,
    *,
    session_id: str,
    payload: DraftAlertEvaluationRequest,
) -> DraftAlertEvaluationResponse:
    draft = _require_draft(session, session_id)
    if draft.status == "reset":
        raise _error(
            "ALERT_EVALUATION_STALE",
            "A reset draft is historical and cannot be evaluated again.",
            "Inspect its alert history or evaluate the replacement draft.",
            status_code=409,
        )
    configuration = _require_configuration(session, session_id)
    _require_revisions(draft, configuration, payload)
    latest = _latest_evaluation(session, configuration.id)
    _require_client_evaluation_revision(
        latest,
        payload.last_evaluation_draft_revision,
    )
    state = _build_state(session, draft, configuration)
    current_overall = state.current_pick.overall_pick if state.current_pick is not None else None
    if current_overall != payload.expected_current_overall_pick:
        raise _error(
            "ALERT_EVALUATION_STALE",
            (
                "The active draft coordinate changed before evaluation "
                f"(expected pick {payload.expected_current_overall_pick}, "
                f"current pick {current_overall})."
            ),
            "Refresh the draft and retry with the visible current pick.",
            status_code=409,
        )
    existing = session.scalar(
        select(DraftAlertEvaluationRow).where(
            DraftAlertEvaluationRow.configuration_id == configuration.id,
            DraftAlertEvaluationRow.input_fingerprint == state.fingerprint,
        )
    )
    if existing is not None:
        return DraftAlertEvaluationResponse(
            evaluation=_evaluation_read(existing, idempotent=True),
            alerts=_list_response(
                session,
                draft=draft,
                configuration=configuration,
                scope="current",
                limit=25,
                offset=0,
                idempotent_latest=True,
            ),
        )

    evaluated_at = utc_now_text()
    evaluated_datetime = datetime.fromisoformat(evaluated_at)
    desired = (
        _desired_events(
            session,
            state,
            evaluated_at=evaluated_datetime,
        )
        if configuration.enabled
        else ()
    )
    try:
        _lock_guards(
            session,
            draft=draft,
            configuration=configuration,
        )
        existing = session.scalar(
            select(DraftAlertEvaluationRow).where(
                DraftAlertEvaluationRow.configuration_id == configuration.id,
                DraftAlertEvaluationRow.input_fingerprint == state.fingerprint,
            )
        )
        if existing is not None:
            session.rollback()
            return DraftAlertEvaluationResponse(
                evaluation=_evaluation_read(existing, idempotent=True),
                alerts=_list_response(
                    session,
                    draft=draft,
                    configuration=configuration,
                    scope="current",
                    limit=25,
                    offset=0,
                    idempotent_latest=True,
                ),
            )
        opened = updated = superseded = 0
        if configuration.enabled:
            opened, updated, superseded = _reconcile_events(
                session,
                state,
                desired,
                now=evaluated_at,
            )
        limitation_codes = [f"{_CONFIG_REVISION_CODE_PREFIX}{configuration.revision}"]
        if not configuration.enabled:
            limitation_codes.append("ALERTS_DISABLED")
        evaluation = DraftAlertEvaluationRow(
            id=str(uuid4()),
            configuration_id=configuration.id,
            draft_revision=draft.revision,
            input_fingerprint=state.fingerprint,
            current_overall_pick=current_overall,
            next_user_pick=(
                state.next_user_pick.overall_pick if state.next_user_pick is not None else None
            ),
            candidate_count=(len(state.available_candidates) if configuration.enabled else 0),
            opened_count=opened,
            updated_count=updated,
            superseded_count=superseded,
            limitation_codes_json=_json(limitation_codes),
            evaluated_at=evaluated_at,
        )
        session.add(evaluation)
        _commit_transaction(session)
    except HubError:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        raise _error(
            "ALERT_EVALUATION_FAILED",
            "The alert evaluation could not be saved.",
            "Keep the saved draft and retry alert evaluation.",
            status_code=500,
        ) from exc
    return DraftAlertEvaluationResponse(
        evaluation=_evaluation_read(evaluation, idempotent=False),
        alerts=_list_response(
            session,
            draft=_require_draft(session, session_id),
            configuration=_require_configuration(session, session_id),
            scope="current",
            limit=25,
            offset=0,
        ),
    )


def list_draft_alerts(
    session: Session,
    *,
    session_id: str,
    scope: str,
    limit: int,
    offset: int,
) -> DraftAlertListResponse:
    draft = _require_draft(session, session_id)
    configuration = _require_configuration(session, session_id)
    return _list_response(
        session,
        draft=draft,
        configuration=configuration,
        scope=scope,
        limit=limit,
        offset=offset,
    )


def read_draft_alert(
    session: Session,
    *,
    session_id: str,
    alert_id: str,
) -> AlertDetailRead:
    draft = _require_draft(session, session_id)
    configuration = _require_configuration(session, session_id)
    row = session.get(DraftAlertEventRow, alert_id)
    if row is None or row.configuration_id != configuration.id:
        raise _error(
            "ALERT_EVENT_NOT_FOUND",
            "That alert event does not exist for this draft.",
            "Choose an event from the draft alert list.",
            status_code=404,
        )
    candidate = session.scalar(
        select(DraftCandidateRow).where(
            DraftCandidateRow.session_id == draft.id,
            DraftCandidateRow.player_id == row.player_id,
        )
    )
    if candidate is None:
        raise _error(
            "ALERT_EVENT_NOT_FOUND",
            "The alert's frozen player identity is unavailable.",
            "Inspect another event from the draft alert history.",
            status_code=404,
        )
    trade = session.scalar(
        select(DraftAlertTradeReferenceRow)
        .where(DraftAlertTradeReferenceRow.event_id == row.id)
        .order_by(
            DraftAlertTradeReferenceRow.created_at.desc(),
            DraftAlertTradeReferenceRow.id.desc(),
        )
        .limit(1)
    )
    trade_read = None
    if trade is not None:
        cost = _load_json(trade.cost_range_json)
        trade_read = AlertTradeReferenceRead(
            target_pick_window={
                "low": trade.target_overall_pick_low,
                "high": trade.target_overall_pick_high,
            },
            target_round_pick_labels=list(_load_json(trade.target_round_pick_labels_json)),
            incremental_cost=cost.get("incremental_cost"),
            pick_only_references=list(cost.get("pick_only_references", [])),
            cost_availability=cost.get(
                "cost_availability",
                "unavailable",
            ),
            explanation_template_key=trade.explanation_template_key,
            limitation_codes=list(_load_json(trade.limitation_codes_json)),
        )
    player = AlertPlayerRead(
        id=candidate.player_id,
        display_name=candidate.display_name,
        primary_position=candidate.primary_position,
        team=candidate.team,
    )
    return AlertDetailRead(
        player=player,
        event=_event_read(row),
        original_evidence=_load_json(row.original_evidence_json),
        current_evidence=_load_json(row.current_evidence_json),
        trade_reference=trade_read,
    )
