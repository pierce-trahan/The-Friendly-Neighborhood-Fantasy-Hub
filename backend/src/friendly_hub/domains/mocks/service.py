from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from friendly_hub.core.errors import HubError
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.drafts.models import (
    DraftCandidateRow,
    DraftPickRow,
    DraftSessionRow,
)
from friendly_hub.domains.drafts.schemas import DraftSessionCreate
from friendly_hub.domains.drafts.service import (
    create_session_in_transaction,
    read_session,
)
from friendly_hub.domains.leagues.models import LeagueProfileRow
from friendly_hub.domains.leagues.schemas import LeagueProfileDocument
from friendly_hub.domains.mocks.definitions import (
    CPU_ENGINE_VERSION,
    RNG_VERSION,
    STRATEGY_DEFINITION_VERSION,
)
from friendly_hub.domains.mocks.engine import (
    content_fingerprint,
    fallback_archetype_for_slot,
)
from friendly_hub.domains.mocks.models import (
    MockConfigurationRow,
    MockCpuProfileRow,
    MockGuidanceEventRow,
    MockStrategyRevisionRow,
)
from friendly_hub.domains.mocks.schemas import (
    MockConfigurationRead,
    MockCpuProfileRead,
    MockGuidanceRead,
    MockSessionCreate,
    MockSessionRead,
    MockStrategyRevisionRead,
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


def _candidate_snapshot(
    session: Session,
    draft_session_id: str,
) -> list[dict[str, object]]:
    rows = list(
        session.scalars(
            select(DraftCandidateRow).where(
                DraftCandidateRow.session_id == draft_session_id
            )
        )
    )
    ordered = sorted(
        rows,
        key=lambda row: (
            row.manual_rank is None,
            row.manual_rank if row.manual_rank is not None else 0,
            row.search_name,
            row.player_id,
        ),
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
            "tier_order": row.tier_order,
        }
        for index, row in enumerate(ordered)
    ]


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
) -> list[dict[str, object]]:
    return [
        {
            "draft_slot": slot,
            "source": "fallback",
            "archetype_key": payload.fallback_archetypes.get(
                slot, fallback_archetype_for_slot(payload.seed, slot)
            ),
            "confidence": "not_applicable",
            "draft_sample_count": 0,
            "pick_sample_count": 0,
        }
        for slot in range(1, payload.team_count + 1)
        if slot != payload.user_slot
    ]


