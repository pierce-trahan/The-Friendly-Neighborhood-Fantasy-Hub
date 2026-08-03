from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.alerts.models import (
    AlertEvidenceSnapshotRow,
    AlertPlayerSignalRow,
    DraftAlertConfigurationRow,
    DraftAlertEventRow,
    DraftAlertTradeReferenceRow,
)
from friendly_hub.domains.reports.engine import RosterPlayer
from friendly_hub.domains.reports.evidence import (
    EvidenceContext,
    PlayerEvidence,
    build_evidence_sections,
)
from friendly_hub.domains.reports.models import PostDraftReportPlayerRow
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}


def _fixture_root() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "alert_evidence"


def _csv_text(rows: list[dict[str, str]], fieldnames: list[str]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _rewrite_csv(filename: str, transform) -> str:
    source = (_fixture_root() / filename).read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(source))
    assert reader.fieldnames is not None
    rows = [transform(dict(row)) for row in reader]
    return _csv_text(rows, list(reader.fieldnames))


def _seed_draft(
    client: TestClient,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    preview = client.post("/api/v1/player-imports/fixture/preview")
    assert preview.status_code == 201
    committed = client.post(f"/api/v1/player-imports/{preview.json()['id']}/commit")
    assert committed.status_code == 200
    players_response = client.get("/api/v1/players", params={"limit": 100})
    assert players_response.status_code == 200
    players = players_response.json()["items"]
    assert len(players) >= 6

    board_response = client.post(
        "/api/v1/boards",
        json={"name": "Evidence Enrichment Board", "scope": "overall"},
    )
    assert board_response.status_code == 201
    board = board_response.json()
    for player in players:
        response = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": player["id"]},
        )
        assert response.status_code == 200

    profile_response = client.post("/api/v1/league-profiles/samples/entropy")
    assert profile_response.status_code == 201
    draft_response = client.post(
        f"/api/v1/boards/{board['id']}/draft-sessions",
        json={
            "name": "Evidence Enrichment Draft",
            "mode": "live",
            "league_profile_id": profile_response.json()["id"],
            "draft_format": "snake",
            "third_round_reversal": False,
            "team_count": 2,
            "round_count": 3,
            "user_slot": 1,
            "team_names": ["Your Team", "Evidence Rival"],
        },
    )
    assert draft_response.status_code == 201, draft_response.text
    return draft_response.json(), players


def _evidence_payload(
    players: list[dict[str, object]],
    *,
    evidence_as_of: datetime,
    production_coverage: int = 2,
) -> dict[str, object]:
    timestamp = evidence_as_of.astimezone(UTC).isoformat().replace("+00:00", "Z")
    user_players = [players[index] for index in (0, 3, 4)]
    expected_windows = {
        str(user_players[0]["display_name"]): (1, 1),
        str(user_players[1]["display_name"]): (2, 3),
        str(user_players[2]["display_name"]): (6, 6),
    }
    production_names = {
        str(player["display_name"]) for player in user_players[:production_coverage]
    }

    def player_transform(row: dict[str, str]) -> dict[str, str]:
        row["evidence_as_of"] = timestamp
        if row["display_name"] in expected_windows:
            low, high = expected_windows[row["display_name"]]
            row["expected_pick_low"] = str(low)
            row["expected_pick_high"] = str(high)
            row["market_band"] = "strong"
            row["age_risk_band"] = "middle"
            row["win_now_production_band"] = (
                "high" if row["display_name"] in production_names else ""
            )
        return row

    def pick_transform(row: dict[str, str]) -> dict[str, str]:
        row["evidence_as_of"] = timestamp
        return row

    return {
        "player_filename": "player-signals.synthetic.csv",
        "player_csv_text": _rewrite_csv(
            "player-signals.synthetic.csv", player_transform
        ),
        "pick_filename": "pick-values.synthetic.csv",
        "pick_csv_text": _rewrite_csv("pick-values.synthetic.csv", pick_transform),
        "metadata": {
            "snapshot_key": f"phase-6-enrichment-{int(evidence_as_of.timestamp())}",
            "source_label": "Neighborhood Synthetic Evidence",
            "source_kind": "synthetic",
            "source_namespace": "sanitized_fixture",
            "permitted_use_confirmed": True,
            "private_source_reference": "never-expose-private-reference",
            "as_of": timestamp,
            "league_type": "dynasty",
            "draft_purpose": "startup",
            "team_count": 2,
            "draft_format": "snake",
            "third_round_reversal": False,
            "round_count": 3,
            "quarterback_mode": "superflex",
            "reception_scoring": "ppr",
            "tight_end_premium": True,
            "supported_draft_depth": 240,
        },
    }


