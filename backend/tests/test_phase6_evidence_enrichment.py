from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.domains.alerts.models import (
    AlertEvidenceSnapshotRow,
    AlertPlayerSignalRow,
    DraftAlertConfigurationRow,
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

        assert production["availability"] == "limited"
        assert production["confidence"] == "low"
        assert production["metrics"]["coverage_basis_points"] == 6666
        assert market["availability"] == "supported"
        assert market["confidence"] == "medium"
        assert age_risk["availability"] == "supported"
        assert age_risk["confidence"] == "medium"
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
