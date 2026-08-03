from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from friendly_hub.domains.alerts.configuration_service import (
    assess_snapshot_compatibility,
)
from friendly_hub.domains.alerts.engine import age_risk_freshness, elapsed_freshness
from friendly_hub.domains.alerts.models import (
    AlertEvidenceSnapshotRow,
    AlertPlayerSignalRow,
    DraftAlertConfigurationRow,
)
from friendly_hub.domains.drafts.models import DraftSessionRow
from friendly_hub.domains.reports.engine import (
    RosterPlayer,
    evaluate_evidence_coverage,
    render_explanation,
)

Freshness = Literal["fresh", "aging", "stale", "expired", "invalid"]

_FRESHNESS_ORDER = {
    "fresh": 0,
    "aging": 1,
    "stale": 2,
    "expired": 3,
    "invalid": 4,
}
_MARKET_FRESHNESS = (7, 21, 45)
_PRODUCTION_FRESHNESS = (14, 30, 60)


@dataclass(frozen=True)
class PlayerEvidence:
    player_id: str
    market_band: str | None
    production_band: str | None
    age_risk_band: str | None
    expected_pick_low: int | None
    expected_pick_high: int | None
    field_timestamps: dict[str, str]
    field_freshness: dict[str, Freshness]
    limitation_codes: tuple[str, ...]

    def safe_document(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "market_band": self.market_band,
            "win_now_production_band": self.production_band,
            "age_risk_band": self.age_risk_band,
            "expected_pick": (
                {"low": self.expected_pick_low, "high": self.expected_pick_high}
                if self.expected_pick_low is not None
                and self.expected_pick_high is not None
                else None
            ),
            "field_timestamps": dict(sorted(self.field_timestamps.items())),
            "field_freshness": dict(sorted(self.field_freshness.items())),
            "limitation_codes": list(self.limitation_codes),
        }


@dataclass(frozen=True)
class EvidenceContext:
    configuration_id: str
    configuration_revision: int
    configuration_enabled: bool
    alert_engine_version: str
    alert_rule_version: str
    freshness_policy_version: str
    snapshot_id: str
    snapshot_content_hash: str
    snapshot_status: str
    source_label: str
    source_as_of: str
    compatibility: str
    compatibility_reasons: tuple[str, ...]
    signals: tuple[PlayerEvidence, ...]
    invalid: bool

    def fingerprint_document(self) -> dict[str, Any]:
        return {
            "evidence_enrichment_version": "phase6-evidence-enrichment-v1",
            "attached": True,
            "configuration": {
                "id": self.configuration_id,
                "revision": self.configuration_revision,
                "enabled": self.configuration_enabled,
                "alert_engine_version": self.alert_engine_version,
                "alert_rule_version": self.alert_rule_version,
                "freshness_policy_version": self.freshness_policy_version,
            },
            "snapshot": {
                "id": self.snapshot_id,
                "content_hash": self.snapshot_content_hash,
                "status": self.snapshot_status,
                "source_label": self.source_label,
                "source_as_of": self.source_as_of,
                "format_compatibility": self.compatibility,
                "compatibility_reasons": list(self.compatibility_reasons),
            },
            "roster_signals": [signal.safe_document() for signal in self.signals],
            "invalid": self.invalid,
        }

    def safe_player_evidence(self, player_id: str) -> dict[str, Any]:
        signal = next(
            (candidate for candidate in self.signals if candidate.player_id == player_id),
            None,
        )
        return signal.safe_document() if signal is not None else {}

    def safe_provenance(self, freshness: str) -> dict[str, Any]:
        return {
            "source_label": self.source_label,
            "source_as_of": self.source_as_of,
            "format_compatibility": self.compatibility,
            "compatibility_reasons": list(self.compatibility_reasons),
            "freshness_at_completion": freshness,
            "freshness_policy_version": self.freshness_policy_version,
        }


@dataclass(frozen=True)
class EvidenceSectionResult:
    section_key: str
    availability: str
    confidence: str
    metrics: dict[str, Any]
    reason_codes: tuple[str, ...]
    limitation_codes: tuple[str, ...]
    explanation_template_key: str
    explanation: str
    safe_provenance: dict[str, Any]


def no_evidence_fingerprint_document() -> dict[str, Any]:
    return {
        "evidence_enrichment_version": "phase6-evidence-enrichment-v1",
        "attached": False,
    }


def _parse_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _parse_object(value: str) -> tuple[dict[str, Any], bool]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}, True
    if not isinstance(parsed, dict):
        return {}, True
    return parsed, False


def _parse_codes(value: str) -> tuple[tuple[str, ...], bool]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return (), True
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        return (), True
    return tuple(sorted(set(parsed))), False