def _attach_evidence(
    client: TestClient,
    draft: dict[str, object],
    players: list[dict[str, object]],
    *,
    evidence_as_of: datetime,
    production_coverage: int = 2,
) -> str:
    preview = client.post(
        "/api/v1/alert-evidence-imports/preview",
        json=_evidence_payload(
            players,
            evidence_as_of=evidence_as_of,
            production_coverage=production_coverage,
        ),
    )
    assert preview.status_code == 201, preview.text
    preview_body = preview.json()
    committed = client.post(
        f"/api/v1/alert-evidence-imports/{preview_body['id']}/commit",
        json={
            "content_hash": preview_body["content_hash"],
            "permitted_use_confirmed": True,
        },
    )
    assert committed.status_code == 200, committed.text
    snapshot_id = committed.json()["snapshot"]["id"]
    attached = client.post(
        f"/api/v1/draft-sessions/{draft['id']}/alert-configuration",
        json={
            "draft_revision": draft["revision"],
            "evidence_snapshot_id": snapshot_id,
        },
    )
    assert attached.status_code == 201, attached.text
    assert attached.json()["format_compatibility"] == "exact"
    return str(snapshot_id)


def _complete(
    client: TestClient,
    draft: dict[str, object],
    players: list[dict[str, object]],
) -> dict[str, object]:
    current = draft
    for player in players[:6]:
        current_pick = current["current_pick"]
        assert isinstance(current_pick, dict)
        picked = client.post(
            f"/api/v1/draft-sessions/{current['id']}/picks",
            json={
                "revision": current["revision"],
                "expected_overall_pick": current_pick["overall_pick"],
                "player_id": player["id"],
            },
        )
        assert picked.status_code == 200, picked.text
        current = picked.json()
    assert current["status"] == "completed"
    return current


def _generate(client: TestClient, draft: dict[str, object]):
    return client.post(
        f"/api/v1/draft-sessions/{draft['id']}/post-draft-reports",
        json={
            "draft_revision": draft["revision"],
            "expected_completed_at": draft["completed_at"],
        },
    )


def _section(report: dict[str, object], key: str) -> dict[str, object]:
    sections = report["sections"]
    assert isinstance(sections, list)
    return next(section for section in sections if section["section_key"] == key)


def _evidence_source_state(client: TestClient, snapshot_id: str) -> tuple[object, ...]:
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        snapshot = session.get(AlertEvidenceSnapshotRow, snapshot_id)
        assert snapshot is not None
        configuration = session.scalar(
            select(DraftAlertConfigurationRow).where(
                DraftAlertConfigurationRow.evidence_snapshot_id == snapshot_id
            )
        )
        assert configuration is not None
        signals = tuple(
            session.execute(
                select(
                    AlertPlayerSignalRow.id,
                    AlertPlayerSignalRow.field_timestamps_json,
                    AlertPlayerSignalRow.private_source_record_reference,
                )
                .where(AlertPlayerSignalRow.evidence_snapshot_id == snapshot_id)
                .order_by(AlertPlayerSignalRow.id)
            )
        )
        return (
            snapshot.content_hash,
            snapshot.status,
            snapshot.private_source_reference,
            configuration.id,
            configuration.revision,
            configuration.updated_at,
            signals,
        )


