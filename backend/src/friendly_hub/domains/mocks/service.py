from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from friendly_hub.core.errors import HubError
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.drafts.models import (
    DraftCandidateRow,
    DraftPickRevisionRow,
    DraftPickRow,
    DraftSessionRow,
)
from friendly_hub.domains.drafts.schemas import DraftSessionCreate
from friendly_hub.domains.drafts.service import (
    create_session_in_transaction,
    read_session,
    record_pick_in_transaction,
)
from friendly_hub.domains.leagues.models import LeagueProfileRow
from friendly_hub.domains.leagues.schemas import LeagueProfileDocument
from friendly_hub.domains.mocks.definitions import (
    MARKET_BOARD_ENGINE_VERSION,
    PRACTICE_BOARD_ENGINE_VERSION,
    RNG_VERSION,
    STRATEGY_DEFINITION_VERSION,
    SUPPORTED_CPU_ENGINE_VERSIONS,
)
from friendly_hub.domains.mocks.engine import (
    CandidateInput,
    CandidateScoreInput,
    ScoredCandidate,
    build_consideration_set,
    content_fingerprint,
    effective_randomness,
    emphasized_position,
    fallback_archetype_for_slot,
    roster_score_components,
    score_candidates,
    select_candidate,
)
from friendly_hub.domains.mocks.market import load_market_snapshot
from friendly_hub.domains.mocks.models import (
    MockConfigurationRow,
    MockCpuProfileRow,
    MockGuidanceEventRow,
    MockPickDecisionRow,
    MockStrategyRevisionRow,
)
from friendly_hub.domains.mocks.schemas import (
    MockConfigurationRead,
    MockCpuPickCreate,
    MockCpuProfileRead,
    MockDecisionAlternativeRead,
    MockGuidanceRead,
    MockMarketBaselineRead,
    MockPickDecisionAudit,
    MockPickDecisionSummary,
    MockScoreComponentsRead,
    MockSessionCreate,
    MockSessionRead,
    MockStrategyRevisionRead,
)
from friendly_hub.domains.mocks.strategy import (
    evaluate_strategy,
    explanation_text,
    pivot_text,
    user_roster_counts,
)


def _error(code: str, message: str, action: str, status_code: int) -> HubError:
    return HubError(
        code=code,
        message=message,
        action=action,
        status_code=status_code,
    )