def _add_mock_rows(
    session: Session,
    draft_row: DraftSessionRow,
    payload: MockSessionCreate,
) -> MockConfigurationRow:
    candidate_snapshot = _candidate_snapshot(session, draft_row.id)
    if len(candidate_snapshot) < 2:
        raise _error(
            "MOCK.CANDIDATES_INSUFFICIENT",
            "A mock draft needs at least two frozen candidates.",
            "Add or import more relevant players, then create the mock again.",
            409,
        )

    league_row = (
        session.get(LeagueProfileRow, payload.league_profile_id)
        if payload.league_profile_id
        else None
    )
    league_shape, league_shape_source_timestamp = _normalize_league_shape(
        league_row,
        team_count=payload.team_count,
    )
    _validate_strategy_compatibility(payload.strategy_key, league_shape)
    profile_snapshot = _profile_snapshot(payload)
    fingerprint = content_fingerprint(
        {
            "candidates": candidate_snapshot,
            "draft_order": _draft_order_snapshot(session, draft_row.id),
            "league_shape": league_shape,
            "profiles": profile_snapshot,
        }
    )
    now = utc_now_text()
    configuration = MockConfigurationRow(
        id=str(uuid4()),
        draft_session_id=draft_row.id,
        seed=payload.seed,
        rng_version=RNG_VERSION,
        cpu_engine_version=CPU_ENGINE_VERSION,
        strategy_definition_version=STRATEGY_DEFINITION_VERSION,
        league_shape_json=_json(league_shape),
        league_shape_source_timestamp=league_shape_source_timestamp,
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
                source="fallback",
                archetype_key=profile["archetype_key"],
                confidence="not_applicable",
                draft_sample_count=0,
                pick_sample_count=0,
                tendency_snapshot_json=_json(
                    {
                        "archetype_key": profile["archetype_key"],
                        "source": "fallback",
                    }
                ),
                internal_manager_reference=None,
                source_timestamp=now,
                created_at=now,
            )
        )

    limitations = _strategy_limitations(payload.strategy_key, league_shape)
    missing_timeline_evidence = "TIMELINE_EVIDENCE_UNAVAILABLE" in limitations
    guidance = MockGuidanceEventRow(
        id=str(uuid4()),
        mock_configuration_id=configuration.id,
        strategy_revision_id=strategy_revision.id,
        deterministic_event_key=(
            f"{STRATEGY_DEFINITION_VERSION}:{payload.strategy_key}:initial:1"
        ),
        effective_overall_pick=1,
        state="insufficient_evidence" if missing_timeline_evidence else "on_plan",
        confidence="low" if limitations else "medium",
        observed_counts_json="{}",
        target_ranges_json=_json({"checkpoint": "initial"}),
        reason_codes_json=_json(["STRATEGY_REHEARSAL_STARTED"]),
        limitation_codes_json=_json(limitations),
        explanation_template_key=f"{payload.strategy_key}.initial",
        pivot_template_key=None,
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
        _add_mock_rows(session, draft_row, payload)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return read_mock_session(session, draft_row.id)


def _guidance_read(row: MockGuidanceEventRow) -> MockGuidanceRead:
    return MockGuidanceRead(
        id=row.id,
        effective_overall_pick=row.effective_overall_pick,
        state=row.state,
        confidence=row.confidence,
        observed_counts=json.loads(row.observed_counts_json),
        target_ranges=json.loads(row.target_ranges_json),
        reason_codes=json.loads(row.reason_codes_json),
        limitation_codes=json.loads(row.limitation_codes_json),
        explanation_template_key=row.explanation_template_key,
        pivot_template_key=row.pivot_template_key,
        status=row.status,
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )


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
    strategy_revision = session.scalar(
        select(MockStrategyRevisionRow)
        .where(
            MockStrategyRevisionRow.mock_configuration_id == configuration.id
        )
        .order_by(MockStrategyRevisionRow.sequence_number.desc())
        .limit(1)
    )
    profiles = list(
        session.scalars(
            select(MockCpuProfileRow)
            .where(MockCpuProfileRow.mock_configuration_id == configuration.id)
            .order_by(MockCpuProfileRow.draft_slot)
        )
    )
    guidance_rows = list(
        session.scalars(
            select(MockGuidanceEventRow)
            .where(MockGuidanceEventRow.mock_configuration_id == configuration.id)
            .order_by(
                MockGuidanceEventRow.effective_overall_pick.desc(),
                MockGuidanceEventRow.created_at.desc(),
            )
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
    guidance = [_guidance_read(row) for row in guidance_rows]
    roster_counts = json.loads(strategy_revision.user_roster_counts_json)
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
            revision=configuration.revision,
            include_in_learning=configuration.include_in_learning,
            learning_opted_in_at=configuration.learning_opted_in_at,
            learning_withdrawn_at=configuration.learning_withdrawn_at,
            created_at=configuration.created_at,
            updated_at=configuration.updated_at,
        ),
        current_strategy_revision=MockStrategyRevisionRead(
            sequence_number=strategy_revision.sequence_number,
            previous_strategy_key=strategy_revision.previous_strategy_key,
            next_strategy_key=strategy_revision.next_strategy_key,
            effective_overall_pick=strategy_revision.effective_overall_pick,
            user_roster_counts=roster_counts,
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
        can_advance_cpu=bool(
            draft.status == "active"
            and draft.current_pick
            and draft.current_pick.selecting_slot != draft.user_slot
        ),
        recovery_guidance=draft.recovery_guidance,
    )
