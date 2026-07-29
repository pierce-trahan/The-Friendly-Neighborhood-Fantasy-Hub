from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from friendly_hub.core.errors import HubError
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.alerts.definitions import (
    ALERT_ENGINE_VERSION,
    ALERT_FRESHNESS_POLICY_VERSION,
    ALERT_RULE_VERSION,
    FormatCompatibility,
)
from friendly_hub.domains.alerts.models import (
    AlertEvidenceSnapshotRow,
    DraftAlertConfigurationRevisionRow,
    DraftAlertConfigurationRow,
)
from friendly_hub.domains.alerts.schemas import (
    DraftAlertConfigurationCreate,
    DraftAlertConfigurationPatch,
    DraftAlertConfigurationRead,
)
from friendly_hub.domains.alerts.service import read_alert_evidence_snapshot
from friendly_hub.domains.drafts.models import DraftSessionRow
from friendly_hub.domains.leagues.models import LeagueProfileRow
from friendly_hub.domains.leagues.schemas import LeagueProfileDocument


@dataclass(frozen=True)
class CompatibilityAssessment:
    state: FormatCompatibility
    reasons: tuple[str, ...]


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
        action=f"{action} Draft picks and existing alert history remain unchanged.",
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


def _require_configurable_draft(draft: DraftSessionRow) -> None:
    if draft.status not in {"active", "paused"}:
        raise _error(
            "ALERT_DRAFT_NOT_CONFIGURABLE",
            "Alert configuration can change only on an active or paused draft.",
            "Open an active draft, or inspect this draft's saved configuration.",
            status_code=409,
        )


def _require_draft_revision(draft: DraftSessionRow, expected: int) -> None:
    if draft.revision != expected:
        raise _error(
            "ALERT_DRAFT_STALE_REVISION",
            (
                "The draft changed before the alert configuration could be "
                f"saved (expected revision {expected}, current revision "
                f"{draft.revision})."
            ),
            "Refresh the draft and submit its current revision.",
            status_code=409,
        )