def _json(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _normalized_positions(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(
        {
            item.strip().upper()
            for item in value
            if isinstance(item, str) and item.strip()
        }
    )


def _normalize_league_shape(
    league_row: LeagueProfileRow | None,
    *,
    team_count: int,
) -> tuple[dict[str, object], str | None]:
    if league_row is None:
        return (
            {
                "schema_version": 1,
                "source": "draft_configuration",
                "team_count": team_count,
                "league_type": "unknown",
                "starter_slots": [],
                "bench_slots": None,
                "taxi_slots": None,
                "injured_reserve_slots": None,
                "superflex": False,
                "qb_eligible_starter_slots": 0,
                "tight_end_premium": False,
                "limitations": ["LEAGUE_SHAPE_UNAVAILABLE"],
            },
            None,
        )

    document = LeagueProfileDocument.model_validate_json(league_row.payload_json)
    raw_starters = document.roster.get("starters", [])
    starter_slots: list[dict[str, object]] = []
    if isinstance(raw_starters, list):
        for raw_slot in raw_starters:
            if not isinstance(raw_slot, dict):
                continue
            slot = raw_slot.get("slot")
            if not isinstance(slot, str) or not slot.strip():
                continue
            starter_slots.append(
                {
                    "slot": slot.strip().upper(),
                    "eligible_positions": _normalized_positions(
                        raw_slot.get("eligible_positions")
                    ),
                }
            )

    qb_eligible_slots = sum(
        1 for slot in starter_slots if "QB" in slot["eligible_positions"]
    )
    superflex = any(
        slot["slot"] in {"SUPER_FLEX", "SUPERFLEX", "SF"}
        or (
            "QB" in slot["eligible_positions"]
            and len(slot["eligible_positions"]) > 1
        )
        for slot in starter_slots
    )
    tight_end_premium = False
    raw_rules = document.scoring.get("rules", [])
    if isinstance(raw_rules, list):
        for rule in raw_rules:
            if not isinstance(rule, dict):
                continue
            position_scope = _normalized_positions(rule.get("position_scope"))
            points = rule.get("points")
            normalized_stat = rule.get("normalized_stat")
            if (
                "TE" in position_scope
                and isinstance(points, int | float)
                and not isinstance(points, bool)
                and points > 0
                and normalized_stat in {"reception", "receiving_first_down"}
            ):
                tight_end_premium = True
                break

    limitations: list[str] = []
    if document.league.team_count != team_count:
        limitations.append("LEAGUE_TEAM_COUNT_DIFFERS")
    return (
        {
            "schema_version": 1,
            "source": "league_profile",
            "team_count": team_count,
            "league_type": document.league.league_type,
            "starter_slots": starter_slots,
            "bench_slots": document.roster.get("bench_slots"),
            "taxi_slots": document.roster.get("taxi_slots"),
            "injured_reserve_slots": document.roster.get("injured_reserve_slots"),
            "superflex": superflex,
            "qb_eligible_starter_slots": qb_eligible_slots,
            "tight_end_premium": tight_end_premium,
            "limitations": limitations,
        },
        document.provenance.source_as_of or league_row.imported_at,
    )


def _strategy_limitations(
    strategy_key: str,
    league_shape: dict[str, object],
) -> list[str]:
    limitations = list(league_shape.get("limitations", []))
    if strategy_key in {"win_now", "productive_struggle"}:
        limitations.append("TIMELINE_EVIDENCE_UNAVAILABLE")
    return sorted(set(limitations))


def _validate_strategy_compatibility(
    strategy_key: str,
    league_shape: dict[str, object],
) -> None:
    if strategy_key != "early_qb_superflex":
        return
    superflex = league_shape.get("superflex") is True
    qb_slots = league_shape.get("qb_eligible_starter_slots")
    if not superflex and (not isinstance(qb_slots, int) or qb_slots < 2):
        raise _error(
            "MOCK.STRATEGY_INCOMPATIBLE",
            "Early-QB superflex requires a superflex or two-QB league shape.",
            "Choose another strategy or attach a compatible local league profile.",
            409,
        )


_POSITION_FALLBACK_ORDER = {"QB": 0, "WR": 1, "RB": 2, "TE": 3}


def _ordered_candidate_rows(
    session: Session,
    draft_session_id: str,
    cpu_engine_version: str = PRACTICE_BOARD_ENGINE_VERSION,
) -> list[DraftCandidateRow]:
    rows = list(
        session.scalars(
            select(DraftCandidateRow).where(
                DraftCandidateRow.session_id == draft_session_id
            )
        )
    )
    if cpu_engine_version == MARKET_BOARD_ENGINE_VERSION:
        return sorted(
            rows,
            key=lambda row: (
                row.market_rank is None,
                row.market_rank if row.market_rank is not None else 0,
                row.manual_rank is None,
                row.manual_rank if row.manual_rank is not None else 0,
                _POSITION_FALLBACK_ORDER.get(row.primary_position, 9),
                not row.is_rookie,
                -(row.rookie_class or 0),
                row.search_name,
                row.player_id,
            ),
        )
    return sorted(
        rows,
        key=lambda row: (
            row.manual_rank is None,
            row.manual_rank if row.manual_rank is not None else 0,
            row.search_name,
            row.player_id,
        ),
    )


def _candidate_snapshot(
    session: Session,
    draft_session_id: str,
    cpu_engine_version: str,
) -> list[dict[str, object]]:
    ordered = _ordered_candidate_rows(
        session,
        draft_session_id,
        cpu_engine_version,
    )
    return [
        {
            "practice_index": index,
            "player_id": row.player_id,
            "primary_position": row.primary_position,
            "fantasy_positions": json.loads(row.fantasy_positions_json),
            "player_status": row.player_status,
            "is_rookie": row.is_rookie,
            "rookie_class": row.rookie_class,
            "snapshot_source": row.snapshot_source,
            "manual_rank": row.manual_rank,
            "market_rank": row.market_rank,
            "tier_order": row.tier_order,
        }
        for index, row in enumerate(ordered)
    ]


def _practice_board_baseline(
    candidate_count: int,
    limitation: str,
) -> dict[str, object]:
    return {
        "label": "Personal Board practice fallback",
        "evidence_kind": "personal_board_fallback",
        "source_name": None,
        "source_url": None,
        "rank_type": "personal_board_order",
        "format": "practice_only",
        "source_as_of": None,
        "player_count": 0,
        "matched_candidate_count": 0,
        "candidate_count": candidate_count,
        "coverage_percent": 0,
        "confidence": "unavailable",
        "limitations": [limitation, "NOT_MARKET_EVIDENCE"],
    }


def _apply_market_baseline(
    session: Session,
    draft_session_id: str,
    market_snapshot_path: Path | None,
) -> tuple[dict[str, object], str]:
    rows = list(
        session.scalars(
            select(DraftCandidateRow).where(
                DraftCandidateRow.session_id == draft_session_id
            )
        )
    )
    try:
        snapshot = load_market_snapshot(market_snapshot_path)
    except RuntimeError:
        return (
            _practice_board_baseline(len(rows), "MARKET_BASELINE_INVALID"),
            PRACTICE_BOARD_ENGINE_VERSION,
        )
    if snapshot is None:
        return (
            _practice_board_baseline(len(rows), "MARKET_BASELINE_UNAVAILABLE"),
            PRACTICE_BOARD_ENGINE_VERSION,
        )

    by_identity = {
        (entry.search_name, entry.position): entry for entry in snapshot.entries
    }
    matched_count = 0
    for row in rows:
        entry = by_identity.get((row.search_name, row.primary_position))
        row.market_rank = entry.market_rank if entry is not None else None
        if entry is not None:
            matched_count += 1
    if matched_count < 2:
        for row in rows:
            row.market_rank = None
        return (
            _practice_board_baseline(len(rows), "MARKET_BASELINE_COVERAGE_INSUFFICIENT"),
            PRACTICE_BOARD_ENGINE_VERSION,
        )

    limitations = list(snapshot.limitations)
    if matched_count < len(rows):
        limitations.append("UNMATCHED_CANDIDATES_USE_FALLBACK")
    return (
        {
            "label": snapshot.label,
            "evidence_kind": snapshot.evidence_kind,
            "source_name": snapshot.source_name,
            "source_url": snapshot.source_url,
            "rank_type": snapshot.rank_type,
            "format": snapshot.format,
            "source_as_of": snapshot.source_as_of,
            "player_count": snapshot.player_count,
            "matched_candidate_count": matched_count,
            "candidate_count": len(rows),
            "coverage_percent": round(matched_count * 100 / len(rows)),
            "confidence": "medium",
            "limitations": sorted(set(limitations)),
        },
        MARKET_BOARD_ENGINE_VERSION,
    )


def _copy_market_baseline(
    session: Session,
    draft_session_id: str,
    source_configuration: MockConfigurationRow,
) -> tuple[dict[str, object], str]:
    source_rows = list(
        session.scalars(
            select(DraftCandidateRow).where(
                DraftCandidateRow.session_id == source_configuration.draft_session_id
            )
        )
    )
    ranks = {row.player_id: row.market_rank for row in source_rows}
    for row in session.scalars(
        select(DraftCandidateRow).where(
            DraftCandidateRow.session_id == draft_session_id
        )
    ):
        row.market_rank = ranks.get(row.player_id)
    if source_configuration.market_baseline_json:
        baseline = json.loads(source_configuration.market_baseline_json)
    else:
        baseline = _practice_board_baseline(
            len(source_rows),
            "LEGACY_PRACTICE_BOARD_ENGINE",
        )
    return baseline, source_configuration.cpu_engine_version


def _draft_order_snapshot(
    session: Session,
    draft_session_id: str,
) -> list[dict[str, int]]:
    rows = list(
        session.scalars(
            select(DraftPickRow)
            .where(DraftPickRow.session_id == draft_session_id)
            .order_by(DraftPickRow.overall_pick)
        )
    )
    return [
        {
            "overall_pick": row.overall_pick,
            "round_number": row.round_number,
            "pick_in_round": row.pick_in_round,
            "selecting_slot": row.selecting_slot,
        }
        for row in rows
    ]


def _profile_snapshot(
    payload: MockSessionCreate,
    cpu_engine_version: str,
) -> list[dict[str, object]]:
    return [
        {
            "draft_slot": slot,
            "source": "fallback",
            "archetype_key": payload.fallback_archetypes.get(
                slot,
                fallback_archetype_for_slot(
                    payload.seed,
                    slot,
                    cpu_engine_version,
                ),
            ),
            "confidence": "not_applicable",
            "draft_sample_count": 0,
            "pick_sample_count": 0,
        }
        for slot in range(1, payload.team_count + 1)
        if slot != payload.user_slot
    ]


def _copied_profile_snapshot(
    session: Session,
    configuration: MockConfigurationRow,
) -> list[dict[str, object]]:
    rows = session.scalars(
        select(MockCpuProfileRow)
        .where(MockCpuProfileRow.mock_configuration_id == configuration.id)
        .order_by(MockCpuProfileRow.draft_slot)
    )
    return [
        {
            "draft_slot": row.draft_slot,
            "source": row.source,
            "archetype_key": row.archetype_key,
            "confidence": row.confidence,
            "draft_sample_count": row.draft_sample_count,
            "pick_sample_count": row.pick_sample_count,
            "tendency_snapshot_json": row.tendency_snapshot_json,
            "internal_manager_reference": row.internal_manager_reference,
            "source_timestamp": row.source_timestamp,
        }
        for row in rows
    ]


def _profile_fingerprint_snapshot(
    profile_snapshot: list[dict[str, object]],
) -> list[dict[str, object]]:
    keys = (
        "draft_slot",
        "source",
        "archetype_key",
        "confidence",
        "draft_sample_count",
        "pick_sample_count",
    )
    return [
        {key: profile[key] for key in keys}
        for profile in profile_snapshot
    ]


def _add_mock_rows(
    session: Session,
    draft_row: DraftSessionRow,
    payload: MockSessionCreate,
    *,
    copy_from_configuration: MockConfigurationRow | None = None,
    market_snapshot_path: Path | None = None,
) -> MockConfigurationRow:
    if copy_from_configuration is None:
        league_row = (
            session.get(LeagueProfileRow, payload.league_profile_id)
            if payload.league_profile_id
            else None
        )
        league_shape, league_shape_source_timestamp = _normalize_league_shape(
            league_row,
            team_count=payload.team_count,
        )
        market_baseline, cpu_engine_version = _apply_market_baseline(
            session,
            draft_row.id,
            market_snapshot_path,
        )
        profile_snapshot = _profile_snapshot(payload, cpu_engine_version)
        rng_version = RNG_VERSION
        strategy_definition_version = STRATEGY_DEFINITION_VERSION
    else:
        league_shape = json.loads(copy_from_configuration.league_shape_json)
        league_shape_source_timestamp = (
            copy_from_configuration.league_shape_source_timestamp
        )
        profile_snapshot = _copied_profile_snapshot(
            session,
            copy_from_configuration,
        )
        rng_version = copy_from_configuration.rng_version
        market_baseline, cpu_engine_version = _copy_market_baseline(
            session,
            draft_row.id,
            copy_from_configuration,
        )
        strategy_definition_version = (
            copy_from_configuration.strategy_definition_version
        )
    candidate_snapshot = _candidate_snapshot(
        session,
        draft_row.id,
        cpu_engine_version,
    )
    if len(candidate_snapshot) < 2:
        raise _error(
            "MOCK.CANDIDATES_INSUFFICIENT",
            "A mock draft needs at least two frozen candidates.",
            "Add or import more relevant players, then create the mock again.",
            409,
        )
    _validate_strategy_compatibility(payload.strategy_key, league_shape)
    fingerprint = content_fingerprint(
        {
            "candidates": candidate_snapshot,
            "draft_order": _draft_order_snapshot(session, draft_row.id),
            "league_shape": league_shape,
            "profiles": _profile_fingerprint_snapshot(profile_snapshot),
            "market_baseline": market_baseline,
        }
    )
    now = utc_now_text()
    configuration = MockConfigurationRow(
        id=str(uuid4()),
        draft_session_id=draft_row.id,
        seed=payload.seed,
        rng_version=rng_version,
        cpu_engine_version=cpu_engine_version,
        strategy_definition_version=strategy_definition_version,
        league_shape_json=_json(league_shape),
        league_shape_source_timestamp=league_shape_source_timestamp,
        market_baseline_json=_json(market_baseline),
        content_fingerprint=fingerprint,
        randomness=payload.randomness,
        current_strategy_key=payload.strategy_key,
        revision=0,
        include_in_learning=payload.include_in_learning,
        learning_opted_in_at=now if payload.include_in_learning else None,
        learning_withdrawn_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(configuration)
    session.flush()
    strategy_revision = MockStrategyRevisionRow(
        id=str(uuid4()),
        mock_configuration_id=configuration.id,
        sequence_number=1,
        previous_strategy_key=None,
        next_strategy_key=payload.strategy_key,
        effective_overall_pick=1,
        user_roster_counts_json="{}",
        private_user_note=None,
        created_at=now,
    )
    session.add(strategy_revision)
    session.flush()
    for profile in profile_snapshot:
        session.add(
            MockCpuProfileRow(
                id=str(uuid4()),
                mock_configuration_id=configuration.id,
                draft_slot=profile["draft_slot"],
                source=profile["source"],
                archetype_key=profile["archetype_key"],
                confidence=profile["confidence"],
                draft_sample_count=profile["draft_sample_count"],
                pick_sample_count=profile["pick_sample_count"],
                tendency_snapshot_json=str(
                    profile.get("tendency_snapshot_json")
                    or _json(
                        {
                            "archetype_key": profile["archetype_key"],
                            "source": profile["source"],
                        }
                    )
                ),
                internal_manager_reference=profile.get(
                    "internal_manager_reference"
                ),
                source_timestamp=str(profile.get("source_timestamp") or now),
                created_at=now,
            )
        )

    evaluation = evaluate_strategy(
        strategy_key=payload.strategy_key,
        round_count=payload.round_count,
        team_count=payload.team_count,
        effective_overall_pick=1,
        roster=(),
        league_shape=league_shape,
    )
    guidance = MockGuidanceEventRow(
        id=str(uuid4()),
        mock_configuration_id=configuration.id,
        strategy_revision_id=strategy_revision.id,
        deterministic_event_key=(
            f"{strategy_definition_version}:{payload.strategy_key}:initial:1"
        ),
        effective_overall_pick=1,
        state=evaluation.state,
        confidence=evaluation.confidence,
        observed_counts_json=_json(evaluation.observed_counts),
        target_ranges_json=_json(evaluation.target_ranges),
        reason_codes_json=_json(evaluation.reason_codes),
        limitation_codes_json=_json(evaluation.limitation_codes),
        explanation_template_key=evaluation.explanation_template_key,
        pivot_template_key=evaluation.pivot_template_key,
        status="open",
        created_at=now,
        resolved_at=None,
    )
    session.add(guidance)
    session.flush()
    return configuration


def create_mock_session(
    session: Session,
    board_id: str,
    payload: MockSessionCreate,
    market_snapshot_path: Path | None = None,
) -> MockSessionRead:
    draft_payload = DraftSessionCreate(
        name=payload.name,
        mode="mock",
        league_profile_id=payload.league_profile_id,
        draft_format=payload.draft_format,
        third_round_reversal=payload.third_round_reversal,
        team_count=payload.team_count,
        round_count=payload.round_count,
        user_slot=payload.user_slot,
        pick_timer_seconds=payload.pick_timer_seconds,
        team_names=payload.team_names,
    )
    try:
        draft_row = create_session_in_transaction(session, board_id, draft_payload)
        _add_mock_rows(
            session,
            draft_row,
            payload,
            market_snapshot_path=market_snapshot_path,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return read_mock_session(session, draft_row.id)


def _require_cpu_mock(
    session: Session,
    session_id: str,
) -> tuple[DraftSessionRow, MockConfigurationRow]:
    draft_row = session.get(DraftSessionRow, session_id)
    if draft_row is None:
        raise _error(
            "MOCK.NOT_FOUND",
            "That mock session could not be found.",
            "Return to the Personal Board and choose an available mock.",
            404,
        )
    if draft_row.mode != "mock":
        raise _error(
            "MOCK.LIVE_SESSION",
            "CPU automation is available only in a practice simulation.",
            "Continue the live draft manually or create a mock session.",
            409,
        )
    configuration = session.scalar(
        select(MockConfigurationRow).where(
            MockConfigurationRow.draft_session_id == session_id
        )
    )
    if configuration is None:
        raise _error(
            "MOCK.STATE_INCOMPLETE",
            "That practice session is missing its mock configuration.",
            "Keep the session for audit and create a fresh mock.",
            409,
        )
    return draft_row, configuration


def _current_pick(
    session: Session,
    session_id: str,
) -> DraftPickRow | None:
    return session.scalar(
        select(DraftPickRow)
        .where(
            DraftPickRow.session_id == session_id,
            DraftPickRow.player_id.is_(None),
        )
        .order_by(DraftPickRow.overall_pick)
        .limit(1)
    )


def _cpu_roster_counts(
    picks: list[DraftPickRow],
    candidates_by_id: dict[str, DraftCandidateRow],
    selecting_slot: int,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for pick in picks:
        if pick.selecting_slot != selecting_slot or pick.player_id is None:
            continue
        candidate = candidates_by_id.get(pick.player_id)
        if candidate is None:
            continue
        position = candidate.primary_position.strip().upper()
        counts[position] = counts.get(position, 0) + 1
    return counts


def _unfilled_starter_positions(
    league_shape: dict[str, Any],
    roster_counts: dict[str, int],
) -> set[str]:
    raw_slots = league_shape.get("starter_slots", [])
    if not isinstance(raw_slots, list):
        return set()
    remaining = dict(roster_counts)
    eligible_slots: list[list[str]] = []
    for raw_slot in raw_slots:
        if not isinstance(raw_slot, dict):
            continue
        positions = _normalized_positions(raw_slot.get("eligible_positions"))
        if positions:
            eligible_slots.append(positions)
    unfilled: set[str] = set()
    for positions in sorted(eligible_slots, key=lambda value: (len(value), value)):
        available = sorted(
            (remaining.get(position, 0), position)
            for position in positions
            if remaining.get(position, 0) > 0
        )
        if available:
            _, assigned_position = available[-1]
            remaining[assigned_position] -= 1
        else:
            unfilled.update(positions)
    return unfilled


def _score_components_read(candidate: ScoredCandidate) -> MockScoreComponentsRead:
    return MockScoreComponentsRead(
        board_order=candidate.components.board_order,
        starter_need=candidate.components.starter_need,
        depth_need=candidate.components.depth_need,
        archetype_fit=candidate.components.archetype_fit,
        duplication_penalty=candidate.components.duplication_penalty,
        random_variation=candidate.components.random_variation,
    )


def _decision_reason_codes(
    candidate: ScoredCandidate,
    engine_version: str,
) -> list[str]:
    reasons = [
        "MARKET_ECR_BASELINE"
        if engine_version == MARKET_BOARD_ENGINE_VERSION
        else "PRACTICE_BOARD_BASELINE"
    ]
    if candidate.components.starter_need > 0:
        reasons.append("STARTER_COVERAGE")
    if candidate.components.depth_need > 0:
        reasons.append("ROSTER_DEPTH")
    if candidate.components.archetype_fit > 0:
        reasons.append("PROFILE_ARCHETYPE_FIT")
    if candidate.components.duplication_penalty < 0:
        reasons.append("POSITION_CONCENTRATION_PENALTY")
    if candidate.components.random_variation != 0:
        reasons.append("SEEDED_VARIATION")
    return reasons


def _decision_limitations(
    profile: MockCpuProfileRow,
    league_shape: dict[str, Any],
    market_baseline: dict[str, Any],
) -> list[str]:
    limitations = {
        value
        for value in league_shape.get("limitations", [])
        if isinstance(value, str)
    }
    limitations.update(
        value
        for value in market_baseline.get("limitations", [])
        if isinstance(value, str)
    )
    if profile.source == "fallback":
        limitations.add("FALLBACK_PROFILE_NO_HISTORY")
    elif profile.confidence == "low":
        limitations.add("LOW_CONFIDENCE_HISTORY_PROFILE")
    return sorted(limitations)


def _advance_mock_revision(
    session: Session,
    configuration: MockConfigurationRow,
    expected_revision: int,
    now: str,
) -> None:
    result = session.execute(
        update(MockConfigurationRow)
        .where(
            MockConfigurationRow.id == configuration.id,
            MockConfigurationRow.revision == expected_revision,
        )
        .values(revision=expected_revision + 1, updated_at=now)
    )
    if result.rowcount != 1:
        session.rollback()
        raise _error(
            "MOCK.STALE_REVISION",
            "The mock changed before that CPU pick could be saved.",
            "Refresh the practice room and retry from the current pick.",
            409,
        )
    session.refresh(configuration)


def _build_cpu_decision_row(
    *,
    configuration: MockConfigurationRow,
    mutation,
    profile: MockCpuProfileRow,
    chosen: ScoredCandidate,
    scored: tuple[ScoredCandidate, ...],
    configured_randomness: int,
    applied_randomness: int,
    limitation_codes: list[str],
    now: str,
) -> MockPickDecisionRow:
    alternatives = [
        {
            "player_id": candidate.player_id,
            "total_score": candidate.total_score,
            "component_scores": _score_components_read(candidate).model_dump(),
        }
        for candidate in scored
        if candidate.player_id != chosen.player_id
    ][:5]
    return MockPickDecisionRow(
        id=str(uuid4()),
        mock_configuration_id=configuration.id,
        draft_pick_revision_id=mutation.pick_revision.id,
        overall_pick=mutation.pick.overall_pick,
        selecting_slot=mutation.pick.selecting_slot,
        chosen_player_id=chosen.player_id,
        profile_source=profile.source,
        profile_archetype_key=profile.archetype_key,
        engine_version=configuration.cpu_engine_version,
        rng_version=configuration.rng_version,
        total_score=chosen.total_score,
        component_scores_json=_json(_score_components_read(chosen).model_dump()),
        random_audit_json=_json(
            {
                "canonical_input": chosen.random_draw.canonical_input,
                "configured_randomness": configured_randomness,
                "digest_hex": chosen.random_draw.digest_hex,
                "effective_randomness": applied_randomness,
                "numerator": str(chosen.random_draw.numerator),
                "denominator": str(1 << 64),
                "purpose": "candidate-random-variation",
            }
        ),
        alternatives_json=_json(alternatives),
        reason_codes_json=_json(
            _decision_reason_codes(chosen, configuration.cpu_engine_version)
        ),
        limitation_codes_json=_json(limitation_codes),
        created_at=now,
    )


def advance_cpu_pick(
    session: Session,
    session_id: str,
    payload: MockCpuPickCreate,
) -> MockSessionRead:
    draft_row, configuration = _require_cpu_mock(session, session_id)
    if draft_row.status != "active":
        raise _error(
            "MOCK.NOT_ACTIVE",
            "A CPU pick can be recorded only while the mock is active.",
            "Resume the mock or start a new practice session.",
            409,
        )
    if configuration.revision != payload.mock_revision:
        raise _error(
            "MOCK.STALE_REVISION",
            "The mock changed before that CPU pick could be saved.",
            "Refresh the practice room and retry from the current pick.",
            409,
        )
    if (
        configuration.cpu_engine_version not in SUPPORTED_CPU_ENGINE_VERSIONS
        or configuration.rng_version != RNG_VERSION
    ):
        raise _error(
            "MOCK.VERSION_UNSUPPORTED",
            "This saved mock uses an unsupported CPU or random-draw version.",
            "Keep it for audit and create a new mock with the current engine.",
            409,
        )
    current = _current_pick(session, session_id)
    if current is None:
        raise _error(
            "MOCK.COMPLETE",
            "Every pick in this mock is already filled.",
            "Review the completed practice session.",
            409,
        )
    if current.overall_pick != payload.expected_overall_pick:
        raise _error(
            "MOCK.STALE_CURRENT_PICK",
            "The mock advanced before that CPU request could be saved.",
            "Refresh the practice room and use the current overall pick.",
            409,
        )
    if current.selecting_slot != payload.expected_selecting_slot:
        raise _error(
            "MOCK.STALE_CURRENT_SLOT",
            "The team on the clock changed before that CPU request could be saved.",
            "Refresh the practice room and verify the current draft slot.",
            409,
        )
    if current.selecting_slot == draft_row.user_slot:
        raise _error(
            "MOCK.USER_SLOT",
            "The user's draft slot cannot be automated.",
            "Make this pick manually from the ordinary draft candidate table.",
            409,
        )

    profile = session.scalar(
        select(MockCpuProfileRow).where(
            MockCpuProfileRow.mock_configuration_id == configuration.id,
            MockCpuProfileRow.draft_slot == current.selecting_slot,
        )
    )
    if profile is None:
        raise _error(
            "MOCK.PROFILE_MISSING",
            "The CPU slot is missing its saved profile snapshot.",
            "Keep the session for audit and create a fresh mock.",
            409,
        )
    try:
        applied_randomness = effective_randomness(
            configuration.randomness,
            profile.archetype_key,
        )
        profile_emphasis = emphasized_position(profile.archetype_key)
    except ValueError as exc:
        raise _error(
            "MOCK.PROFILE_UNSUPPORTED",
            "The CPU slot uses an unsupported profile archetype.",
            "Keep the session for audit and create a fresh mock.",
            409,
        ) from exc

    candidate_rows = _ordered_candidate_rows(
        session,
        session_id,
        configuration.cpu_engine_version,
    )
    picks = list(
        session.scalars(
            select(DraftPickRow)
            .where(DraftPickRow.session_id == session_id)
            .order_by(DraftPickRow.overall_pick)
        )
    )
    drafted_ids = {pick.player_id for pick in picks if pick.player_id is not None}
    available_inputs = tuple(
        CandidateInput(
            player_id=row.player_id,
            position=row.primary_position,
            practice_index=index,
        )
        for index, row in enumerate(candidate_rows)
        if row.player_id not in drafted_ids
    )
    if not available_inputs:
        raise _error(
            "MOCK.CANDIDATES_EXHAUSTED",
            "No frozen candidates remain available for the CPU pick.",
            "Review the draft or create a mock with a larger player pool.",
            409,
        )
    candidates_by_id = {row.player_id: row for row in candidate_rows}
    roster_counts = _cpu_roster_counts(
        picks,
        candidates_by_id,
        current.selecting_slot,
    )
    league_shape: dict[str, Any] = json.loads(configuration.league_shape_json)
    unfilled_positions = _unfilled_starter_positions(league_shape, roster_counts)
    considered = build_consideration_set(
        available_inputs,
        randomness=applied_randomness,
        unfilled_starter_positions=unfilled_positions,
        emphasized_position=profile_emphasis,
    )
    score_inputs: list[CandidateScoreInput] = []
    for candidate in considered:
        row = candidates_by_id[candidate.player_id]
        roster_components = roster_score_components(
            position=row.primary_position,
            is_rookie=row.is_rookie,
            roster_counts=roster_counts,
            unfilled_starter_positions=unfilled_positions,
            archetype_key=profile.archetype_key,
            tight_end_premium=league_shape.get("tight_end_premium") is True,
        )
        score_inputs.append(
            CandidateScoreInput(
                player_id=row.player_id,
                practice_index=candidate.practice_index,
                starter_need=roster_components.starter_need,
                depth_need=roster_components.depth_need,
                archetype_fit=roster_components.archetype_fit,
                duplication_penalty=roster_components.duplication_penalty,
            )
        )
    scored = score_candidates(
        tuple(score_inputs),
        candidate_count=len(candidate_rows),
        seed=configuration.seed,
        fingerprint=configuration.content_fingerprint,
        overall_pick=current.overall_pick,
        selecting_slot=current.selecting_slot,
        randomness=applied_randomness,
        engine_version=configuration.cpu_engine_version,
    )
    chosen = select_candidate(scored)
    now = utc_now_text()
    market_baseline: dict[str, Any] = json.loads(
        configuration.market_baseline_json or "{}"
    )
    limitations = _decision_limitations(profile, league_shape, market_baseline)
    try:
        mutation = record_pick_in_transaction(
            session,
            session_id,
            revision=payload.draft_revision,
            expected_overall_pick=payload.expected_overall_pick,
            expected_selecting_slot=payload.expected_selecting_slot,
            player_id=chosen.player_id,
        )
        session.flush()
        _advance_mock_revision(
            session,
            configuration,
            payload.mock_revision,
            now,
        )
        decision = _build_cpu_decision_row(
            configuration=configuration,
            mutation=mutation,
            profile=profile,
            chosen=chosen,
            scored=scored,
            configured_randomness=configuration.randomness,
            applied_randomness=applied_randomness,
            limitation_codes=limitations,
            now=now,
        )
        session.add(decision)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return read_mock_session(session, session_id)


def _guidance_read(
    row: MockGuidanceEventRow,
    strategy_revision: MockStrategyRevisionRow,
    strategy_definition_version: str,
) -> MockGuidanceRead:
    target_ranges = json.loads(row.target_ranges_json)
    affected_positions = target_ranges.get("affected_positions", [])
    return MockGuidanceRead(
        id=row.id,
        strategy_key=strategy_revision.next_strategy_key,
        strategy_definition_version=strategy_definition_version,
        effective_overall_pick=row.effective_overall_pick,
        state=row.state,
        confidence=row.confidence,
        observed_counts=json.loads(row.observed_counts_json),
        target_ranges=target_ranges,
        affected_positions=affected_positions,
        reason_codes=json.loads(row.reason_codes_json),
        limitation_codes=json.loads(row.limitation_codes_json),
        explanation_template_key=row.explanation_template_key,
        explanation=explanation_text(row.explanation_template_key),
        pivot_template_key=row.pivot_template_key,
        viable_pivot_explanation=pivot_text(row.pivot_template_key),
        status=row.status,
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )


def _user_roster(
    session: Session,
    draft_row: DraftSessionRow,
) -> list[tuple[str, bool]]:
    candidates = {
        candidate.player_id: candidate
        for candidate in _ordered_candidate_rows(session, draft_row.id)
    }
    picks = session.scalars(
        select(DraftPickRow)
        .where(
            DraftPickRow.session_id == draft_row.id,
            DraftPickRow.selecting_slot == draft_row.user_slot,
            DraftPickRow.player_id.is_not(None),
        )
        .order_by(DraftPickRow.overall_pick)
    )
    return [
        (
            candidates[pick.player_id].primary_position,
            candidates[pick.player_id].is_rookie,
        )
        for pick in picks
        if pick.player_id in candidates
    ]


def _decision_summary(
    session: Session,
    row: MockPickDecisionRow,
    *,
    profile_by_slot: dict[int, MockCpuProfileRow] | None = None,
) -> MockPickDecisionSummary:
    configuration = session.get(MockConfigurationRow, row.mock_configuration_id)
    if configuration is None:
        raise _error(
            "MOCK.STATE_INCOMPLETE",
            "A saved CPU decision is missing required snapshot state.",
            "Keep the session for audit and create a fresh mock.",
            409,
        )
    candidate = session.scalar(
        select(DraftCandidateRow).where(
            DraftCandidateRow.session_id == configuration.draft_session_id,
            DraftCandidateRow.player_id == row.chosen_player_id,
        )
    )
    pick = (
        session.scalar(
            select(DraftPickRow).where(
                DraftPickRow.session_id == configuration.draft_session_id,
                DraftPickRow.overall_pick == row.overall_pick,
            )
        )
        if candidate is not None
        else None
    )
    profile = (
        profile_by_slot.get(row.selecting_slot)
        if profile_by_slot is not None
        else session.scalar(
            select(MockCpuProfileRow).where(
                MockCpuProfileRow.mock_configuration_id
                == row.mock_configuration_id,
                MockCpuProfileRow.draft_slot == row.selecting_slot,
            )
        )
    )
    if candidate is None or pick is None or profile is None:
        raise _error(
            "MOCK.STATE_INCOMPLETE",
            "A saved CPU decision is missing required snapshot state.",
            "Keep the session for audit and create a fresh mock.",
            409,
        )
    latest_pick_revision = session.scalar(
        select(DraftPickRevisionRow)
        .where(DraftPickRevisionRow.pick_id == pick.id)
        .order_by(DraftPickRevisionRow.session_revision.desc())
        .limit(1)
    )
    active = bool(
        latest_pick_revision is not None
        and latest_pick_revision.id == row.draft_pick_revision_id
        and pick.player_id == row.chosen_player_id
    )
    decision_pick_revision = session.get(
        DraftPickRevisionRow,
        row.draft_pick_revision_id,
    )
    manually_corrected = bool(
        decision_pick_revision is not None
        and session.scalar(
            select(DraftPickRevisionRow.id)
            .where(
                DraftPickRevisionRow.pick_id == pick.id,
                DraftPickRevisionRow.action_kind == "corrected",
                DraftPickRevisionRow.session_revision
                > decision_pick_revision.session_revision,
            )
            .limit(1)
        )
        is not None
    )
    return MockPickDecisionSummary(
        id=row.id,
        overall_pick=row.overall_pick,
        selecting_slot=row.selecting_slot,
        chosen_player_id=row.chosen_player_id,
        chosen_player_display_name=candidate.display_name,
        chosen_player_position=candidate.primary_position,
        profile_source=row.profile_source,
        profile_archetype_key=row.profile_archetype_key,
        profile_confidence=profile.confidence,
        engine_version=row.engine_version,
        rng_version=row.rng_version,
        total_score=row.total_score,
        component_scores=MockScoreComponentsRead.model_validate_json(
            row.component_scores_json
        ),
        reason_codes=json.loads(row.reason_codes_json),
        limitation_codes=json.loads(row.limitation_codes_json),
        decision_status="active" if active else "historical",
        manually_corrected=manually_corrected,
        created_at=row.created_at,
    )


def read_mock_decision(
    session: Session,
    session_id: str,
    overall_pick: int,
) -> MockPickDecisionAudit:
    _, configuration = _require_cpu_mock(session, session_id)
    row = session.scalar(
        select(MockPickDecisionRow)
        .where(
            MockPickDecisionRow.mock_configuration_id == configuration.id,
            MockPickDecisionRow.overall_pick == overall_pick,
        )
        .order_by(MockPickDecisionRow.created_at.desc(), MockPickDecisionRow.id.desc())
        .limit(1)
    )
    if row is None:
        raise _error(
            "MOCK.DECISION_NOT_FOUND",
            "No CPU decision audit exists for that overall pick.",
            "Choose a CPU-made pick from the practice draft.",
            404,
        )
    summary = _decision_summary(session, row)
    return MockPickDecisionAudit(
        **summary.model_dump(),
        random_audit=json.loads(row.random_audit_json),
        alternatives=[
            MockDecisionAlternativeRead.model_validate(alternative)
            for alternative in json.loads(row.alternatives_json)
        ],
    )


def _reset_replay_status(
    session: Session,
    draft_row: DraftSessionRow,
    configuration: MockConfigurationRow,
) -> Literal[
    "original",
    "exact_replay",
    "new_seed",
    "snapshot_changed",
    "unavailable",
]:
    if draft_row.reset_from_session_id is None:
        return "original"
    source = session.scalar(
        select(MockConfigurationRow).where(
            MockConfigurationRow.draft_session_id
            == draft_row.reset_from_session_id
        )
    )
    if source is None:
        return "unavailable"
    if source.content_fingerprint != configuration.content_fingerprint:
        return "snapshot_changed"
    if source.seed != configuration.seed:
        return "new_seed"
    return "exact_replay"


def _market_baseline_read(
    configuration: MockConfigurationRow,
    candidate_count: int,
) -> MockMarketBaselineRead:
    if configuration.market_baseline_json:
        raw: dict[str, Any] = json.loads(configuration.market_baseline_json)
    else:
        raw = _practice_board_baseline(
            candidate_count,
            "LEGACY_PRACTICE_BOARD_ENGINE",
        )
    source_as_of = raw.get("source_as_of")
    freshness: Literal["fresh", "stale", "unavailable"] = "unavailable"
    if isinstance(source_as_of, str) and source_as_of:
        try:
            source_date = date.fromisoformat(source_as_of[:10])
        except ValueError:
            freshness = "unavailable"
        else:
            age_days = (datetime.now(UTC).date() - source_date).days
            freshness = "fresh" if age_days <= 14 else "stale"
    return MockMarketBaselineRead.model_validate(raw | {"freshness": freshness})


def read_mock_session(session: Session, session_id: str) -> MockSessionRead:
    draft_row = session.get(DraftSessionRow, session_id)
    configuration = session.scalar(
        select(MockConfigurationRow).where(
            MockConfigurationRow.draft_session_id == session_id
        )
    )
    if draft_row is None or configuration is None or draft_row.mode != "mock":
        raise _error(
            "MOCK.NOT_FOUND",
            "That mock session could not be found.",
            "Return to the Personal Board and choose an available mock.",
            404,
        )
    strategy_revisions = list(
        session.scalars(
        select(MockStrategyRevisionRow)
        .where(
            MockStrategyRevisionRow.mock_configuration_id == configuration.id
        )
            .order_by(MockStrategyRevisionRow.sequence_number)
        )
    )
    strategy_revision = strategy_revisions[-1] if strategy_revisions else None
    strategy_revision_by_id = {row.id: row for row in strategy_revisions}
    profiles = list(
        session.scalars(
            select(MockCpuProfileRow)
            .where(MockCpuProfileRow.mock_configuration_id == configuration.id)
            .order_by(MockCpuProfileRow.draft_slot)
        )
    )
    profile_by_slot = {profile.draft_slot: profile for profile in profiles}
    last_decision_row = session.scalar(
        select(MockPickDecisionRow)
        .where(MockPickDecisionRow.mock_configuration_id == configuration.id)
        .order_by(
            MockPickDecisionRow.overall_pick.desc(),
            MockPickDecisionRow.created_at.desc(),
            MockPickDecisionRow.id.desc(),
        )
        .limit(1)
    )
    guidance_rows = list(
        session.scalars(
            select(MockGuidanceEventRow)
            .where(MockGuidanceEventRow.mock_configuration_id == configuration.id)
            .order_by(
                MockGuidanceEventRow.created_at.desc(),
                MockGuidanceEventRow.id.desc(),
                MockGuidanceEventRow.effective_overall_pick.desc(),
            )
            .limit(20)
        )
    )
    if strategy_revision is None or not guidance_rows:
        raise _error(
            "MOCK.STATE_INCOMPLETE",
            "The mock session is missing required strategy state.",
            "Keep the session for audit and create a fresh mock.",
            409,
        )

    draft = read_session(session, session_id)
    league_shape: dict[str, Any] = json.loads(configuration.league_shape_json)
    limitations = _strategy_limitations(
        configuration.current_strategy_key,
        league_shape,
    )
    guidance = [
        _guidance_read(
            row,
            strategy_revision_by_id[row.strategy_revision_id],
            configuration.strategy_definition_version,
        )
        for row in guidance_rows
        if row.strategy_revision_id in strategy_revision_by_id
    ]
    if not guidance:
        raise _error(
            "MOCK.STATE_INCOMPLETE",
            "The mock session is missing required strategy guidance.",
            "Keep the session for audit and create a fresh mock.",
            409,
        )
    limitations = sorted(
        set(limitations) | set(guidance[0].limitation_codes)
    )
    roster_counts = user_roster_counts(_user_roster(session, draft_row))
    revision_roster_counts = json.loads(strategy_revision.user_roster_counts_json)
    return MockSessionRead(
        draft=draft,
        mock=MockConfigurationRead(
            seed=configuration.seed,
            rng_version=configuration.rng_version,
            cpu_engine_version=configuration.cpu_engine_version,
            strategy_definition_version=configuration.strategy_definition_version,
            content_fingerprint=configuration.content_fingerprint,
            randomness=configuration.randomness,
            current_strategy_key=configuration.current_strategy_key,
            strategy_compatibility="reduced" if limitations else "compatible",
            strategy_limitations=limitations,
            reset_replay_status=_reset_replay_status(
                session,
                draft_row,
                configuration,
            ),
            revision=configuration.revision,
            include_in_learning=configuration.include_in_learning,
            learning_opted_in_at=configuration.learning_opted_in_at,
            learning_withdrawn_at=configuration.learning_withdrawn_at,
            created_at=configuration.created_at,
            updated_at=configuration.updated_at,
            market_baseline=_market_baseline_read(
                configuration,
                draft.candidate_total,
            ),
        ),
        current_strategy_revision=MockStrategyRevisionRead(
            sequence_number=strategy_revision.sequence_number,
            reason=(
                "initial_strategy"
                if strategy_revision.sequence_number == 1
                else "user_pivot"
            ),
            previous_strategy_key=strategy_revision.previous_strategy_key,
            next_strategy_key=strategy_revision.next_strategy_key,
            effective_overall_pick=strategy_revision.effective_overall_pick,
            user_roster_counts=revision_roster_counts,
            created_at=strategy_revision.created_at,
        ),
        user_roster_counts=roster_counts,
        current_checkpoint=guidance[0],
        guidance=guidance,
        cpu_profiles=[
            MockCpuProfileRead(
                draft_slot=row.draft_slot,
                source=row.source,
                archetype_key=row.archetype_key,
                confidence=row.confidence,
                draft_sample_count=row.draft_sample_count,
                pick_sample_count=row.pick_sample_count,
            )
            for row in profiles
        ],
        last_cpu_decision=(
            _decision_summary(
                session,
                last_decision_row,
                profile_by_slot=profile_by_slot,
            )
            if last_decision_row
            else None
        ),
        can_advance_cpu=bool(
            draft.status == "active"
            and draft.current_pick
            and draft.current_pick.selecting_slot != draft.user_slot
        ),
        recovery_guidance=draft.recovery_guidance,
    )
