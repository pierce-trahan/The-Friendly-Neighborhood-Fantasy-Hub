from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from friendly_hub.core.errors import HubError
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.drafts.models import (
    DraftCandidateRow,
    DraftPickRevisionRow,
    DraftPickRow,
    DraftSessionRow,
    DraftTeamRow,
)
from friendly_hub.domains.leagues.models import LeagueProfileRow
from friendly_hub.domains.leagues.schemas import LeagueProfileDocument
from friendly_hub.domains.mocks.models import MockConfigurationRow
from friendly_hub.domains.reports.definitions import (
    BALANCED_MAXIMUM_BASIS_POINTS,
    EXPLANATION_TEMPLATE_VERSION,
    REPORT_ENGINE_VERSION,
    REPORT_RULES_VERSION,
    SECTION_KEYS,
    SECTION_TITLES,
    SUPPORTED_SLOT_ELIGIBILITY,
)
from friendly_hub.domains.reports.engine import (
    RosterPlayer,
    StarterCoverageResult,
    StarterSlot,
    canonical_json,
    content_fingerprint,
    evaluate_concentration,
    evaluate_starter_coverage,
    render_explanation,
    unsupported_section_state,
)
from friendly_hub.domains.reports.evidence import (
    EvidenceContext,
    build_evidence_sections,
    load_evidence_context,
    no_evidence_fingerprint_document,
)
from friendly_hub.domains.reports.history import (
    DecisionHistoryContext,
    MomentCandidate,
    MomentPick,
    build_history_sections,
    load_decision_history,
)
from friendly_hub.domains.reports.models import (
    PostDraftReportMomentRow,
    PostDraftReportPlayerRow,
    PostDraftReportRow,
    PostDraftReportSectionRow,
)
from friendly_hub.domains.reports.schemas import (
    PostDraftReportGenerateRequest,
    PostDraftReportGenerateResponse,
    PostDraftReportListResponse,
    PostDraftReportMomentRead,
    PostDraftReportPlayerRead,
    PostDraftReportRead,
    PostDraftReportSectionRead,
    PostDraftReportSummaryRead,
)

logger = logging.getLogger("friendly_hub.reports")

MAXIMUM_DRAFT_CANDIDATES = 500
MAXIMUM_USER_ROSTER_PICKS = 60

_SLOT_ALIASES = {
    "SUPERFLEX": "SUPER_FLEX",
    "SUPER_FLEX": "SUPER_FLEX",
    "SF": "SUPER_FLEX",
}

_CORE_EXPLANATIONS = {
    "draft.summary.observed": (
        "This snapshot records the completed draft configuration and the user's saved roster."
    ),
    "position.inventory.observed": (
        "Position counts and investment windows come directly from the saved completed picks."
    ),
}

_ACTION_REVIEW_DRAFT = (
    "The draft and any existing reports remain unchanged. Review the saved draft "
    "before retrying."
)
_ACTION_REVIEW_CANDIDATES = (
    "The draft and any existing reports remain unchanged. Review the saved candidate "
    "snapshot before retrying."
)
_ACTION_REVIEW_PICKS = (
    "The draft and any existing reports remain unchanged. Review the saved pick "
    "history before retrying."
)
_ACTION_RESTORE_LEAGUE = (
    "The draft and any existing reports remain unchanged. Restore or re-import a "
    "valid local league profile."
)
_ACTION_ATTACH_LEAGUE = (
    "The draft and any existing reports remain unchanged. Attach a valid local "
    "league profile and retry."
)
_ACTION_REFRESH_COMPLETED = (
    "The draft and any existing reports remain unchanged. Refresh the completed "
    "draft and retry with its exact revision."
)
_ACTION_RESTORE_MOCK = (
    "The draft and any existing reports remain unchanged. Open another saved mock or "
    "restore this one from backup."
)
_ACTION_RETRY_REVISION = (
    "The draft and any existing reports remain unchanged. Retry the same completed "
    "revision."
)
_ACTION_RESTORE_REPORT = (
    "The source draft remains unchanged. Restore the local backup or generate from "
    "a different completed revision."
)


@dataclass(frozen=True)
class _CandidateSnapshot:
    player_id: str
    display_name: str
    primary_position: str
    fantasy_positions: tuple[str, ...]
    is_rookie: bool
    manual_rank: int | None
    tier_order: int | None
    favorite: bool


@dataclass(frozen=True)
class _GenerationSnapshot:
    draft: DraftSessionRow
    picks: tuple[DraftPickRow, ...]
    teams: tuple[DraftTeamRow, ...]
    candidates: tuple[_CandidateSnapshot, ...]
    roster: tuple[RosterPlayer, ...]
    roster_candidates: tuple[_CandidateSnapshot, ...]
    starter_slots: tuple[StarterSlot, ...]
    league_shape: dict[str, Any]
    league_shape_fingerprint: str
    mock_context: dict[str, Any] | None
    evidence_context: EvidenceContext | None
    decision_history: DecisionHistoryContext


@dataclass(frozen=True)
class _Section:
    section_key: str
    availability: str
    confidence: str
    metrics: dict[str, Any]
    reason_codes: tuple[str, ...]
    limitation_codes: tuple[str, ...]
    explanation_template_key: str
    explanation: str
    safe_provenance: dict[str, Any]


def _error(
    code: str,
    message: str,
    action: str,
    status_code: int,
    *,
    retryable: bool = False,
) -> HubError:
    return HubError(
        code=code,
        message=message,
        action=action,
        status_code=status_code,
        retryable=retryable,
    )