def _elapsed_freshness(
    timestamp: str | None,
    completed_at: datetime,
    thresholds: tuple[int, int, int],
) -> Freshness:
    parsed = _parse_utc(timestamp or "")
    if parsed is None:
        return "invalid"
    return elapsed_freshness(
        evidence_as_of=parsed,
        evaluated_at=completed_at,
        fresh_through_days=thresholds[0],
        aging_through_days=thresholds[1],
        stale_through_days=thresholds[2],
    )


def _age_freshness(
    timestamp: str | None,
    completed_at: datetime,
    limitations: tuple[str, ...],
) -> Freshness:
    parsed = _parse_utc(timestamp or "")
    if parsed is None or parsed > completed_at:
        return "invalid"
    if any(code.endswith("SOURCE_CONFLICT") for code in limitations):
        return age_risk_freshness("source_conflict")
    return age_risk_freshness("valid")


def _player_evidence(
    row: AlertPlayerSignalRow,
    completed_at: datetime,
) -> tuple[PlayerEvidence, bool]:
    timestamps, timestamps_invalid = _parse_object(row.field_timestamps_json)
    limitations, limitations_invalid = _parse_codes(row.limitation_codes_json)
    normalized_timestamps = {
        key: value
        for key, value in timestamps.items()
        if isinstance(key, str) and isinstance(value, str)
    }
    field_freshness: dict[str, Freshness] = {}
    if row.market_band is not None:
        field_freshness["market_band"] = _elapsed_freshness(
            normalized_timestamps.get("market_band"),
            completed_at,
            _MARKET_FRESHNESS,
        )
    if row.win_now_production_band is not None:
        field_freshness["win_now_production_band"] = _elapsed_freshness(
            normalized_timestamps.get("win_now_production_band"),
            completed_at,
            _PRODUCTION_FRESHNESS,
        )
    if row.age_risk_band is not None:
        field_freshness["age_risk_band"] = _age_freshness(
            normalized_timestamps.get("age_risk_band"),
            completed_at,
            limitations,
        )
    if row.expected_pick_low is not None and row.expected_pick_high is not None:
        field_freshness["expected_pick"] = _elapsed_freshness(
            normalized_timestamps.get("expected_pick"),
            completed_at,
            _MARKET_FRESHNESS,
        )
    return (
        PlayerEvidence(
            player_id=row.player_id,
            market_band=row.market_band,
            production_band=row.win_now_production_band,
            age_risk_band=row.age_risk_band,
            expected_pick_low=row.expected_pick_low,
            expected_pick_high=row.expected_pick_high,
            field_timestamps=dict(sorted(normalized_timestamps.items())),
            field_freshness=dict(sorted(field_freshness.items())),
            limitation_codes=limitations,
        ),
        timestamps_invalid or limitations_invalid,
    )


def load_evidence_context(
    session: Session,
    *,
    draft: DraftSessionRow,
    roster: tuple[RosterPlayer, ...],
    completed_at: datetime,
) -> EvidenceContext | None:
    configuration = session.scalar(
        select(DraftAlertConfigurationRow).where(
            DraftAlertConfigurationRow.draft_session_id == draft.id
        )
    )
    if configuration is None:
        return None
    snapshot = session.get(AlertEvidenceSnapshotRow, configuration.evidence_snapshot_id)
    if snapshot is None:
        return EvidenceContext(
            configuration_id=configuration.id,
            configuration_revision=configuration.revision,
            configuration_enabled=configuration.enabled,
            alert_engine_version=configuration.engine_version,
            alert_rule_version=configuration.rule_version,
            freshness_policy_version=configuration.freshness_policy_version,
            snapshot_id=configuration.evidence_snapshot_id,
            snapshot_content_hash="",
            snapshot_status="missing",
            source_label="Unavailable local evidence",
            source_as_of="",
            compatibility="unknown",
            compatibility_reasons=("EVIDENCE_SNAPSHOT_MISSING",),
            signals=(),
            invalid=True,
        )

    assessment = assess_snapshot_compatibility(
        session,
        draft=draft,
        snapshot=snapshot,
    )
    roster_ids = {player.canonical_player_id for player in roster}
    rows = tuple(
        session.scalars(
            select(AlertPlayerSignalRow)
            .where(
                AlertPlayerSignalRow.evidence_snapshot_id == snapshot.id,
                AlertPlayerSignalRow.player_id.in_(roster_ids),
            )
            .order_by(AlertPlayerSignalRow.player_id)
        )
    )
    signals: list[PlayerEvidence] = []
    snapshot_as_of = _parse_utc(snapshot.source_as_of)
    invalid = (
        snapshot.status == "invalidated"
        or snapshot_as_of is None
        or snapshot_as_of > completed_at
    )
    configuration_updated = _parse_utc(configuration.updated_at)
    if configuration_updated is None or configuration_updated > completed_at:
        invalid = True
    for row in rows:
        signal, signal_invalid = _player_evidence(row, completed_at)
        signals.append(signal)
        invalid = invalid or signal_invalid
    return EvidenceContext(
        configuration_id=configuration.id,
        configuration_revision=configuration.revision,
        configuration_enabled=configuration.enabled,
        alert_engine_version=configuration.engine_version,
        alert_rule_version=configuration.rule_version,
        freshness_policy_version=configuration.freshness_policy_version,
        snapshot_id=snapshot.id,
        snapshot_content_hash=snapshot.content_hash,
        snapshot_status=snapshot.status,
        source_label=snapshot.source_label,
        source_as_of=snapshot.source_as_of,
        compatibility=assessment.state,
        compatibility_reasons=assessment.reasons,
        signals=tuple(signals),
        invalid=invalid,
    )


def _worst_freshness(states: list[Freshness]) -> str:
    if not states:
        return "unavailable"
    return max(states, key=_FRESHNESS_ORDER.__getitem__)


def _usable(freshness: Freshness | None) -> bool:
    return freshness in {"fresh", "aging", "stale"}


def _confidence(
    baseline: str,
    *,
    compatibility: str,
    freshness: str,
) -> str:
    if baseline == "unavailable":
        return "unavailable"
    if baseline == "low" or compatibility == "partial" or freshness == "stale":
        return "low"
    return "medium"


def _reason(prefix: str, availability: str) -> str:
    suffix = {
        "supported": "AVAILABLE",
        "limited": "LIMITED",
        "unavailable": "UNAVAILABLE",
    }[availability]
    return f"{prefix}_EVIDENCE_{suffix}"


def _section_limitations(
    *,
    base: tuple[str, ...],
    context: EvidenceContext | None,
    freshness_counts: Counter[Freshness],
    signal_limitations: set[str],
    availability: str,
) -> tuple[str, ...]:
    limitations = set(base) | signal_limitations
    if context is None:
        limitations.add("EVIDENCE_SNAPSHOT_NOT_ATTACHED")
    else:
        limitations.update(context.compatibility_reasons)
        if context.compatibility == "family":
            limitations.add("FORMAT_FAMILY")
        elif context.compatibility == "partial":
            limitations.add("FORMAT_PARTIAL")
        elif context.compatibility in {"incompatible", "unknown"}:
            limitations.add(f"FORMAT_{context.compatibility.upper()}")
        if context.invalid:
            limitations.add("EVIDENCE_CONTEXT_INVALID")
    for state in ("aging", "stale", "expired", "invalid"):
        if freshness_counts[state]:
            limitations.add(f"FRESHNESS_{state.upper()}")
    if availability == "unavailable" and context is not None:
        limitations.add("EVIDENCE_COVERAGE_BELOW_MINIMUM")
    return tuple(sorted(limitations))


def _empty_section(
    *,
    section_key: str,
    prefix: str,
    template_key: str,
    roster_count: int,
    base_limitations: tuple[str, ...],
) -> EvidenceSectionResult:
    return EvidenceSectionResult(
        section_key=section_key,
        availability="unavailable",
        confidence="unavailable",
        metrics={
            "roster_players": roster_count,
            "covered_players": 0,
            "uncovered_players": roster_count,
            "coverage_basis_points": 0,
            "band_distribution": {},
            "freshness_counts": {},
        },
        reason_codes=(_reason(prefix, "unavailable"),),
        limitation_codes=tuple(
            sorted(set(base_limitations) | {"EVIDENCE_SNAPSHOT_NOT_ATTACHED"})
        ),
        explanation_template_key=template_key,
        explanation=render_explanation(template_key=template_key, values={}),
        safe_provenance={},
    )