def _saved_alert_evidence(configuration_revision: int, draft_revision: int) -> dict[str, object]:
    return {
        "source_label": "Neighborhood Synthetic Evidence",
        "source_as_of": "2026-08-01T00:00:00Z",
        "format_compatibility": "exact",
        "expected_selection": {"low": 1, "high": 2},
        "market_gap": {"low": 0, "high": 1},
        "return_risk": "uncertain",
        "current_overall_pick": 1,
        "next_user_pick": 4,
        "personal_reason": {
            "manual_rank": 1,
            "tier_order": None,
            "favorite": True,
            "qualifier_mode": "tier_or_favorite",
            "qualified": True,
        },
        "components": {
            "personal_conviction": {
                "state": "available",
                "band": "favorite",
                "reasons": [],
            },
            "dynasty_market": {
                "state": "available",
                "band": "strong",
                "reasons": [],
            },
            "win_now_production": {
                "state": "available",
                "band": "high",
                "reasons": [],
            },
            "age_risk": {
                "state": "available",
                "band": "middle",
                "reasons": [],
            },
            "strategy_fit": {
                "state": "unavailable",
                "band": None,
                "reasons": ["STRATEGY_FIT_UNAVAILABLE"],
            },
        },
        "target_pick_window": {"low": 1, "high": 2},
        "cost_availability": "available",
        "confidence_reasons": ["FRESH_EVIDENCE"],
        "limitation_codes": ["PICK_ONLY_REFERENCE"],
        "engine_version": "alert-engine-v1",
        "rule_version": "alert-rules-v1",
        "freshness_policy_version": "alert-freshness-v1",
        "configuration_revision": configuration_revision,
        "draft_revision": draft_revision,
        "private_source_reference": "PRIVATE ALERT SOURCE REFERENCE",
    }


