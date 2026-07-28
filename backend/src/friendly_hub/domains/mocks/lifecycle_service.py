from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.drafts.models import (
    DraftPickRevisionRow,
    DraftPickRow,
    DraftSessionRow,
    DraftTeamRow,
)
from friendly_hub.domains.mocks.engine import normalize_seed
from friendly_hub.domains.mocks.models import MockConfigurationRow
from friendly_hub.domains.mocks.schemas import MockSessionCreate
from friendly_hub.domains.mocks.service import (
    _add_mock_rows,
    _error,
    _user_roster,
)
from friendly_hub.domains.mocks.strategy import evaluate_strategy
from friendly_hub.domains.mocks.strategy_service import (
    _add_guidance_event,
    _current_pick,
    _latest_strategy_revision,
    _update_mock_strategy,
)


def _configuration_for_draft(
    session: Session,
    draft_session_id: str,
) -> MockConfigurationRow | None:
    return session.scalar(
        select(MockConfigurationRow).where(
            MockConfigurationRow.draft_session_id == draft_session_id
        )
    )


def _record_user_roster_guidance(
    session: Session,
    *,
    draft_row: DraftSessionRow,
    configuration: MockConfigurationRow,
    event_kind: str,
) -> None:
    strategy_revision = _latest_strategy_revision(session, configuration.id)
    current = _current_pick(session, draft_row.id)
    effective_pick = (
        current.overall_pick
        if current is not None
        else draft_row.team_count * draft_row.round_count
    )
    roster = _user_roster(session, draft_row)
    evaluation = evaluate_strategy(
        strategy_key=configuration.current_strategy_key,
        round_count=draft_row.round_count,
        team_count=draft_row.team_count,
        effective_overall_pick=effective_pick,
        roster=roster,
        league_shape=json.loads(configuration.league_shape_json),
    )
    _add_guidance_event(
        session,
        configuration=configuration,
        strategy_revision=strategy_revision,
        effective_overall_pick=effective_pick,
        evaluation=evaluation,
        event_kind=event_kind,
        now=utc_now_text(),
    )


def _advance_mock_after_draft_mutation(
    session: Session,
    *,
    draft_row: DraftSessionRow,
    pick: DraftPickRow,
    pick_revision: DraftPickRevisionRow,
    event_kind: str,
) -> None:
    configuration = _configuration_for_draft(session, draft_row.id)
    if configuration is None:
        return
    expected_mock_revision = configuration.revision
    if pick.selecting_slot == draft_row.user_slot:
        _record_user_roster_guidance(
            session,
            draft_row=draft_row,
            configuration=configuration,
            event_kind=(
                f"user-{event_kind}-revision-"
                f"{pick_revision.session_revision}"
            ),
        )
    _update_mock_strategy(
        session,
        configuration,
        expected_revision=expected_mock_revision,
        strategy_key=None,
        now=utc_now_text(),
    )


def record_mock_correction_in_transaction(
    session: Session,
    *,
    draft_row: DraftSessionRow,
    pick: DraftPickRow,
    pick_revision: DraftPickRevisionRow,
) -> None:
    _advance_mock_after_draft_mutation(
        session,
        draft_row=draft_row,
        pick=pick,
        pick_revision=pick_revision,
        event_kind="correction",
    )


def record_mock_undo_in_transaction(
    session: Session,
    *,
    draft_row: DraftSessionRow,
    pick: DraftPickRow,
    pick_revision: DraftPickRevisionRow,
) -> None:
    _advance_mock_after_draft_mutation(
        session,
        draft_row=draft_row,
        pick=pick,
        pick_revision=pick_revision,
        event_kind="undo",
    )


def reset_mock_in_transaction(
    session: Session,
    *,
    source_draft: DraftSessionRow,
    replacement_draft: DraftSessionRow,
    replacement_seed: str | None,
) -> None:
    source_configuration = _configuration_for_draft(session, source_draft.id)
    if source_configuration is None:
        return
    try:
        seed = (
            normalize_seed(replacement_seed)
            if replacement_seed is not None
            else source_configuration.seed
        )
    except ValueError as exc:
        raise _error(
            "MOCK.INVALID_SEED",
            "The replacement seed must be an unsigned 64-bit whole number.",
            "Use digits from 0 through 18446744073709551615.",
            422,
        ) from exc

    team_names = [
        row.display_name
        for row in session.scalars(
            select(DraftTeamRow)
            .where(DraftTeamRow.session_id == replacement_draft.id)
            .order_by(DraftTeamRow.draft_slot)
        )
    ]
    payload = MockSessionCreate(
        name=replacement_draft.name,
        league_profile_id=replacement_draft.league_profile_id,
        draft_format=replacement_draft.draft_format,
        third_round_reversal=replacement_draft.third_round_reversal,
        team_count=replacement_draft.team_count,
        round_count=replacement_draft.round_count,
        user_slot=replacement_draft.user_slot,
        pick_timer_seconds=replacement_draft.pick_timer_seconds,
        team_names=team_names,
        seed=seed,
        randomness=source_configuration.randomness,
        strategy_key=source_configuration.current_strategy_key,
        include_in_learning=False,
    )
    _add_mock_rows(
        session,
        replacement_draft,
        payload,
        copy_from_configuration=source_configuration,
    )
    _update_mock_strategy(
        session,
        source_configuration,
        expected_revision=source_configuration.revision,
        strategy_key=None,
        now=utc_now_text(),
    )