def _categorical_section(
    *,
    context: EvidenceContext,
    roster: tuple[RosterPlayer, ...],
    section_key: str,
    prefix: str,
    field_name: str,
    freshness_key: str,
    template_family: str,
    base_limitations: tuple[str, ...],
) -> EvidenceSectionResult:
    signal_by_player = {signal.player_id: signal for signal in context.signals}
    band_counts: Counter[str] = Counter()
    freshness_counts: Counter[Freshness] = Counter()
    signal_limitations: set[str] = set()
    covered = 0
    for player in roster:
        signal = signal_by_player.get(player.canonical_player_id)
        if signal is None:
            continue
        value = getattr(signal, field_name)
        if value is None:
            continue
        freshness = signal.field_freshness.get(freshness_key)
        if freshness is not None:
            freshness_counts[freshness] += 1
        signal_limitations.update(signal.limitation_codes)
        if _usable(freshness):
            covered += 1
            band_counts[value] += 1

    evidence_state: Literal["usable", "invalid", "incompatible"] = "usable"
    if context.invalid:
        evidence_state = "invalid"
        covered = 0
        band_counts.clear()
    elif context.compatibility in {"incompatible", "unknown"}:
        evidence_state = "incompatible"
        covered = 0
        band_counts.clear()
    coverage = evaluate_evidence_coverage(
        covered_players=covered,
        roster_players=len(roster),
        evidence_state=evidence_state,
    )
    usable_freshness = [state for state in freshness_counts if _usable(state)]
    worst_freshness = _worst_freshness(
        usable_freshness if usable_freshness else list(freshness_counts)
    )
    if context.invalid:
        worst_freshness = "invalid"
    confidence = _confidence(
        coverage.confidence,
        compatibility=context.compatibility,
        freshness=worst_freshness,
    )
    availability = coverage.availability
    template_suffix = {
        "supported": "supported",
        "limited": "limited",
        "unavailable": "unavailable",
    }[availability]
    template_key = f"{template_family}.{template_suffix}"
    values = (
        {"covered_players": covered, "roster_players": len(roster)}
        if availability in {"supported", "limited"}
        else {}
    )
    return EvidenceSectionResult(
        section_key=section_key,
        availability=availability,
        confidence=confidence,
        metrics={
            "roster_players": len(roster),
            "covered_players": covered,
            "uncovered_players": len(roster) - covered,
            "coverage_basis_points": coverage.coverage_basis_points,
            "band_distribution": dict(sorted(band_counts.items())),
            "freshness_counts": dict(sorted(freshness_counts.items())),
        },
        reason_codes=(_reason(prefix, availability),),
        limitation_codes=_section_limitations(
            base=base_limitations,
            context=context,
            freshness_counts=freshness_counts,
            signal_limitations=signal_limitations,
            availability=availability,
        ),
        explanation_template_key=template_key,
        explanation=render_explanation(template_key=template_key, values=values),
        safe_provenance=context.safe_provenance(worst_freshness),
    )


def build_evidence_sections(
    context: EvidenceContext | None,
    roster: tuple[RosterPlayer, ...],
) -> tuple[EvidenceSectionResult, ...]:
    specs = (
        (
            "year_one_production_context",
            "PRODUCTION",
            "production_band",
            "win_now_production_band",
            "production",
            ("CATEGORICAL_SINGLE_SOURCE", "NOT_A_PROJECTION"),
        ),
        (
            "dynasty_market_context",
            "MARKET",
            "market_band",
            "market_band",
            "market",
            ("CATEGORICAL_SINGLE_SOURCE", "NOT_A_ROSTER_VALUE"),
        ),
        (
            "age_risk_profile",
            "AGE_RISK",
            "age_risk_band",
            "age_risk_band",
            "age_risk",
            ("CATEGORICAL_SINGLE_SOURCE", "NOT_AN_AVERAGE_AGE"),
        ),
    )
    results: list[EvidenceSectionResult] = []
    for section_key, prefix, field_name, freshness_key, family, limitations in specs:
        if context is None:
            results.append(
                _empty_section(
                    section_key=section_key,
                    prefix=prefix,
                    template_key=f"{family}.unavailable",
                    roster_count=len(roster),
                    base_limitations=limitations,
                )
            )
        else:
            results.append(
                _categorical_section(
                    context=context,
                    roster=roster,
                    section_key=section_key,
                    prefix=prefix,
                    field_name=field_name,
                    freshness_key=freshness_key,
                    template_family=family,
                    base_limitations=limitations,
                )
            )

    market = results[1]
    if (
        context is not None
        and not context.invalid
        and context.compatibility in {"exact", "family", "partial"}
    ):
        signal_by_player = {signal.player_id: signal for signal in context.signals}
        comparisons: list[dict[str, Any]] = []
        for player in roster:
            signal = signal_by_player.get(player.canonical_player_id)
            if (
                signal is None
                or signal.market_band is None
                or not _usable(signal.field_freshness.get("market_band"))
                or signal.expected_pick_low is None
                or signal.expected_pick_high is None
                or not _usable(signal.field_freshness.get("expected_pick"))
            ):
                continue
            if player.overall_pick < signal.expected_pick_low:
                selection_context = "before_expected_window"
            elif player.overall_pick > signal.expected_pick_high:
                selection_context = "after_expected_window"
            else:
                selection_context = "within_expected_window"
            comparisons.append(
                {
                    "player_id": player.canonical_player_id,
                    "actual_overall_pick": player.overall_pick,
                    "expected_pick_low": signal.expected_pick_low,
                    "expected_pick_high": signal.expected_pick_high,
                    "selection_context": selection_context,
                }
            )
        market_metrics = {**market.metrics, "expected_selection_context": comparisons}
        results[1] = replace(market, metrics=market_metrics)
    else:
        results[1] = replace(
            market,
            metrics={**market.metrics, "expected_selection_context": []},
        )
    return tuple(results)