def _insert_saved_alert(
    client: TestClient,
    *,
    draft_id: str,
    snapshot_id: str,
    player_id: str,
    corrupt: bool = False,
) -> str:
    event_id = str(uuid4())
    now = utc_now_text()
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        configuration = session.scalar(
            select(DraftAlertConfigurationRow).where(
                DraftAlertConfigurationRow.draft_session_id == draft_id
            )
        )
        assert configuration is not None
        evidence = _saved_alert_evidence(configuration.revision, 0)
        session.add(
            DraftAlertEventRow(
                id=event_id,
                configuration_id=configuration.id,
                player_id=player_id,
                deterministic_event_key=f"saved-report-event-{event_id}",
                alert_kind="trade_up_window",
                status="open",
                confidence="medium",
                freshness="fresh",
                first_confirmed_draft_revision=0,
                last_confirmed_draft_revision=0,
                original_evidence_json=json.dumps(
                    {**evidence, "private_original_context": "PRIVATE ORIGINAL"}
                ),
                current_evidence_json=("{" if corrupt else json.dumps(evidence)),
                explanation_template_keys_json=json.dumps(["TRADE_UP_WINDOW_V1"]),
                limitation_codes_json=json.dumps(["PICK_ONLY_REFERENCE"]),
                snooze_boundary=None,
                dismissed_at=None,
                superseded_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            DraftAlertTradeReferenceRow(
                id=str(uuid4()),
                event_id=event_id,
                target_overall_pick_low=1,
                target_overall_pick_high=2,
                target_round_pick_labels_json=json.dumps(
                    ["Round 1, pick 1", "Round 1, pick 2"]
                ),
                cost_range_json=json.dumps(
                    {
                        "incremental_cost": {"low": 10, "high": 20},
                        "pick_only_references": [
                            {
                                "label": "Year 1, round 2",
                                "season_offset": 1,
                                "round": 2,
                                "value": {"low": 15, "high": 25},
                                "private_asset_key": "PRIVATE ASSET KEY",
                            }
                        ],
                        "cost_availability": "available",
                        "private_curve": "PRIVATE CURVE",
                    }
                ),
                pick_curve_snapshot_id=snapshot_id,
                explanation_template_key="PICK_ONLY_COST_REFERENCE_V1",
                limitation_codes_json=json.dumps(["PICK_ONLY_REFERENCE"]),
                created_at=now,
            )
        )
        session.commit()
    return event_id


def test_attached_evidence_enriches_report_without_mutating_or_leaking_sources(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        draft, players = _seed_draft(client)
        snapshot_id = _attach_evidence(
            client,
            draft,
            players,
            evidence_as_of=datetime.now(UTC) - timedelta(days=1),
        )
        completed = _complete(client, draft, players)
        source_before = _evidence_source_state(client, snapshot_id)

        generated = _generate(client, completed)
        assert generated.status_code == 201, generated.text
        report = generated.json()["report"]
        production = _section(report, "year_one_production_context")
        market = _section(report, "dynasty_market_context")
        age_risk = _section(report, "age_risk_profile")
        alert_history = _section(report, "recorded_alert_moments")

        assert production["availability"] == "limited"
        assert production["confidence"] == "low"
        assert production["metrics"]["coverage_basis_points"] == 6666
        assert market["availability"] == "supported"
        assert market["confidence"] == "medium"
        assert age_risk["availability"] == "supported"
        assert age_risk["confidence"] == "medium"
        assert alert_history["availability"] == "supported"
        assert alert_history["metrics"]["history_state"] == "configured_no_events"
        assert market["safe_provenance"]["source_label"] == (
            "Neighborhood Synthetic Evidence"
        )
        assert market["safe_provenance"]["format_compatibility"] == "exact"
        assert market["safe_provenance"]["freshness_at_completion"] == "fresh"
        selection_contexts = {
            item["selection_context"]
            for item in market["metrics"]["expected_selection_context"]
        }
        assert selection_contexts == {
            "before_expected_window",
            "within_expected_window",
            "after_expected_window",
        }
        assert "PHASE6_STEP6" not in generated.text
        assert "never-expose-private-reference" not in generated.text
        assert "demo-qb-001" not in generated.text
        assert _evidence_source_state(client, snapshot_id) == source_before

        session_factory = client.app.state.session_factory
        with session_factory() as session:
            safe_documents = [
                json.loads(value)
                for value in session.scalars(
                    select(PostDraftReportPlayerRow.safe_evidence_json).where(
                        PostDraftReportPlayerRow.report_id == report["id"]
                    )
                )
            ]
        assert all("categorical_evidence" in item for item in safe_documents)
        persisted = json.dumps(safe_documents, sort_keys=True)
        assert "market_band" in persisted
        assert "private" not in persisted.lower()
        assert "demo-qb-001" not in persisted

        repeated = _generate(client, completed)
        assert repeated.status_code == 200
        assert repeated.json()["idempotent"] is True
        assert repeated.json()["report"] == report


def test_saved_alert_and_pick_only_reference_are_projected_without_private_fields(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        draft, players = _seed_draft(client)
        snapshot_id = _attach_evidence(
            client,
            draft,
            players,
            evidence_as_of=datetime.now(UTC) - timedelta(days=1),
            production_coverage=3,
        )
        event_id = _insert_saved_alert(
            client,
            draft_id=str(draft["id"]),
            snapshot_id=snapshot_id,
            player_id=str(players[0]["id"]),
        )
        completed = _complete(client, draft, players)
        session_factory = client.app.state.session_factory
        with session_factory() as session:
            event = session.get(DraftAlertEventRow, event_id)
            assert event is not None
            after_completion = utc_now_text()
            event.status = "dismissed"
            event.dismissed_at = after_completion
            event.updated_at = after_completion
            session.add(
                DraftAlertTradeReferenceRow(
                    id=str(uuid4()),
                    event_id=event_id,
                    target_overall_pick_low=2,
                    target_overall_pick_high=3,
                    target_round_pick_labels_json=json.dumps(
                        ["Round 1, pick 2", "Round 2, pick 1"]
                    ),
                    cost_range_json=json.dumps(
                        {
                            "incremental_cost": {"low": 11, "high": 21},
                            "pick_only_references": [
                                {
                                    "label": "Year 1, round 2",
                                    "season_offset": 1,
                                    "round": 2,
                                    "value": {"low": 16, "high": 26},
                                }
                            ],
                            "cost_availability": "available",
                        }
                    ),
                    pick_curve_snapshot_id=snapshot_id,
                    explanation_template_key="PICK_ONLY_COST_REFERENCE_V1",
                    limitation_codes_json=json.dumps(["PICK_ONLY_REFERENCE"]),
                    created_at=after_completion,
                )
            )
            session.commit()
            source_before = (
                event.status,
                event.current_evidence_json,
                tuple(
                    session.execute(
                        select(
                            DraftAlertTradeReferenceRow.id,
                            DraftAlertTradeReferenceRow.cost_range_json,
                        ).where(DraftAlertTradeReferenceRow.event_id == event_id)
                    )
                ),
            )

        generated = _generate(client, completed)
        assert generated.status_code == 201, generated.text
        report = generated.json()["report"]
        section = _section(report, "recorded_alert_moments")
        assert section["availability"] == "supported"
        assert section["confidence"] == "high"
        assert section["metrics"]["history_state"] == "available"
        assert section["metrics"]["event_count"] == 1
        alert_moments = [
            moment
            for moment in report["moments"]
            if moment["moment_kind"] == "alert_event"
        ]
        assert len(alert_moments) == 1
        moment = alert_moments[0]
        assert moment["safe_summary"]["kind"] == "trade_up_window"
        assert moment["safe_summary"]["status"] == "dismissed"
        assert moment["safe_summary"]["drafted_outcome"] == {
            "state": "drafted_by_user",
            "overall_pick": 1,
        }
        trade = moment["safe_summary"]["trade_reference"]
        assert trade["target_pick_window"] == {"low": 2, "high": 3}
        assert trade["incremental_cost"] == {"low": 11, "high": 21}
        assert trade["pick_only_references"] == [
            {
                "label": "Year 1, round 2",
                "season_offset": 1,
                "round": 2,
                "value": {"low": 16, "high": 26},
            }
        ]
        assert "NO_TRADE_EXECUTION_CLAIM" in moment["limitation_codes"]
        forbidden = (
            "PRIVATE ALERT SOURCE REFERENCE",
            "PRIVATE ORIGINAL",
            "PRIVATE ASSET KEY",
            "PRIVATE CURVE",
            "private_source_reference",
            "pick_curve_snapshot_id",
            "ownership",
        )
        assert all(marker not in generated.text for marker in forbidden)

        with session_factory() as session:
            event = session.get(DraftAlertEventRow, event_id)
            assert event is not None
            source_after = (
                event.status,
                event.current_evidence_json,
                tuple(
                    session.execute(
                        select(
                            DraftAlertTradeReferenceRow.id,
                            DraftAlertTradeReferenceRow.cost_range_json,
                        ).where(DraftAlertTradeReferenceRow.event_id == event_id)
                    )
                ),
            )
        assert source_after == source_before


def test_disabled_and_corrupt_alert_histories_remain_distinct(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        disabled_draft, disabled_players = _seed_draft(client)
        disabled_snapshot = _attach_evidence(
            client,
            disabled_draft,
            disabled_players,
            evidence_as_of=datetime.now(UTC) - timedelta(days=1),
        )
        assert disabled_snapshot
        session_factory = client.app.state.session_factory
        with session_factory() as session:
            configuration = session.scalar(
                select(DraftAlertConfigurationRow).where(
                    DraftAlertConfigurationRow.draft_session_id == disabled_draft["id"]
                )
            )
            assert configuration is not None
            configuration.enabled = False
            configuration.updated_at = utc_now_text()
            session.commit()
        disabled_completed = _complete(client, disabled_draft, disabled_players)
        disabled_report = _generate(client, disabled_completed)
        assert disabled_report.status_code == 201, disabled_report.text
        disabled_section = _section(
            disabled_report.json()["report"], "recorded_alert_moments"
        )
        assert disabled_section["availability"] == "supported"
        assert disabled_section["metrics"]["history_state"] == (
            "disabled_at_completion"
        )
        assert disabled_section["metrics"]["event_count"] == 0

    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        corrupt_draft, corrupt_players = _seed_draft(client)
        corrupt_snapshot = _attach_evidence(
            client,
            corrupt_draft,
            corrupt_players,
            evidence_as_of=datetime.now(UTC) - timedelta(days=1),
        )
        _insert_saved_alert(
            client,
            draft_id=str(corrupt_draft["id"]),
            snapshot_id=corrupt_snapshot,
            player_id=str(corrupt_players[0]["id"]),
            corrupt=True,
        )
        corrupt_completed = _complete(client, corrupt_draft, corrupt_players)
        corrupt_report = _generate(client, corrupt_completed)
        assert corrupt_report.status_code == 201, corrupt_report.text
        report = corrupt_report.json()["report"]
        corrupt_section = _section(report, "recorded_alert_moments")
        assert corrupt_section["availability"] == "unavailable"
        assert corrupt_section["confidence"] == "unavailable"
        assert corrupt_section["metrics"]["history_state"] == (
            "unavailable_due_to_corruption"
        )
        assert not any(
            moment["moment_kind"] == "alert_event" for moment in report["moments"]
        )


def test_saved_alert_detail_is_deterministically_ordered_and_capped_at_twenty(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        draft, players = _seed_draft(client)
        snapshot_id = _attach_evidence(
            client,
            draft,
            players,
            evidence_as_of=datetime.now(UTC) - timedelta(days=1),
        )
        assert snapshot_id
        session_factory = client.app.state.session_factory
        event_ids = [f"00000000-0000-0000-0000-{number:012d}" for number in range(21)]
        with session_factory() as session:
            configuration = session.scalar(
                select(DraftAlertConfigurationRow).where(
                    DraftAlertConfigurationRow.draft_session_id == draft["id"]
                )
            )
            assert configuration is not None
            evidence = _saved_alert_evidence(configuration.revision, 0)
            now = utc_now_text()
            for event_id in reversed(event_ids):
                session.add(
                    DraftAlertEventRow(
                        id=event_id,
                        configuration_id=configuration.id,
                        player_id=str(players[0]["id"]),
                        deterministic_event_key=f"saved-cap-event-{event_id}",
                        alert_kind="value_watch",
                        status="open",
                        confidence="medium",
                        freshness="fresh",
                        first_confirmed_draft_revision=0,
                        last_confirmed_draft_revision=0,
                        original_evidence_json=json.dumps(evidence),
                        current_evidence_json=json.dumps(evidence),
                        explanation_template_keys_json=json.dumps(["VALUE_WATCH_V1"]),
                        limitation_codes_json=json.dumps([]),
                        snooze_boundary=None,
                        dismissed_at=None,
                        superseded_at=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.commit()

        completed = _complete(client, draft, players)
        generated = _generate(client, completed)
        assert generated.status_code == 201, generated.text
        report = generated.json()["report"]
        section = _section(report, "recorded_alert_moments")
        assert section["metrics"]["event_count"] == 21
        assert section["metrics"]["included_event_count"] == 20
        assert section["metrics"]["truncated"] is True
        moment_keys = [
            moment["moment_key"]
            for moment in report["moments"]
            if moment["moment_kind"] == "alert_event"
        ]
        assert moment_keys == [f"alert:{event_id}" for event_id in event_ids[:20]]


def test_elapsed_evidence_is_unavailable_at_the_completion_boundary(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        draft, players = _seed_draft(client)
        _attach_evidence(
            client,
            draft,
            players,
            evidence_as_of=datetime.now(UTC) - timedelta(days=90),
            production_coverage=3,
        )
        completed = _complete(client, draft, players)
        generated = _generate(client, completed)
        assert generated.status_code == 201, generated.text
        report = generated.json()["report"]

        for key in ("year_one_production_context", "dynasty_market_context"):
            section = _section(report, key)
            assert section["availability"] == "unavailable"
            assert section["confidence"] == "unavailable"
            assert section["metrics"]["covered_players"] == 0
            assert "FRESHNESS_EXPIRED" in section["limitation_codes"]
        assert _section(report, "age_risk_profile")["availability"] == "supported"


def _player(
    number: int,
    *,
    production: bool,
    market: bool,
    age: bool,
    freshness: str = "fresh",
) -> PlayerEvidence:
    return PlayerEvidence(
        player_id=f"player-{number}",
        market_band="strong" if market else None,
        production_band="high" if production else None,
        age_risk_band="middle" if age else None,
        expected_pick_low=None,
        expected_pick_high=None,
        field_timestamps={},
        field_freshness={
            **({"market_band": freshness} if market else {}),
            **({"win_now_production_band": freshness} if production else {}),
            **({"age_risk_band": freshness} if age else {}),
        },
        limitation_codes=(),
    )


def _context(signals: tuple[PlayerEvidence, ...], *, compatibility: str = "exact"):
    return EvidenceContext(
        configuration_id="configuration-1",
        configuration_revision=0,
        configuration_enabled=True,
        alert_engine_version="alert-engine-v1",
        alert_rule_version="alert-rules-v1",
        freshness_policy_version="alert-freshness-v1",
        snapshot_id="snapshot-1",
        snapshot_content_hash="a" * 64,
        snapshot_status="committed",
        source_label="Synthetic Evidence",
        source_as_of="2026-08-01T00:00:00Z",
        compatibility=compatibility,
        compatibility_reasons=(),
        signals=signals,
        invalid=False,
    )


def test_coverage_thresholds_and_compatibility_confidence_are_fail_closed() -> None:
    roster = tuple(
        RosterPlayer(
            canonical_player_id=f"player-{number}",
            overall_pick=number,
            primary_position="WR",
            fantasy_positions=("WR",),
        )
        for number in range(1, 11)
    )
    signals = tuple(
        _player(
            number,
            production=number <= 8,
            market=number <= 5,
            age=number <= 4,
        )
        for number in range(1, 11)
    )
    sections = {
        section.section_key: section
        for section in build_evidence_sections(_context(signals), roster)
    }
    assert sections["year_one_production_context"].availability == "supported"
    assert sections["year_one_production_context"].confidence == "medium"
    assert sections["dynasty_market_context"].availability == "limited"
    assert sections["dynasty_market_context"].confidence == "low"
    assert sections["age_risk_profile"].availability == "unavailable"
    assert sections["age_risk_profile"].confidence == "unavailable"

    partial = build_evidence_sections(
        _context(
            tuple(
                _player(number, production=True, market=True, age=True)
                for number in range(1, 11)
            ),
            compatibility="partial",
        ),
        roster,
    )
    assert all(section.availability == "supported" for section in partial)
    assert all(section.confidence == "low" for section in partial)

    incompatible = build_evidence_sections(
        _context(signals, compatibility="incompatible"), roster
    )
    assert all(section.availability == "unavailable" for section in incompatible)
    assert all("FORMAT_INCOMPATIBLE" in section.limitation_codes for section in incompatible)

    mixed_freshness = build_evidence_sections(
        _context(
            tuple(
                _player(
                    number,
                    production=True,
                    market=True,
                    age=True,
                    freshness="expired" if number == 10 else "fresh",
                )
                for number in range(1, 11)
            )
        ),
        roster,
    )
    assert all(section.availability == "supported" for section in mixed_freshness)
    assert all(
        section.safe_provenance["freshness_at_completion"] == "fresh"
        for section in mixed_freshness
    )
    assert all("FRESHNESS_EXPIRED" in section.limitation_codes for section in mixed_freshness)


def test_missing_evidence_uses_explicit_unavailable_sections() -> None:
    roster = (
        RosterPlayer(
            canonical_player_id="player-1",
            overall_pick=1,
            primary_position="QB",
            fantasy_positions=("QB",),
        ),
    )
    sections = build_evidence_sections(None, roster)
    assert len(sections) == 3
    assert all(section.availability == "unavailable" for section in sections)
    assert all(section.confidence == "unavailable" for section in sections)
    assert all(
        "EVIDENCE_SNAPSHOT_NOT_ATTACHED" in section.limitation_codes
        for section in sections
    )
