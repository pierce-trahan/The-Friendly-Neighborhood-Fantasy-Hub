from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from friendly_hub.core.errors import HubError
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.alerts.evaluation_service import read_draft_alert
from friendly_hub.domains.alerts.models import (
    DraftAlertConfigurationRow,
    DraftAlertEventRow,
)
from friendly_hub.domains.alerts.schemas import (
    AlertDetailRead,
    DraftAlertEventStatusPatch,
)
from friendly_hub.domains.drafts.models import DraftPickRow, DraftSessionRow


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
            "Attach compatible committed evidence before changing alerts.",
            status_code=404,
        )
    return configuration


def _require_event(
    session: Session,
    *,
    configuration_id: str,
    alert_id: str,
) -> DraftAlertEventRow:
    event = session.get(DraftAlertEventRow, alert_id)
    if event is None or event.configuration_id != configuration_id:
        raise _error(
            "ALERT_EVENT_NOT_FOUND",
            "That alert event does not exist for this draft.",
            "Choose an event from the draft alert list.",
            status_code=404,
        )
    return event


def _stale_status(message: str, action: str) -> HubError:
    return _error(
        "ALERT_EVENT_STALE_STATUS",
        message,
        action,
        status_code=409,
    )


def _snooze_boundary(
    session: Session,
    *,
    draft: DraftSessionRow,
    pick_count: int,
) -> int:
    if draft.status not in {"active", "paused"}:
        raise _stale_status(
            "Only an active or paused draft alert can be snoozed.",
            "Inspect completed history or reopen another current alert.",
        )
    unmade = list(
        session.scalars(
            select(DraftPickRow)
            .where(
                DraftPickRow.session_id == draft.id,
                DraftPickRow.player_id.is_(None),
            )
            .order_by(DraftPickRow.overall_pick)
        )
    )
    if not unmade:
        raise _stale_status(
            "This draft has no remaining picks for a snooze boundary.",
            "Inspect the completed alert history.",
        )
    current = unmade[0].overall_pick
    future_user = next(
        (
            pick.overall_pick
            for pick in unmade
            if pick.selecting_slot == draft.user_slot and pick.overall_pick > current
        ),
        None,
    )
    saved_pick_boundary = min(
        current + pick_count,
        (draft.team_count * draft.round_count) + 1,
    )
    return min(saved_pick_boundary, future_user) if future_user is not None else saved_pick_boundary


def _lock_rows(
    session: Session,
    *,
    draft: DraftSessionRow,
    configuration: DraftAlertConfigurationRow,
    event: DraftAlertEventRow,
    expected_status: str,
    values: dict[str, object],
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
    event_result = session.execute(
        update(DraftAlertEventRow)
        .where(
            DraftAlertEventRow.id == event.id,
            DraftAlertEventRow.status == expected_status,
            DraftAlertEventRow.updated_at == event.updated_at,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if (
        draft_result.rowcount != 1
        or configuration_result.rowcount != 1
        or event_result.rowcount != 1
    ):
        session.rollback()
        raise _stale_status(
            "The draft, configuration, or alert changed before the status update.",
            "Refresh the alert history and retry its current status.",
        )


def _commit_transaction(session: Session) -> None:
    session.commit()


def update_draft_alert_status(
    session: Session,
    *,
    session_id: str,
    alert_id: str,
    payload: DraftAlertEventStatusPatch,
) -> AlertDetailRead:
    draft = _require_draft(session, session_id)
    configuration = _require_configuration(session, session_id)
    event = _require_event(
        session,
        configuration_id=configuration.id,
        alert_id=alert_id,
    )
    if configuration.revision != payload.configuration_revision:
        raise _error(
            "ALERT_CONFIGURATION_STALE_REVISION",
            (
                "The alert configuration changed before this status update "
                f"(expected revision {payload.configuration_revision}, current "
                f"revision {configuration.revision})."
            ),
            "Refresh the configuration and retry.",
            status_code=409,
        )
    if event.status != payload.expected_status:
        raise _stale_status(
            (
                "The alert status changed before this update "
                f"(expected {payload.expected_status}, current {event.status})."
            ),
            "Refresh the alert history and retry its current status.",
        )
    if draft.status == "reset":
        raise _stale_status(
            "A reset draft's alert history is read-only.",
            "Inspect the history or open its replacement draft.",
        )
    if event.status == "superseded":
        raise _stale_status(
            "A superseded alert is permanent read-only history.",
            "Choose a current dismissed or snoozed event to reopen.",
        )
    if event.status == payload.status:
        raise _stale_status(
            f"The alert is already {payload.status}.",
            "Choose a different lifecycle action.",
        )
    allowed = {
        ("open", "dismissed"),
        ("open", "snoozed"),
        ("dismissed", "open"),
        ("snoozed", "open"),
    }
    if (event.status, payload.status) not in allowed:
        raise _stale_status(
            f"An alert cannot change from {event.status} to {payload.status}.",
            "Reopen it before choosing another suppression action.",
        )

    now = utc_now_text()
    values: dict[str, object] = {
        "status": payload.status,
        "updated_at": now,
    }
    if payload.status == "dismissed":
        values.update(
            dismissed_at=now,
            snooze_boundary=None,
        )
    elif payload.status == "snoozed":
        values.update(
            dismissed_at=None,
            snooze_boundary=_snooze_boundary(
                session,
                draft=draft,
                pick_count=configuration.snooze_pick_count,
            ),
        )
    else:
        values.update(
            dismissed_at=None,
            snooze_boundary=None,
        )

    try:
        _lock_rows(
            session,
            draft=draft,
            configuration=configuration,
            event=event,
            expected_status=payload.expected_status,
            values=values,
        )
        _commit_transaction(session)
    except HubError:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        raise _error(
            "ALERT_EVALUATION_FAILED",
            "The alert status could not be saved.",
            "Refresh the alert history and retry the lifecycle action.",
            status_code=500,
        ) from exc
    session.expire_all()
    return read_draft_alert(
        session,
        session_id=session_id,
        alert_id=alert_id,
    )