def _lock_draft_revision(
    session: Session,
    *,
    session_id: str,
    expected_revision: int,
) -> None:
    result = session.execute(
        update(DraftSessionRow)
        .where(
            DraftSessionRow.id == session_id,
            DraftSessionRow.revision == expected_revision,
        )
        .values(updated_at=DraftSessionRow.updated_at)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.rollback()
        current = session.get(DraftSessionRow, session_id)
        current_revision = current.revision if current is not None else "missing"
        raise _error(
            "ALERT_DRAFT_STALE_REVISION",
            (
                "The draft changed before the alert configuration could be "
                f"saved (expected revision {expected_revision}, current "
                f"revision {current_revision})."
            ),
            "Refresh the draft and submit its current revision.",
            status_code=409,
        )


def _require_snapshot(
    session: Session,
    snapshot_id: str,
) -> AlertEvidenceSnapshotRow:
    snapshot = session.get(AlertEvidenceSnapshotRow, snapshot_id)
    if snapshot is None or snapshot.status != "committed":
        raise _error(
            "ALERT_EVIDENCE_NOT_FOUND",
            "That committed alert-evidence snapshot is not available.",
            "Choose a committed snapshot from the local evidence list.",
            status_code=404,
        )
    return snapshot


def _draft_profile_facts(
    session: Session,
    draft: DraftSessionRow,
) -> tuple[dict[str, object | None], list[str]]:
    facts: dict[str, object | None] = {
        "league_type": None,
        "draft_purpose": None,
        "team_count": draft.team_count,
        "draft_format": draft.draft_format,
        "third_round_reversal": draft.third_round_reversal,
        "rounds": draft.round_count,
        "qb_mode": None,
        "reception_scoring": None,
        "te_premium": None,
    }
    missing: list[str] = []
    profile = (
        session.get(LeagueProfileRow, draft.league_profile_id) if draft.league_profile_id else None
    )
    if profile is None:
        return facts, [
            "LEAGUE_TYPE_UNKNOWN",
            "DRAFT_PURPOSE_UNKNOWN",
            "QUARTERBACK_MODE_UNKNOWN",
            "RECEPTION_SCORING_UNKNOWN",
            "TIGHT_END_PREMIUM_UNKNOWN",
        ]

    try:
        document = LeagueProfileDocument.model_validate_json(profile.payload_json)
    except ValueError:
        return facts, ["LEAGUE_PROFILE_INVALID"]

    if document.league.league_type != "unknown":
        facts["league_type"] = document.league.league_type
    else:
        missing.append("LEAGUE_TYPE_UNKNOWN")

    matching_drafts = [item for item in document.drafts if item.get("format") == draft.draft_format]
    purposes = {
        item.get("purpose")
        for item in matching_drafts
        if item.get("purpose") in {"startup", "rookie", "supplemental"}
    }
    if len(purposes) == 1:
        facts["draft_purpose"] = purposes.pop()
    else:
        missing.append("DRAFT_PURPOSE_UNKNOWN")

    starters = document.roster.get("starters")
    if isinstance(starters, list):
        has_superflex = any(
            isinstance(item, dict)
            and (
                item.get("slot") == "SUPER_FLEX"
                or "QB" in (item.get("eligible_positions") or [])
                and item.get("slot") not in {"QB", "BENCH"}
            )
            for item in starters
        )
        facts["qb_mode"] = "superflex" if has_superflex else "one_qb"
    else:
        missing.append("QUARTERBACK_MODE_UNKNOWN")

    rules = document.scoring.get("rules")
    if isinstance(rules, list):
        reception_rules = [
            item
            for item in rules
            if isinstance(item, dict)
            and item.get("normalized_stat") == "reception"
            and isinstance(item.get("points"), (int, float))
        ]
        if len(reception_rules) == 1:
            points = float(reception_rules[0]["points"])
            scoring_by_points = {
                0.0: "standard",
                0.5: "half_ppr",
                1.0: "ppr",
            }
            facts["reception_scoring"] = scoring_by_points.get(points)
        if facts["reception_scoring"] is None:
            missing.append("RECEPTION_SCORING_UNKNOWN")

        facts["te_premium"] = any(
            isinstance(item, dict)
            and item.get("rule_kind") == "bonus"
            and isinstance(item.get("points"), (int, float))
            and float(item["points"]) > 0
            and "TE" in (item.get("position_scope") or [])
            for item in rules
        )
    else:
        missing.extend(["RECEPTION_SCORING_UNKNOWN", "TIGHT_END_PREMIUM_UNKNOWN"])
    return facts, sorted(set(missing))


def assess_snapshot_compatibility(
    session: Session,
    *,
    draft: DraftSessionRow,
    snapshot: AlertEvidenceSnapshotRow,
) -> CompatibilityAssessment:
    draft_facts, missing = _draft_profile_facts(session, draft)
    try:
        source = json.loads(snapshot.format_json)
    except (TypeError, json.JSONDecodeError):
        missing.append("EVIDENCE_FORMAT_UNKNOWN")
        source = {}

    required_source_fields = {
        "league_type",
        "draft_purpose",
        "team_count",
        "draft_format",
        "third_round_reversal",
        "rounds",
        "qb_mode",
        "reception_scoring",
        "te_premium",
    }
    missing.extend(
        f"EVIDENCE_{name.upper()}_UNKNOWN"
        for name in sorted(required_source_fields)
        if name not in source or source[name] is None
    )
    if missing:
        return CompatibilityAssessment("unknown", tuple(sorted(set(missing))))

    critical_fields = {
        "league_type": "LEAGUE_TYPE_DIFFERS",
        "draft_purpose": "DRAFT_PURPOSE_DIFFERS",
        "draft_format": "DRAFT_FORMAT_DIFFERS",
        "third_round_reversal": "THIRD_ROUND_REVERSAL_DIFFERS",
        "qb_mode": "QUARTERBACK_MODE_DIFFERS",
        "reception_scoring": "RECEPTION_SCORING_DIFFERS",
    }
    critical_differences = [
        code
        for field_name, code in critical_fields.items()
        if source[field_name] != draft_facts[field_name]
    ]
    draft_depth = draft.team_count * draft.round_count
    if snapshot.supported_draft_depth < draft_depth:
        critical_differences.append("SUPPORTED_DRAFT_DEPTH_TOO_SHALLOW")
    if critical_differences:
        return CompatibilityAssessment(
            "incompatible",
            tuple(sorted(critical_differences)),
        )

    shape_differences: list[str] = []
    if source["team_count"] != draft.team_count:
        shape_differences.append("TEAM_COUNT_DIFFERS")
    if source["rounds"] != draft.round_count:
        shape_differences.append("ROUND_COUNT_DIFFERS")
    modifier_differences = []
    if source["te_premium"] != draft_facts["te_premium"]:
        modifier_differences.append("TIGHT_END_PREMIUM_DIFFERS")

    reasons = tuple(sorted(shape_differences + modifier_differences))
    if modifier_differences:
        return CompatibilityAssessment("partial", reasons)
    if shape_differences:
        return CompatibilityAssessment("family", reasons)
    return CompatibilityAssessment("exact", ())


def _require_compatible(assessment: CompatibilityAssessment) -> None:
    if assessment.state not in {"exact", "family", "partial"}:
        reason_text = ", ".join(assessment.reasons) or "format facts unavailable"
        raise _error(
            "ALERT_EVIDENCE_INCOMPATIBLE",
            (
                "The evidence snapshot cannot be attached to this frozen draft "
                f"format ({assessment.state}: {reason_text})."
            ),
            "Choose evidence marked exact, family, or partial for this draft.",
            status_code=409,
        )


def _settings(configuration: DraftAlertConfigurationRow) -> dict[str, object]:
    return {
        "eligible_tier_count": configuration.eligible_tier_count,
        "enabled": configuration.enabled,
        "engine_version": configuration.engine_version,
        "freshness_policy_version": configuration.freshness_policy_version,
        "minimum_conservative_gap": configuration.minimum_conservative_gap,
        "personal_qualifier_mode": configuration.personal_qualifier_mode,
        "rule_version": configuration.rule_version,
        "snooze_pick_count": configuration.snooze_pick_count,
    }


def _settings_json(settings: dict[str, object]) -> str:
    return json.dumps(settings, separators=(",", ":"), sort_keys=True)


def copy_alert_configuration_on_reset_in_transaction(
    session: Session,
    *,
    source_draft: DraftSessionRow,
    replacement_draft: DraftSessionRow,
) -> DraftAlertConfigurationRow | None:
    source = session.scalar(
        select(DraftAlertConfigurationRow).where(
            DraftAlertConfigurationRow.draft_session_id == source_draft.id
        )
    )
    if source is None:
        return None
    now = utc_now_text()
    copied = DraftAlertConfigurationRow(
        id=str(uuid4()),
        draft_session_id=replacement_draft.id,
        evidence_snapshot_id=source.evidence_snapshot_id,
        enabled=source.enabled,
        personal_qualifier_mode=source.personal_qualifier_mode,
        eligible_tier_count=source.eligible_tier_count,
        minimum_conservative_gap=source.minimum_conservative_gap,
        snooze_pick_count=source.snooze_pick_count,
        engine_version=source.engine_version,
        rule_version=source.rule_version,
        freshness_policy_version=source.freshness_policy_version,
        revision=0,
        created_at=now,
        updated_at=now,
    )
    settings_json = _settings_json(_settings(source))
    revision = DraftAlertConfigurationRevisionRow(
        id=str(uuid4()),
        configuration_id=copied.id,
        sequence_number=1,
        previous_evidence_snapshot_id=source.evidence_snapshot_id,
        next_evidence_snapshot_id=source.evidence_snapshot_id,
        previous_settings_json=settings_json,
        next_settings_json=settings_json,
        reason="reset_copy",
        created_at=now,
    )
    session.add(copied)
    session.flush()
    session.add(revision)
    return copied


def _commit_transaction(session: Session) -> None:
    session.commit()


def _read_configuration(
    session: Session,
    *,
    draft: DraftSessionRow,
    configuration: DraftAlertConfigurationRow,
) -> DraftAlertConfigurationRead:
    snapshot = _require_snapshot(session, configuration.evidence_snapshot_id)
    assessment = assess_snapshot_compatibility(
        session,
        draft=draft,
        snapshot=snapshot,
    )
    evidence = read_alert_evidence_snapshot(session, snapshot.id).model_copy(
        update={"compatibility_state": assessment.state}
    )
    return DraftAlertConfigurationRead(
        id=configuration.id,
        draft_session_id=draft.id,
        draft_revision=draft.revision,
        evidence_snapshot_id=snapshot.id,
        enabled=configuration.enabled,
        personal_qualifier_mode=configuration.personal_qualifier_mode,
        eligible_tier_count=configuration.eligible_tier_count,
        minimum_conservative_gap=configuration.minimum_conservative_gap,
        snooze_pick_count=configuration.snooze_pick_count,
        engine_version=configuration.engine_version,
        rule_version=configuration.rule_version,
        freshness_policy_version=configuration.freshness_policy_version,
        revision=configuration.revision,
        format_compatibility=assessment.state,
        compatibility_reasons=list(assessment.reasons),
        evidence_snapshot=evidence,
        created_at=configuration.created_at,
        updated_at=configuration.updated_at,
    )


def create_draft_alert_configuration(
    session: Session,
    *,
    session_id: str,
    payload: DraftAlertConfigurationCreate,
) -> DraftAlertConfigurationRead:
    draft = _require_draft(session, session_id)
    _require_configurable_draft(draft)
    _require_draft_revision(draft, payload.draft_revision)
    existing = session.scalar(
        select(DraftAlertConfigurationRow).where(
            DraftAlertConfigurationRow.draft_session_id == session_id
        )
    )
    if existing is not None:
        raise _error(
            "ALERT_CONFIGURATION_EXISTS",
            "This draft already has an alert configuration.",
            "Refresh it and use the guarded update route.",
            status_code=409,
        )

    snapshot = _require_snapshot(session, payload.evidence_snapshot_id)
    assessment = assess_snapshot_compatibility(
        session,
        draft=draft,
        snapshot=snapshot,
    )
    _require_compatible(assessment)

    now = utc_now_text()
    configuration = DraftAlertConfigurationRow(
        id=str(uuid4()),
        draft_session_id=session_id,
        evidence_snapshot_id=snapshot.id,
        enabled=payload.enabled,
        personal_qualifier_mode=payload.personal_qualifier_mode,
        eligible_tier_count=payload.eligible_tier_count,
        minimum_conservative_gap=payload.minimum_conservative_gap,
        snooze_pick_count=payload.snooze_pick_count,
        engine_version=ALERT_ENGINE_VERSION,
        rule_version=ALERT_RULE_VERSION,
        freshness_policy_version=ALERT_FRESHNESS_POLICY_VERSION,
        revision=0,
        created_at=now,
        updated_at=now,
    )
    revision = DraftAlertConfigurationRevisionRow(
        id=str(uuid4()),
        configuration_id=configuration.id,
        sequence_number=1,
        previous_evidence_snapshot_id=None,
        next_evidence_snapshot_id=snapshot.id,
        previous_settings_json=None,
        next_settings_json=_settings_json(_settings(configuration)),
        reason="initial",
        created_at=now,
    )
    try:
        _lock_draft_revision(
            session,
            session_id=session_id,
            expected_revision=payload.draft_revision,
        )
        session.add(configuration)
        session.flush()
        session.add(revision)
        _commit_transaction(session)
    except HubError:
        raise
    except Exception as exc:
        session.rollback()
        raise _error(
            "ALERT_CONFIGURATION_SAVE_FAILED",
            "The alert configuration could not be saved.",
            "Refresh the draft and try the attachment again.",
            status_code=500,
        ) from exc
    return _read_configuration(
        session,
        draft=_require_draft(session, session_id),
        configuration=configuration,
    )


def read_draft_alert_configuration(
    session: Session,
    *,
    session_id: str,
) -> DraftAlertConfigurationRead:
    draft = _require_draft(session, session_id)
    configuration = session.scalar(
        select(DraftAlertConfigurationRow).where(
            DraftAlertConfigurationRow.draft_session_id == session_id
        )
    )
    if configuration is None:
        raise _error(
            "ALERT_CONFIGURATION_NOT_FOUND",
            "This draft does not have an alert configuration.",
            "Attach a compatible committed evidence snapshot first.",
            status_code=404,
        )
    return _read_configuration(
        session,
        draft=draft,
        configuration=configuration,
    )


def update_draft_alert_configuration(
    session: Session,
    *,
    session_id: str,
    payload: DraftAlertConfigurationPatch,
) -> DraftAlertConfigurationRead:
    draft = _require_draft(session, session_id)
    _require_configurable_draft(draft)
    _require_draft_revision(draft, payload.draft_revision)
    configuration = session.scalar(
        select(DraftAlertConfigurationRow).where(
            DraftAlertConfigurationRow.draft_session_id == session_id
        )
    )
    if configuration is None:
        raise _error(
            "ALERT_CONFIGURATION_NOT_FOUND",
            "This draft does not have an alert configuration.",
            "Attach a compatible committed evidence snapshot first.",
            status_code=404,
        )
    if configuration.revision != payload.configuration_revision:
        raise _error(
            "ALERT_CONFIGURATION_STALE_REVISION",
            (
                "The alert configuration changed before this update "
                f"(expected revision {payload.configuration_revision}, current "
                f"revision {configuration.revision})."
            ),
            "Refresh the configuration and submit its current revision.",
            status_code=409,
        )

    previous_settings = _settings(configuration)
    next_snapshot_id = payload.evidence_snapshot_id or configuration.evidence_snapshot_id
    replacing_snapshot = next_snapshot_id != configuration.evidence_snapshot_id
    next_snapshot = _require_snapshot(session, next_snapshot_id)
    assessment = assess_snapshot_compatibility(
        session,
        draft=draft,
        snapshot=next_snapshot,
    )
    if replacing_snapshot:
        _require_compatible(assessment)

    mutable_fields = (
        "enabled",
        "personal_qualifier_mode",
        "eligible_tier_count",
        "minimum_conservative_gap",
        "snooze_pick_count",
    )
    changes = payload.model_dump(exclude_none=True)
    next_values = {
        field_name: changes.get(field_name, getattr(configuration, field_name))
        for field_name in mutable_fields
    }
    next_settings = {
        **previous_settings,
        **next_values,
    }
    settings_changed = next_settings != previous_settings
    if not replacing_snapshot and not settings_changed:
        raise _error(
            "ALERT_CONFIGURATION_UNCHANGED",
            "The submitted alert configuration matches the saved configuration.",
            "Change a setting or choose a different compatible snapshot.",
            status_code=409,
        )

    now = utc_now_text()
    next_revision = configuration.revision + 1
    revision = DraftAlertConfigurationRevisionRow(
        id=str(uuid4()),
        configuration_id=configuration.id,
        sequence_number=next_revision + 1,
        previous_evidence_snapshot_id=configuration.evidence_snapshot_id,
        next_evidence_snapshot_id=next_snapshot_id,
        previous_settings_json=_settings_json(previous_settings),
        next_settings_json=_settings_json(next_settings),
        reason="snapshot_replaced" if replacing_snapshot else "settings_changed",
        created_at=now,
    )
    try:
        _lock_draft_revision(
            session,
            session_id=session_id,
            expected_revision=payload.draft_revision,
        )
        result = session.execute(
            update(DraftAlertConfigurationRow)
            .where(
                DraftAlertConfigurationRow.id == configuration.id,
                DraftAlertConfigurationRow.revision == payload.configuration_revision,
            )
            .values(
                evidence_snapshot_id=next_snapshot_id,
                revision=next_revision,
                updated_at=now,
                **next_values,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            session.rollback()
            raise _error(
                "ALERT_CONFIGURATION_STALE_REVISION",
                "The alert configuration changed before this update.",
                "Refresh the configuration and submit its current revision.",
                status_code=409,
            )
        session.add(revision)
        _commit_transaction(session)
    except HubError:
        raise
    except Exception as exc:
        session.rollback()
        raise _error(
            "ALERT_CONFIGURATION_SAVE_FAILED",
            "The alert configuration could not be saved.",
            "Refresh the draft and try the update again.",
            status_code=500,
        ) from exc

    session.expire_all()
    refreshed = session.get(DraftAlertConfigurationRow, configuration.id)
    assert refreshed is not None
    return _read_configuration(
        session,
        draft=_require_draft(session, session_id),
        configuration=refreshed,
    )