def _parse_utc(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise _error(
            "REPORT_DRAFT_INCOMPLETE",
            f"The saved draft has an invalid {field_name} timestamp.",
            _ACTION_REVIEW_DRAFT,
            409,
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error(
            "REPORT_DRAFT_INCOMPLETE",
            f"The saved draft has an invalid {field_name} timestamp.",
            _ACTION_REVIEW_DRAFT,
            409,
        )
    return parsed.astimezone(UTC)


def _normalized_positions(raw_json: str) -> tuple[str, ...]:
    try:
        value = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise _error(
            "REPORT_DRAFT_INCOMPLETE",
            "A frozen draft candidate has invalid position eligibility.",
            _ACTION_REVIEW_CANDIDATES,
            409,
        ) from exc
    if not isinstance(value, list):
        raise _error(
            "REPORT_DRAFT_INCOMPLETE",
            "A frozen draft candidate has invalid position eligibility.",
            _ACTION_REVIEW_CANDIDATES,
            409,
        )
    return tuple(
        sorted({item.strip().upper() for item in value if isinstance(item, str) and item.strip()})
    )


def _candidate_snapshot(row: DraftCandidateRow) -> _CandidateSnapshot:
    return _CandidateSnapshot(
        player_id=row.player_id,
        display_name=row.display_name,
        primary_position=row.primary_position.strip().upper(),
        fantasy_positions=_normalized_positions(row.fantasy_positions_json),
        is_rookie=row.is_rookie,
        manual_rank=row.manual_rank,
        tier_order=row.tier_order,
        favorite=row.favorite,
    )


def _slot_type(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
    return _SLOT_ALIASES.get(normalized, normalized)


def _normalized_slot_positions(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        sorted({item.strip().upper() for item in value if isinstance(item, str) and item.strip()})
    )


def _tight_end_premium(document: LeagueProfileDocument) -> bool:
    raw_rules = document.scoring.get("rules", [])
    if not isinstance(raw_rules, list):
        return False
    for rule in raw_rules:
        if not isinstance(rule, dict):
            continue
        positions = _normalized_slot_positions(rule.get("position_scope"))
        points = rule.get("points")
        if (
            "TE" in positions
            and isinstance(points, int | float)
            and not isinstance(points, bool)
            and points > 0
            and rule.get("normalized_stat") in {"reception", "receiving_first_down"}
        ):
            return True
    return False


def _live_league_shape(
    league_row: LeagueProfileRow,
    draft: DraftSessionRow,
) -> dict[str, Any]:
    try:
        document = LeagueProfileDocument.model_validate_json(league_row.payload_json)
    except ValidationError as exc:
        raise _error(
            "REPORT_LEAGUE_SHAPE_UNAVAILABLE",
            "The saved league profile cannot be normalized for reporting.",
            _ACTION_RESTORE_LEAGUE,
            409,
        ) from exc
    return {
        "schema_version": 1,
        "league_type": document.league.league_type,
        "starter_slots": document.roster.get("starters"),
        "bench_slots": document.roster.get("bench_slots"),
        "taxi_slots": document.roster.get("taxi_slots"),
        "injured_reserve_slots": document.roster.get("injured_reserve_slots"),
        "tight_end_premium": _tight_end_premium(document),
        "profile_team_count": document.league.team_count,
        "source_as_of": document.provenance.source_as_of or league_row.imported_at,
        "draft_team_count": draft.team_count,
        "draft_round_count": draft.round_count,
        "draft_format": draft.draft_format,
        "third_round_reversal": draft.third_round_reversal,
    }


def _normalize_league_shape(
    raw_shape: dict[str, Any],
    draft: DraftSessionRow,
) -> tuple[tuple[StarterSlot, ...], dict[str, Any]]:
    raw_slots = raw_shape.get("starter_slots")
    if not isinstance(raw_slots, list) or not raw_slots or len(raw_slots) > 60:
        raise _error(
            "REPORT_LEAGUE_SHAPE_UNAVAILABLE",
            "The saved league starter shape cannot be normalized for reporting.",
            _ACTION_ATTACH_LEAGUE,
            409,
        )

    counts: Counter[str] = Counter()
    slots: list[StarterSlot] = []
    for slot_order, raw_slot in enumerate(raw_slots):
        if not isinstance(raw_slot, dict):
            break
        slot_type = _slot_type(raw_slot.get("slot"))
        positions = _normalized_slot_positions(raw_slot.get("eligible_positions"))
        if (
            slot_type not in SUPPORTED_SLOT_ELIGIBILITY
            or set(positions) != SUPPORTED_SLOT_ELIGIBILITY[slot_type]
        ):
            break
        counts[slot_type] += 1
        slots.append(
            StarterSlot(
                slot_order=slot_order,
                slot_key=f"{slot_type}-{counts[slot_type]}",
                slot_type=slot_type,  # type: ignore[arg-type]
                eligible_positions=positions,
            )
        )
    if len(slots) != len(raw_slots):
        raise _error(
            "REPORT_LEAGUE_SHAPE_UNAVAILABLE",
            "The saved league starter shape contains an unsupported slot.",
            _ACTION_ATTACH_LEAGUE,
            409,
        )

    limitations: list[str] = []
    profile_team_count = raw_shape.get("profile_team_count")
    if isinstance(profile_team_count, int) and profile_team_count != draft.team_count:
        limitations.append("LEAGUE_TEAM_COUNT_DIFFERS")
    normalized = {
        "schema_version": 1,
        "team_count": draft.team_count,
        "round_count": draft.round_count,
        "draft_format": draft.draft_format,
        "third_round_reversal": draft.third_round_reversal,
        "league_type": raw_shape.get("league_type", "unknown"),
        "starter_slots": [
            {
                "slot_order": slot.slot_order,
                "slot_key": slot.slot_key,
                "slot_type": slot.slot_type,
                "eligible_positions": list(slot.eligible_positions),
            }
            for slot in slots
        ],
        "bench_slots": raw_shape.get("bench_slots"),
        "taxi_slots": raw_shape.get("taxi_slots"),
        "injured_reserve_slots": raw_shape.get("injured_reserve_slots"),
        "tight_end_premium": raw_shape.get("tight_end_premium") is True,
        "limitations": limitations,
    }
    return tuple(slots), normalized


def _require_draft(session: Session, session_id: str) -> DraftSessionRow:
    draft = session.get(DraftSessionRow, session_id)
    if draft is None:
        raise _error(
            "DRAFT.NOT_FOUND",
            "That draft session could not be found.",
            "Return to the saved draft list and choose an available session.",
            404,
        )
    return draft


def _load_generation_snapshot(
    session: Session,
    session_id: str,
    payload: PostDraftReportGenerateRequest,
) -> _GenerationSnapshot:
    draft = _require_draft(session, session_id)
    if draft.status != "completed" or draft.completed_at is None:
        raise _error(
            "REPORT_DRAFT_NOT_COMPLETE",
            "A post-draft report can be generated only from a completed draft.",
            "The draft and any existing reports remain unchanged. Complete the draft, then retry.",
            409,
        )
    completed_at = _parse_utc(draft.completed_at, field_name="completion")
    if payload.draft_revision != draft.revision or payload.expected_completed_at != completed_at:
        raise _error(
            "REPORT_DRAFT_STALE_REVISION",
            "The completed draft changed before the report request was accepted.",
            _ACTION_REFRESH_COMPLETED,
            409,
        )

    picks = tuple(
        session.scalars(
            select(DraftPickRow)
            .where(DraftPickRow.session_id == draft.id)
            .order_by(DraftPickRow.overall_pick)
        )
    )
    expected_pick_count = draft.team_count * draft.round_count
    player_ids = [pick.player_id for pick in picks]
    if (
        len(picks) != expected_pick_count
        or any(player_id is None for player_id in player_ids)
        or len(set(player_ids)) != expected_pick_count
    ):
        raise _error(
            "REPORT_DRAFT_INCOMPLETE",
            "The completed draft does not contain one unique player for every active pick.",
            _ACTION_REVIEW_PICKS,
            409,
        )

    revisions = tuple(
        session.scalars(
            select(DraftPickRevisionRow)
            .where(DraftPickRevisionRow.session_id == draft.id)
            .order_by(DraftPickRevisionRow.session_revision)
        )
    )
    latest_by_pick: dict[str, DraftPickRevisionRow] = {}
    for revision in revisions:
        latest_by_pick[revision.pick_id] = revision
    if any(
        pick.id not in latest_by_pick
        or latest_by_pick[pick.id].next_player_id != pick.player_id
        or latest_by_pick[pick.id].session_revision > draft.revision
        for pick in picks
    ):
        raise _error(
            "REPORT_DRAFT_INCOMPLETE",
            "The completed draft revision history cannot reproduce its active picks.",
            _ACTION_REVIEW_PICKS,
            409,
        )

    candidate_rows = tuple(
        session.scalars(
            select(DraftCandidateRow)
            .where(DraftCandidateRow.session_id == draft.id)
            .order_by(DraftCandidateRow.player_id)
        )
    )
    if not candidate_rows or len(candidate_rows) > MAXIMUM_DRAFT_CANDIDATES:
        raise _error(
            "REPORT_DRAFT_INCOMPLETE",
            "The frozen candidate snapshot is missing or exceeds the report limit.",
            _ACTION_REVIEW_CANDIDATES,
            409,
        )
    candidates = tuple(_candidate_snapshot(row) for row in candidate_rows)
    candidate_by_player = {candidate.player_id: candidate for candidate in candidates}
    if any(player_id not in candidate_by_player for player_id in player_ids):
        raise _error(
            "REPORT_DRAFT_INCOMPLETE",
            "At least one completed pick is missing from the frozen candidate snapshot.",
            _ACTION_REVIEW_CANDIDATES,
            409,
        )

    teams = tuple(
        session.scalars(
            select(DraftTeamRow)
            .where(DraftTeamRow.session_id == draft.id)
            .order_by(DraftTeamRow.draft_slot)
        )
    )
    if (
        len(teams) != draft.team_count
        or [team.draft_slot for team in teams] != list(range(1, draft.team_count + 1))
        or sum(team.is_user for team in teams) != 1
    ):
        raise _error(
            "REPORT_DRAFT_INCOMPLETE",
            "The completed draft team snapshot is incomplete.",
            _ACTION_REVIEW_DRAFT,
            409,
        )

    mock_context: dict[str, Any] | None = None
    mock_configuration: MockConfigurationRow | None = None
    if draft.mode == "mock":
        mock_configuration = session.scalar(
            select(MockConfigurationRow).where(MockConfigurationRow.draft_session_id == draft.id)
        )
        if mock_configuration is None:
            raise _error(
                "REPORT_DRAFT_INCOMPLETE",
                "The completed mock is missing its saved mock configuration.",
                _ACTION_REVIEW_DRAFT,
                409,
            )
        try:
            raw_shape = json.loads(mock_configuration.league_shape_json)
        except json.JSONDecodeError as exc:
            raise _error(
                "REPORT_LEAGUE_SHAPE_UNAVAILABLE",
                "The completed mock has an invalid frozen league shape.",
                _ACTION_RESTORE_MOCK,
                409,
            ) from exc
        if not isinstance(raw_shape, dict):
            raise _error(
                "REPORT_LEAGUE_SHAPE_UNAVAILABLE",
                "The completed mock has an invalid frozen league shape.",
                _ACTION_RESTORE_MOCK,
                409,
            )
        raw_shape = {
            **raw_shape,
            "draft_team_count": draft.team_count,
            "draft_round_count": draft.round_count,
            "draft_format": draft.draft_format,
            "third_round_reversal": draft.third_round_reversal,
        }
        mock_context = {
            "configuration_fingerprint": mock_configuration.content_fingerprint,
            "strategy_definition_version": mock_configuration.strategy_definition_version,
        }
    else:
        if draft.league_profile_id is None:
            raise _error(
                "REPORT_LEAGUE_SHAPE_UNAVAILABLE",
                "The completed draft has no saved league profile for starter coverage.",
                _ACTION_ATTACH_LEAGUE,
                409,
            )
        league_row = session.get(LeagueProfileRow, draft.league_profile_id)
        if league_row is None:
            raise _error(
                "REPORT_LEAGUE_SHAPE_UNAVAILABLE",
                "The completed draft's saved league profile is unavailable.",
                _ACTION_RESTORE_LEAGUE,
                409,
            )
        raw_shape = _live_league_shape(league_row, draft)

    starter_slots, league_shape = _normalize_league_shape(raw_shape, draft)
    league_shape_fingerprint = content_fingerprint(league_shape)
    user_picks = tuple(pick for pick in picks if pick.selecting_slot == draft.user_slot)
    if not user_picks or len(user_picks) > MAXIMUM_USER_ROSTER_PICKS:
        raise _error(
            "REPORT_DRAFT_INCOMPLETE",
            "The completed draft has an invalid user-roster size for reporting.",
            _ACTION_REVIEW_DRAFT,
            409,
        )
    roster_candidates = tuple(
        candidate_by_player[pick.player_id]  # type: ignore[index]
        for pick in user_picks
    )
    roster = tuple(
        RosterPlayer(
            canonical_player_id=candidate.player_id,
            overall_pick=pick.overall_pick,
            primary_position=candidate.primary_position,
            fantasy_positions=candidate.fantasy_positions,
        )
        for pick, candidate in zip(user_picks, roster_candidates, strict=True)
    )
    evidence_context = load_evidence_context(
        session,
        draft=draft,
        roster=roster,
        completed_at=completed_at,
    )
    decision_history = load_decision_history(
        session,
        draft=draft,
        mock_configuration=mock_configuration,
        candidates=tuple(
            MomentCandidate(
                player_id=candidate.player_id,
                display_name=candidate.display_name,
                primary_position=candidate.primary_position,
                manual_rank=candidate.manual_rank,
                tier_order=candidate.tier_order,
                favorite=candidate.favorite,
            )
            for candidate in candidates
        ),
        picks=tuple(
            MomentPick(
                overall_pick=pick.overall_pick,
                selecting_slot=pick.selecting_slot,
                player_id=pick.player_id,  # type: ignore[arg-type]
            )
            for pick in picks
        ),
        completed_at=completed_at,
    )
    return _GenerationSnapshot(
        draft=draft,
        picks=picks,
        teams=teams,
        candidates=candidates,
        roster=roster,
        roster_candidates=roster_candidates,
        starter_slots=starter_slots,
        league_shape=league_shape,
        league_shape_fingerprint=league_shape_fingerprint,
        mock_context=mock_context,
        evidence_context=evidence_context,
        decision_history=decision_history,
    )


def _canonical_input(snapshot: _GenerationSnapshot) -> dict[str, Any]:
    draft = snapshot.draft
    return {
        "draft": {
            "id": draft.id,
            "name": draft.name,
            "board_id": draft.board_id,
            "revision": draft.revision,
            "completed_at": _parse_utc(
                draft.completed_at or "", field_name="completion"
            ).isoformat(),
            "mode": draft.mode,
            "format": draft.draft_format,
            "third_round_reversal": draft.third_round_reversal,
            "team_count": draft.team_count,
            "round_count": draft.round_count,
            "user_slot": draft.user_slot,
            "teams": [
                {
                    "draft_slot": team.draft_slot,
                    "display_name": team.display_name,
                    "is_user": team.is_user,
                }
                for team in snapshot.teams
            ],
        },
        "ordered_active_picks": [
            {
                "overall_pick": pick.overall_pick,
                "round_number": pick.round_number,
                "pick_in_round": pick.pick_in_round,
                "selecting_slot": pick.selecting_slot,
                "player_id": pick.player_id,
                "recorded_at": pick.recorded_at,
            }
            for pick in snapshot.picks
        ],
        "frozen_candidates": [
            {
                "player_id": candidate.player_id,
                "display_name": candidate.display_name,
                "primary_position": candidate.primary_position,
                "fantasy_positions": list(candidate.fantasy_positions),
                "is_rookie": candidate.is_rookie,
                "personal_rank": candidate.manual_rank,
                "tier_order": candidate.tier_order,
                "favorite": candidate.favorite,
            }
            for candidate in snapshot.candidates
        ],
        "normalized_league_shape": snapshot.league_shape,
        "mock_context": snapshot.mock_context,
        "alert_context": (
            snapshot.evidence_context.fingerprint_document()
            if snapshot.evidence_context is not None
            else no_evidence_fingerprint_document()
        ),
        "decision_moment_context": snapshot.decision_history.fingerprint_document(),
        "versions": {
            "report_engine": REPORT_ENGINE_VERSION,
            "report_rules": REPORT_RULES_VERSION,
            "explanation_templates": EXPLANATION_TEMPLATE_VERSION,
        },
    }


def _section(
    section_key: str,
    *,
    availability: str,
    confidence: str,
    metrics: dict[str, Any],
    reason_codes: tuple[str, ...] = (),
    limitation_codes: tuple[str, ...] = (),
    explanation_template_key: str,
    explanation: str,
    safe_provenance: dict[str, Any] | None = None,
) -> _Section:
    return _Section(
        section_key=section_key,
        availability=availability,
        confidence=confidence,
        metrics=metrics,
        reason_codes=reason_codes,
        limitation_codes=limitation_codes,
        explanation_template_key=explanation_template_key,
        explanation=explanation,
        safe_provenance=safe_provenance or {},
    )


def _percent_text(basis_points: int) -> str:
    return f"{basis_points / 100:.2f}".rstrip("0").rstrip(".")


def _starter_explanation(coverage: StarterCoverageResult) -> tuple[str, str]:
    if coverage.starter_slots_filled == coverage.starter_slots_total:
        key = "starter.coverage_complete"
        values = {"starter_slots_total": coverage.starter_slots_total}
    else:
        key = "starter.coverage_partial"
        values = {
            "starter_slots_filled": coverage.starter_slots_filled,
            "starter_slots_total": coverage.starter_slots_total,
        }
    return key, render_explanation(template_key=key, values=values)


def _concentration_explanation(
    bands: tuple[str, ...],
    maximum_position: str,
    maximum_share_basis_points: int,
    unfilled_distinct_positions: int,
) -> tuple[str, str]:
    share_band = next((band for band in bands if band != "coverage_gap"), None)
    if share_band == "balanced_distribution":
        key = "concentration.balanced"
        values: dict[str, str | int] = {
            "balanced_maximum_percent": BALANCED_MAXIMUM_BASIS_POINTS // 100
        }
    elif share_band == "concentrated":
        key = "concentration.concentrated"
        values = {
            "position": maximum_position,
            "position_share_percent": _percent_text(maximum_share_basis_points),
        }
    elif share_band == "highly_concentrated":
        key = "concentration.highly_concentrated"
        values = {
            "position": maximum_position,
            "position_share_percent": _percent_text(maximum_share_basis_points),
        }
    else:
        key = "concentration.coverage_gap"
        values = {"unfilled_position_count": unfilled_distinct_positions}
    return key, render_explanation(template_key=key, values=values)


def _build_sections(
    snapshot: _GenerationSnapshot,
    coverage: StarterCoverageResult,
) -> tuple[_Section, ...]:
    draft = snapshot.draft
    roster_count = len(snapshot.roster)
    position_counts = Counter(player.primary_position for player in snapshot.roster)
    early_round = ceil(draft.round_count * 0.25)
    middle_round = ceil(draft.round_count * 0.60)
    position_windows: dict[str, dict[str, Any]] = {}
    for position in sorted(position_counts):
        picks = sorted(
            player.overall_pick for player in snapshot.roster if player.primary_position == position
        )
        rounds = [(overall_pick - 1) // draft.team_count + 1 for overall_pick in picks]
        position_windows[position] = {
            "count": len(picks),
            "first_overall_pick": picks[0],
            "last_overall_pick": picks[-1],
            "early_pick_count": sum(round_number <= early_round for round_number in rounds),
            "middle_pick_count": sum(
                early_round < round_number <= middle_round for round_number in rounds
            ),
            "late_pick_count": sum(round_number > middle_round for round_number in rounds),
        }

    assigned_slot_keys = {assignment.slot_key for assignment in coverage.assignments}
    configured_base_types = sorted(
        {
            slot.slot_type
            for slot in snapshot.starter_slots
            if slot.slot_type in {"QB", "RB", "WR", "TE"}
        }
    )
    unfilled_base_types = [
        slot_type
        for slot_type in configured_base_types
        if not any(
            slot.slot_type == slot_type and slot.slot_key in assigned_slot_keys
            for slot in snapshot.starter_slots
        )
    ]
    concentration = evaluate_concentration(
        total_user_picks=roster_count,
        position_pick_counts=position_counts,
        unfilled_distinct_starter_positions=len(unfilled_base_types),
    )
    maximum_count = max(position_counts.values())
    maximum_position = min(
        position for position, count in position_counts.items() if count == maximum_count
    )
    starter_template, starter_explanation = _starter_explanation(coverage)
    concentration_template, concentration_explanation = _concentration_explanation(
        concentration.bands,
        maximum_position,
        concentration.maximum_share_basis_points,
        len(unfilled_base_types),
    )

    sections: list[_Section] = [
        _section(
            "draft_summary",
            availability="supported",
            confidence="high",
            metrics={
                "draft_name": draft.name,
                "mode": draft.mode,
                "completed_at": draft.completed_at,
                "team_count": draft.team_count,
                "round_count": draft.round_count,
                "draft_format": draft.draft_format,
                "third_round_reversal": draft.third_round_reversal,
                "user_slot": draft.user_slot,
                "total_user_picks": roster_count,
                "starter_slots": len(snapshot.starter_slots),
                "bench_slots": snapshot.league_shape.get("bench_slots"),
                "mock_context_available": snapshot.mock_context is not None,
                "alert_context_available": (
                    snapshot.decision_history.alerts.state != "not_configured"
                ),
                "evidence_context_available": snapshot.evidence_context is not None,
            },
            explanation_template_key="draft.summary.observed",
            explanation=_CORE_EXPLANATIONS["draft.summary.observed"],
        ),
        _section(
            "position_inventory",
            availability="supported",
            confidence="high",
            metrics={
                "position_counts": dict(sorted(position_counts.items())),
                "position_windows": position_windows,
                "rookie_count": sum(
                    candidate.is_rookie for candidate in snapshot.roster_candidates
                ),
                "early_round_boundary": early_round,
                "middle_round_boundary": middle_round,
            },
            explanation_template_key="position.inventory.observed",
            explanation=_CORE_EXPLANATIONS["position.inventory.observed"],
        ),
        _section(
            "starter_coverage",
            availability=coverage.availability,
            confidence=coverage.confidence,
            metrics={
                "starter_slots_total": coverage.starter_slots_total,
                "starter_slots_filled": coverage.starter_slots_filled,
                "starter_coverage_basis_points": coverage.starter_coverage_basis_points,
                "assignments": [
                    {
                        "slot_order": assignment.slot_order,
                        "slot_key": assignment.slot_key,
                        "player_id": assignment.canonical_player_id,
                    }
                    for assignment in coverage.assignments
                ],
                "unfilled_slot_keys": list(coverage.unfilled_slot_keys),
                "ambiguous_flex_slot_keys": list(coverage.ambiguous_flex_slot_keys),
                "depth_counts": dict(coverage.depth_counts),
            },
            reason_codes=coverage.reason_codes,
            limitation_codes=coverage.limitation_codes,
            explanation_template_key=starter_template,
            explanation=starter_explanation,
        ),
        _section(
            "roster_concentration",
            availability=coverage.availability,
            confidence=coverage.confidence,
            metrics={
                "position_share_basis_points": {
                    position: count * 10_000 // roster_count
                    for position, count in sorted(position_counts.items())
                },
                "maximum_position": maximum_position,
                "maximum_share_basis_points": concentration.maximum_share_basis_points,
                "bands": list(concentration.bands),
                "starter_position_gaps": unfilled_base_types,
                "surplus_after_starter_assignment": dict(coverage.depth_counts),
                "early_pick_counts": {
                    position: metrics["early_pick_count"]
                    for position, metrics in position_windows.items()
                },
                "zero_depth_positions": [
                    position
                    for position, count in coverage.depth_counts
                    if position in configured_base_types and count == 0
                ],
            },
            reason_codes=tuple(band.upper() for band in concentration.bands),
            limitation_codes=coverage.limitation_codes,
            explanation_template_key=concentration_template,
            explanation=concentration_explanation,
        ),
    ]

    for result in build_evidence_sections(snapshot.evidence_context, snapshot.roster):
        sections.append(
            _section(
                result.section_key,
                availability=result.availability,
                confidence=result.confidence,
                metrics=result.metrics,
                reason_codes=result.reason_codes,
                limitation_codes=result.limitation_codes,
                explanation_template_key=result.explanation_template_key,
                explanation=result.explanation,
                safe_provenance=result.safe_provenance,
            )
        )

    for key, template_key, limitation in (
        ("long_term_value", "long_term.unavailable", "MARKET_BAND_IS_NOT_LONG_TERM_OUTCOME"),
        ("liquidity", "liquidity.unavailable", "MARKET_BAND_IS_NOT_LIQUIDITY"),
        ("player_fragility", "fragility.unavailable", "INJURY_CONTRACT_ROLE_EVIDENCE_REQUIRED"),
    ):
        state = unsupported_section_state(key)
        sections.append(
            _section(
                key,
                availability=state.availability,
                confidence=state.confidence,
                metrics={},
                reason_codes=state.reason_codes,
                limitation_codes=(limitation,),
                explanation_template_key=template_key,
                explanation=render_explanation(template_key=template_key, values={}),
            )
        )

    for result in build_history_sections(
        snapshot.decision_history,
        draft_mode=draft.mode,
        final_position_counts=dict(position_counts),
    ):
        sections.append(
            _section(
                result.section_key,
                availability=result.availability,
                confidence=result.confidence,
                metrics=result.metrics,
                reason_codes=result.reason_codes,
                limitation_codes=result.limitation_codes,
                explanation_template_key=result.explanation_template_key,
                explanation=result.explanation,
            )
        )

    limited_or_unavailable = [
        section.section_key
        for section in sections
        if section.availability in {"limited", "unavailable"}
    ]
    report_limitations = sorted(
        {limitation for section in sections for limitation in section.limitation_codes}
        | {"NO_OUTCOME_PROJECTION", "USER_JUDGMENT_AUTHORITATIVE"}
    )
    sections.append(
        _section(
            "evidence_limits",
            availability="supported",
            confidence="high",
            metrics={
                "limited_or_unavailable_sections": limited_or_unavailable,
                "missing_evidence_categories": [
                    "age",
                    "contract",
                    "injury",
                    "liquidity",
                    "long_term_outcome",
                    "projection",
                ],
                "report_engine_version": REPORT_ENGINE_VERSION,
                "report_rules_version": REPORT_RULES_VERSION,
                "explanation_template_version": EXPLANATION_TEMPLATE_VERSION,
            },
            reason_codes=("REPORT_LIMITS_DISCLOSED",),
            limitation_codes=tuple(report_limitations),
            explanation_template_key="report.limits",
            explanation=render_explanation(template_key="report.limits", values={}),
        )
    )
    section_by_key = {section.section_key: section for section in sections}
    if set(section_by_key) != set(SECTION_KEYS):
        raise AssertionError("generated section registry is incomplete")
    return tuple(section_by_key[key] for key in SECTION_KEYS)


def _persist_report(
    session: Session,
    snapshot: _GenerationSnapshot,
    input_fingerprint: str,
) -> PostDraftReportRow:
    coverage = evaluate_starter_coverage(
        starter_slots=snapshot.starter_slots,
        roster=snapshot.roster,
    )
    sections = _build_sections(snapshot, coverage)
    report_id = str(uuid4())
    section_summary = {section.section_key: section.availability for section in sections}
    limitations = sorted(
        {limitation for section in sections for limitation in section.limitation_codes}
    )
    report = PostDraftReportRow(
        id=report_id,
        draft_session_id=snapshot.draft.id,
        draft_revision=snapshot.draft.revision,
        input_fingerprint=input_fingerprint,
        league_shape_fingerprint=snapshot.league_shape_fingerprint,
        report_engine_version=REPORT_ENGINE_VERSION,
        report_rules_version=REPORT_RULES_VERSION,
        explanation_template_version=EXPLANATION_TEMPLATE_VERSION,
        draft_mode=snapshot.draft.mode,
        generated_at=utc_now_text(),
        completed_at=snapshot.draft.completed_at or "",
        section_summary_json=canonical_json(section_summary),
        limitation_codes_json=canonical_json(limitations),
    )
    session.add(report)
    session.flush()

    user_picks = [
        pick for pick in snapshot.picks if pick.selecting_slot == snapshot.draft.user_slot
    ]
    assigned_by_player = {
        assignment.canonical_player_id: assignment.slot_key for assignment in coverage.assignments
    }
    for pick, candidate in zip(user_picks, snapshot.roster_candidates, strict=True):
        session.add(
            PostDraftReportPlayerRow(
                id=str(uuid4()),
                report_id=report_id,
                player_id=candidate.player_id,
                overall_pick=pick.overall_pick,
                round_number=pick.round_number,
                primary_position=candidate.primary_position,
                fantasy_positions_json=canonical_json(list(candidate.fantasy_positions)),
                starter_assignment=assigned_by_player.get(candidate.player_id),
                saved_personal_rank=candidate.manual_rank,
                saved_tier_order=candidate.tier_order,
                saved_favorite=candidate.favorite,
                safe_evidence_json=canonical_json(
                    {
                        "display_name": candidate.display_name,
                        "categorical_evidence": (
                            snapshot.evidence_context.safe_player_evidence(
                                candidate.player_id
                            )
                            if snapshot.evidence_context is not None
                            else {}
                        ),
                    }
                ),
            )
        )
    for section in sections:
        session.add(
            PostDraftReportSectionRow(
                id=str(uuid4()),
                report_id=report_id,
                section_key=section.section_key,
                availability=section.availability,
                confidence=section.confidence,
                metrics_json=canonical_json(section.metrics),
                reason_codes_json=canonical_json(list(section.reason_codes)),
                limitation_codes_json=canonical_json(list(section.limitation_codes)),
                explanation_template_key=section.explanation_template_key,
                explanation=section.explanation,
                safe_provenance_json=canonical_json(section.safe_provenance),
            )
        )
    for moment in snapshot.decision_history.moments():
        session.add(
            PostDraftReportMomentRow(
                id=str(uuid4()),
                report_id=report_id,
                moment_key=moment.moment_key,
                moment_kind=moment.moment_kind,
                overall_pick=moment.overall_pick,
                primary_player_id=moment.primary_player_id,
                secondary_player_id=moment.secondary_player_id,
                safe_summary_json=canonical_json(moment.safe_summary),
                reason_codes_json=canonical_json(list(moment.reason_codes)),
                limitation_codes_json=canonical_json(list(moment.limitation_codes)),
            )
        )
    session.flush()
    return report


def generate_report(
    session: Session,
    session_id: str,
    payload: PostDraftReportGenerateRequest,
) -> PostDraftReportGenerateResponse:
    input_fingerprint = ""
    try:
        snapshot = _load_generation_snapshot(session, session_id, payload)
        input_fingerprint = content_fingerprint(_canonical_input(snapshot))
        existing = session.scalar(
            select(PostDraftReportRow).where(
                PostDraftReportRow.draft_session_id == session_id,
                PostDraftReportRow.input_fingerprint == input_fingerprint,
            )
        )
        if existing is not None:
            logger.info(
                "report.generation.idempotent",
                extra={"report_id": existing.id, "draft_id": session_id},
            )
            return PostDraftReportGenerateResponse(
                idempotent=True,
                report=read_report(session, existing.id),
            )
        report = _persist_report(session, snapshot, input_fingerprint)
        session.commit()
    except HubError:
        session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        if input_fingerprint:
            existing = session.scalar(
                select(PostDraftReportRow).where(
                    PostDraftReportRow.draft_session_id == session_id,
                    PostDraftReportRow.input_fingerprint == input_fingerprint,
                )
            )
            if existing is not None:
                return PostDraftReportGenerateResponse(
                    idempotent=True,
                    report=read_report(session, existing.id),
                )
        raise _error(
            "REPORT_GENERATION_FAILED",
            "The report could not be saved atomically.",
            _ACTION_RETRY_REVISION,
            500,
            retryable=True,
        ) from exc
    except Exception as exc:
        session.rollback()
        raise _error(
            "REPORT_GENERATION_FAILED",
            "The report could not be generated atomically.",
            _ACTION_RETRY_REVISION,
            500,
            retryable=True,
        ) from exc

    logger.info(
        "report.generation.created",
        extra={
            "report_id": report.id,
            "draft_id": session_id,
            "report_engine_version": REPORT_ENGINE_VERSION,
            "report_rules_version": REPORT_RULES_VERSION,
        },
    )
    return PostDraftReportGenerateResponse(
        idempotent=False,
        report=read_report(session, report.id),
    )


def _json_object(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("saved report JSON must be an object")
    return parsed


def _json_list(value: str) -> list[Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("saved report JSON must be a list")
    return parsed


def _summary_read(
    report: PostDraftReportRow,
    draft_name: str,
) -> PostDraftReportSummaryRead:
    return PostDraftReportSummaryRead(
        id=report.id,
        draft_session_id=report.draft_session_id,
        draft_name=draft_name,
        draft_mode=report.draft_mode,  # type: ignore[arg-type]
        draft_revision=report.draft_revision,
        completed_at=report.completed_at,
        generated_at=report.generated_at,
        report_engine_version=report.report_engine_version,
        report_rules_version=report.report_rules_version,
        explanation_template_version=report.explanation_template_version,
        league_shape_fingerprint=report.league_shape_fingerprint,
        section_summary=_json_object(report.section_summary_json),  # type: ignore[arg-type]
        limitations=[str(item) for item in _json_list(report.limitation_codes_json)],
    )


def read_report(session: Session, report_id: str) -> PostDraftReportRead:
    report = session.get(PostDraftReportRow, report_id)
    if report is None:
        raise _error(
            "REPORT_NOT_FOUND",
            "That saved post-draft report could not be found.",
            "Return to the completed draft and choose an available saved report.",
            404,
        )
    draft = session.get(DraftSessionRow, report.draft_session_id)
    if draft is None:
        raise _error(
            "REPORT_NOT_FOUND",
            "That saved post-draft report no longer has its source draft.",
            "Restore the local backup or choose another saved report.",
            404,
        )
    section_rows = tuple(
        session.scalars(
            select(PostDraftReportSectionRow).where(
                PostDraftReportSectionRow.report_id == report.id
            )
        )
    )
    order = {key: index for index, key in enumerate(SECTION_KEYS)}
    section_rows = tuple(
        sorted(section_rows, key=lambda row: (order.get(row.section_key, 999), row.section_key))
    )
    sections = [
        PostDraftReportSectionRead(
            section_key=row.section_key,
            title=SECTION_TITLES.get(row.section_key, row.section_key),
            availability=row.availability,  # type: ignore[arg-type]
            confidence=row.confidence,  # type: ignore[arg-type]
            metrics=_json_object(row.metrics_json),
            reason_codes=[str(item) for item in _json_list(row.reason_codes_json)],
            limitation_codes=[str(item) for item in _json_list(row.limitation_codes_json)],
            explanation_template_key=row.explanation_template_key,
            explanation=row.explanation,
            safe_provenance=_json_object(row.safe_provenance_json),
        )
        for row in section_rows
    ]
    player_rows = tuple(
        session.scalars(
            select(PostDraftReportPlayerRow)
            .where(PostDraftReportPlayerRow.report_id == report.id)
            .order_by(PostDraftReportPlayerRow.overall_pick)
        )
    )
    roster: list[PostDraftReportPlayerRead] = []
    for row in player_rows:
        safe_evidence = _json_object(row.safe_evidence_json)
        display_name = safe_evidence.get("display_name")
        if not isinstance(display_name, str) or not display_name:
            raise _error(
                "REPORT_GENERATION_FAILED",
                "A saved report roster row is incomplete.",
                _ACTION_RESTORE_REPORT,
                500,
            )
        roster.append(
            PostDraftReportPlayerRead(
                player_id=row.player_id,
                display_name=display_name,
                overall_pick=row.overall_pick,
                round_number=row.round_number,
                primary_position=row.primary_position,
                fantasy_positions=[str(item) for item in _json_list(row.fantasy_positions_json)],
                starter_assignment=row.starter_assignment,
                saved_personal_rank=row.saved_personal_rank,
                saved_tier_order=row.saved_tier_order,
                saved_favorite=row.saved_favorite,
            )
        )
    moment_rows = tuple(
        session.scalars(
            select(PostDraftReportMomentRow)
            .where(PostDraftReportMomentRow.report_id == report.id)
        )
    )
    moments = [
        PostDraftReportMomentRead(
            moment_key=row.moment_key,
            moment_kind=row.moment_kind,  # type: ignore[arg-type]
            overall_pick=row.overall_pick,
            primary_player_id=row.primary_player_id,
            secondary_player_id=row.secondary_player_id,
            safe_summary=_json_object(row.safe_summary_json),
            reason_codes=[str(item) for item in _json_list(row.reason_codes_json)],
            limitation_codes=[str(item) for item in _json_list(row.limitation_codes_json)],
        )
        for row in moment_rows
    ]
    moment_kind_order = {
        "strategy_pivot": 0,
        "strategy_guidance": 1,
        "personal_board_choice": 2,
        "alert_event": 3,
    }
    moments.sort(
        key=lambda moment: (
            moment_kind_order.get(moment.moment_kind, 99),
            (
                moment.safe_summary.get("display_order")
                if isinstance(moment.safe_summary.get("display_order"), int)
                else 999
            ),
            moment.overall_pick or 0,
            moment.moment_key,
        )
    )
    summary_section = next(
        (section for section in sections if section.section_key == "draft_summary"),
        None,
    )
    if summary_section is None:
        raise _error(
            "REPORT_GENERATION_FAILED",
            "The saved report summary is incomplete.",
            _ACTION_RESTORE_REPORT,
            500,
        )
    frozen_draft_name = summary_section.metrics.get("draft_name")
    if not isinstance(frozen_draft_name, str) or not frozen_draft_name:
        raise _error(
            "REPORT_GENERATION_FAILED",
            "The saved report draft identity is incomplete.",
            _ACTION_RESTORE_REPORT,
            500,
        )
    return PostDraftReportRead(
        id=report.id,
        draft_session_id=report.draft_session_id,
        draft_name=frozen_draft_name,
        draft_mode=report.draft_mode,  # type: ignore[arg-type]
        draft_revision=report.draft_revision,
        completed_at=report.completed_at,
        generated_at=report.generated_at,
        report_engine_version=report.report_engine_version,
        report_rules_version=report.report_rules_version,
        explanation_template_version=report.explanation_template_version,
        league_shape_fingerprint=report.league_shape_fingerprint,
        summary=summary_section.metrics,
        section_summary=_json_object(report.section_summary_json),  # type: ignore[arg-type]
        sections=sections,
        roster=roster,
        moments=moments,
        limitations=[str(item) for item in _json_list(report.limitation_codes_json)],
        comparison_eligible=True,
        export_available=False,
        available_actions=[],
    )


def list_reports_for_draft(
    session: Session,
    session_id: str,
    *,
    limit: int,
    offset: int,
) -> PostDraftReportListResponse:
    _require_draft(session, session_id)
    total = session.scalar(
        select(func.count())
        .select_from(PostDraftReportRow)
        .where(PostDraftReportRow.draft_session_id == session_id)
    )
    rows = tuple(
        session.scalars(
            select(PostDraftReportRow)
            .where(PostDraftReportRow.draft_session_id == session_id)
            .order_by(
                PostDraftReportRow.completed_at.desc(),
                PostDraftReportRow.generated_at.desc(),
                PostDraftReportRow.id,
            )
            .limit(limit)
            .offset(offset)
        )
    )
    summary_names: dict[str, str] = {}
    if rows:
        summary_rows = tuple(
            session.scalars(
                select(PostDraftReportSectionRow).where(
                    PostDraftReportSectionRow.report_id.in_([row.id for row in rows]),
                    PostDraftReportSectionRow.section_key == "draft_summary",
                )
            )
        )
        for summary_row in summary_rows:
            name = _json_object(summary_row.metrics_json).get("draft_name")
            if isinstance(name, str) and name:
                summary_names[summary_row.report_id] = name
        if any(row.id not in summary_names for row in rows):
            raise _error(
                "REPORT_GENERATION_FAILED",
                "A saved report list entry is missing its frozen draft identity.",
                _ACTION_RESTORE_REPORT,
                500,
            )
    return PostDraftReportListResponse(
        items=[_summary_read(row, summary_names[row.id]) for row in rows],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )
