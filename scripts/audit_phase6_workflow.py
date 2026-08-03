from __future__ import annotations

import csv
import io
import json
import socket
import tempfile
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}
TEAM_NAMES = ["Your Team", *[f"Fictional Club {index}" for index in range(2, 11)]]
PRIVATE_MARKERS = (
    "PRIVATE AUDIT BOARD NOTE",
    "PRIVATE AUDIT STRATEGY NOTE",
    "never-expose-private-reference",
)
FORBIDDEN_RESPONSE_KEYS = (
    "provider_id",
    "private_source_reference",
    "raw_rows",
    "private_user_note",
    "random_audit",
    "manager_reference",
)


def _expect(response, status: int) -> dict[str, Any]:
    if response.status_code != status:
        raise AssertionError(
            f"{response.request.method} {response.request.url.path} returned "
            f"{response.status_code}: {response.text[:1_000]}"
        )
    return response.json()


def _synthetic_player_fixture(project_root: Path, target: Path) -> None:
    source = json.loads(
        (project_root / "tests/fixtures/players/phase-1-players.sanitized.json").read_text(
            encoding="utf-8"
        )
    )
    players = list(source["players"])
    positions = ("QB", "RB", "WR", "TE")
    for index in range(len(players) + 1, 281):
        position = positions[(index - 1) % len(positions)]
        players.append(
            {
                "name": f"Audit Player {index:03d}",
                "position": position,
                "fantasy_positions": [position],
                "team": f"T{((index - 1) % 32) + 1:02d}",
                "status": "active",
                "rookie_class": 2026 if index % 5 == 0 else 2023,
                "is_rookie": index % 5 == 0,
                "provider": "sanitized_fixture",
                "external_id": f"audit-player-{index:03d}",
            }
        )
    target.write_text(
        json.dumps(
            {
                **source,
                "description": "Fictional 280-player Phase 6 offline audit pool.",
                "players": players,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _rewrite_csv(path: Path, transform) -> str:
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")))
    if reader.fieldnames is None:
        raise AssertionError(f"{path.name} has no CSV header")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=reader.fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(transform(dict(row)) for row in reader)
    return output.getvalue()


def _append_csv_row(csv_text: str, row: dict[str, str]) -> str:
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        raise AssertionError("Synthetic player signal CSV has no header")
    rows = [*reader, row]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=reader.fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _evidence_payload(project_root: Path) -> dict[str, Any]:
    fixture_root = project_root / "tests/fixtures/alert_evidence"
    as_of = "2026-08-03T12:00:00Z"
    windows = {
        "Marcus Hale": (1, 1),
        "Theo Banks": (20, 30),
        "Andre Vale III": (40, 55),
    }

    def player_transform(row: dict[str, str]) -> dict[str, str]:
        row["evidence_as_of"] = as_of
        if row["display_name"] in windows:
            low, high = windows[row["display_name"]]
            row["expected_pick_low"] = str(low)
            row["expected_pick_high"] = str(high)
            row["market_band"] = "strong"
            row["age_risk_band"] = "middle"
            row["win_now_production_band"] = "high"
        return row

    def pick_transform(row: dict[str, str]) -> dict[str, str]:
        row["evidence_as_of"] = as_of
        return row

    player_csv = _rewrite_csv(
        fixture_root / "player-signals.synthetic.csv",
        player_transform,
    )
    player_csv = _append_csv_row(
        player_csv,
        {
            "source_player_key": "audit-player-280",
            "display_name": "Audit Player 280",
            "position": "TE",
            "team": "T24",
            "expected_pick_low": "1",
            "expected_pick_high": "1",
            "market_band": "strong",
            "win_now_production_band": "high",
            "age_risk_band": "middle",
            "evidence_as_of": as_of,
            "limitation_codes": "",
        },
    )
    return {
        "player_filename": "player-signals.synthetic.csv",
        "player_csv_text": player_csv,
        "pick_filename": "pick-values.synthetic.csv",
        "pick_csv_text": _rewrite_csv(
            fixture_root / "pick-values.synthetic.csv",
            pick_transform,
        ),
        "metadata": {
            "snapshot_key": "phase-6-offline-workflow-audit",
            "source_label": "Neighborhood Synthetic Audit Evidence",
            "source_kind": "synthetic",
            "source_namespace": "sanitized_fixture",
            "permitted_use_confirmed": True,
            "private_source_reference": "never-expose-private-reference",
            "as_of": as_of,
            "league_type": "dynasty",
            "draft_purpose": "startup",
            "team_count": 10,
            "draft_format": "snake",
            "third_round_reversal": True,
            "round_count": 24,
            "quarterback_mode": "superflex",
            "reception_scoring": "ppr",
            "tight_end_premium": True,
            "supported_draft_depth": 240,
        },
    }


def _seed_workspace(
    client: TestClient,
    project_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str]:
    preview = _expect(client.post("/api/v1/player-imports/fixture/preview"), 201)
    _expect(client.post(f"/api/v1/player-imports/{preview['id']}/commit"), 200)
    players = _expect(client.get("/api/v1/players", params={"limit": 500}), 200)[
        "items"
    ]
    if len(players) != 280:
        raise AssertionError(f"Expected 280 synthetic players, found {len(players)}")
    league = _expect(client.post("/api/v1/league-profiles/samples/entropy"), 201)
    board = _expect(
        client.post(
            "/api/v1/boards",
            json={
                "name": "Phase 6 Offline Audit Board",
                "description": "Synthetic local workflow audit",
                "league_profile_id": league["id"],
                "scope": "overall",
            },
        ),
        201,
    )
    original_names = {
        "Marcus Hale",
        "Devin Cross Jr.",
        "Elias North",
        "Theo Banks",
        "Andre Vale III",
        "Nolan Reed",
    }
    ordered = [
        *[player for player in players if player["display_name"] in original_names],
        *[player for player in players if player["display_name"] not in original_names],
    ]
    for player in ordered[:30]:
        board = _expect(
            client.post(
                f"/api/v1/boards/{board['id']}/entries",
                json={"player_id": player["id"]},
            ),
            200,
        )
    audit_target = next(
        player for player in ordered if player["display_name"] == "Audit Player 280"
    )
    board = _expect(
        client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": audit_target["id"]},
        ),
        200,
    )
    for name in (
        "Marcus Hale",
        "Theo Banks",
        "Andre Vale III",
        "Audit Player 280",
    ):
        entry = next(
            item
            for item in board["entries"]
            if item["player"]["display_name"] == name
        )
        board = _expect(
            client.patch(
                f"/api/v1/boards/{board['id']}/entries/{entry['id']}",
                json={
                    "favorite": True,
                    "note": "PRIVATE AUDIT BOARD NOTE" if name == "Marcus Hale" else None,
                },
            ),
            200,
        )
    evidence_preview = _expect(
        client.post(
            "/api/v1/alert-evidence-imports/preview",
            json=_evidence_payload(project_root),
        ),
        201,
    )
    evidence = _expect(
        client.post(
            f"/api/v1/alert-evidence-imports/{evidence_preview['id']}/commit",
            json={
                "content_hash": evidence_preview["content_hash"],
                "permitted_use_confirmed": True,
            },
        ),
        200,
    )
    return board, league, ordered, str(evidence["snapshot"]["id"])


def _create_mock(
    client: TestClient,
    board_id: str,
    league_id: str,
    *,
    name: str,
    seed: str,
    strategy: str,
) -> dict[str, Any]:
    return _expect(
        client.post(
            f"/api/v1/boards/{board_id}/mock-sessions",
            json={
                "name": name,
                "league_profile_id": league_id,
                "draft_format": "snake",
                "third_round_reversal": True,
                "team_count": 10,
                "round_count": 24,
                "user_slot": 1,
                "team_names": TEAM_NAMES,
                "seed": seed,
                "randomness": 25,
                "strategy_key": strategy,
                "fallback_archetypes": {
                    str(slot): "balanced" for slot in range(2, 11)
                },
                "include_in_learning": False,
            },
        ),
        201,
    )


def _attach_alerts(
    client: TestClient,
    mock: dict[str, Any],
    snapshot_id: str,
) -> dict[str, Any]:
    configuration = _expect(
        client.post(
            f"/api/v1/draft-sessions/{mock['draft']['id']}/alert-configuration",
            json={
                "draft_revision": mock["draft"]["revision"],
                "evidence_snapshot_id": snapshot_id,
            },
        ),
        201,
    )
    if configuration["format_compatibility"] != "exact":
        raise AssertionError("Synthetic alert evidence did not attach exactly")
    return configuration


def _advance_mock(
    client: TestClient,
    mock: dict[str, Any],
    players: list[dict[str, Any]],
    *,
    pivot_strategy: str,
    alert_configuration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pivoted = False
    alerts_evaluated = alert_configuration is None
    while mock["draft"]["status"] != "completed":
        current = mock["draft"]["current_pick"]
        if current is None:
            raise AssertionError("Active mock has no current pick")
        if current["overall_pick"] == 2 and not pivoted:
            mock = _expect(
                client.patch(
                    f"/api/v1/mock-sessions/{mock['draft']['id']}/strategy",
                    json={
                        "mock_revision": mock["mock"]["revision"],
                        "expected_current_overall_pick": 2,
                        "strategy_key": pivot_strategy,
                        "private_user_note": "PRIVATE AUDIT STRATEGY NOTE",
                    },
                ),
                200,
            )
            pivoted = True
            current = mock["draft"]["current_pick"]
        if current["overall_pick"] == 2 and not alerts_evaluated:
            evaluated = _expect(
                client.post(
                    f"/api/v1/draft-sessions/{mock['draft']['id']}/alerts/evaluate",
                    json={
                        "draft_revision": mock["draft"]["revision"],
                        "configuration_revision": alert_configuration["revision"],
                        "expected_current_overall_pick": 2,
                        "last_evaluation_draft_revision": None,
                    },
                ),
                200,
            )
            if evaluated["evaluation"]["opened_count"] < 1:
                raise AssertionError("Compatible synthetic evidence opened no alert")
            alerts_evaluated = True
        if mock["draft"]["user_on_the_clock"]:
            drafted = {pick["player_id"] for pick in mock["draft"]["picks"]}
            player = next(player for player in players if player["id"] not in drafted)
            _expect(
                client.post(
                    f"/api/v1/draft-sessions/{mock['draft']['id']}/picks",
                    json={
                        "revision": mock["draft"]["revision"],
                        "expected_overall_pick": current["overall_pick"],
                        "player_id": player["id"],
                    },
                ),
                200,
            )
            mock = _expect(
                client.get(f"/api/v1/mock-sessions/{mock['draft']['id']}"),
                200,
            )
        elif mock["can_advance_cpu"]:
            mock = _expect(
                client.post(
                    f"/api/v1/mock-sessions/{mock['draft']['id']}/cpu-pick",
                    json={
                        "draft_revision": mock["draft"]["revision"],
                        "mock_revision": mock["mock"]["revision"],
                        "expected_overall_pick": current["overall_pick"],
                        "expected_selecting_slot": current["selecting_slot"],
                    },
                ),
                200,
            )
        else:
            raise AssertionError("Mock cannot advance at its current pick")
    if not pivoted:
        raise AssertionError("Mock completed without exercising a strategy pivot")
    if not alerts_evaluated:
        raise AssertionError("Mock completed without recording its alert evaluation")
    return mock


def _complete_live(
    client: TestClient,
    board_id: str,
    league_id: str,
    players: list[dict[str, Any]],
) -> dict[str, Any]:
    draft = _expect(
        client.post(
            f"/api/v1/boards/{board_id}/draft-sessions",
            json={
                "name": "Entropy-shaped Offline Live Draft",
                "mode": "live",
                "league_profile_id": league_id,
                "draft_format": "snake",
                "third_round_reversal": True,
                "team_count": 10,
                "round_count": 24,
                "user_slot": 1,
                "team_names": TEAM_NAMES,
            },
        ),
        201,
    )
    for player in players[:240]:
        current = draft["current_pick"]
        draft = _expect(
            client.post(
                f"/api/v1/draft-sessions/{draft['id']}/picks",
                json={
                    "revision": draft["revision"],
                    "expected_overall_pick": current["overall_pick"],
                    "player_id": player["id"],
                },
            ),
            200,
        )
    if draft["status"] != "completed":
        raise AssertionError("Live audit draft did not complete")
    return draft


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _generate(client: TestClient, draft: dict[str, Any]) -> tuple[dict[str, Any], float]:
    started = perf_counter()
    response = client.post(
        f"/api/v1/draft-sessions/{draft['id']}/post-draft-reports",
        json={
            "draft_revision": draft["revision"],
            "expected_completed_at": draft["completed_at"],
        },
    )
    elapsed = perf_counter() - started
    return _expect(response, 201), elapsed


def _source_snapshot(
    client: TestClient,
    board_id: str,
    mock_ids: list[str],
    live_id: str,
) -> str:
    return _canonical(
        {
            "board": _expect(client.get(f"/api/v1/boards/{board_id}"), 200),
            "mocks": [
                _expect(client.get(f"/api/v1/mock-sessions/{mock_id}"), 200)
                for mock_id in mock_ids
            ],
            "live": _expect(client.get(f"/api/v1/draft-sessions/{live_id}"), 200),
            "alerts": _expect(
                client.get(
                    f"/api/v1/draft-sessions/{mock_ids[0]}/alerts",
                    params={"scope": "history", "limit": 25},
                ),
                200,
            ),
        }
    )


def _privacy_scan(label: str, text: str) -> None:
    folded = text.casefold()
    for marker in (*PRIVATE_MARKERS, *FORBIDDEN_RESPONSE_KEYS):
        if marker.casefold() in folded:
            raise AssertionError(f"{label} leaked forbidden marker {marker!r}")


def run_audit() -> dict[str, Any]:
    project_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="friendly-hub-phase6-audit-") as raw_dir:
        audit_root = Path(raw_dir)
        player_fixture = audit_root / "phase6-players.synthetic.json"
        _synthetic_player_fixture(project_root, player_fixture)
        base = RuntimeSettings.from_environment()
        settings = replace(
            base,
            data_dir=audit_root / "data",
            database_path=audit_root / "data/hub.sqlite3",
            log_dir=audit_root / "data/logs",
            player_fixture_path=player_fixture,
        )
        report_documents: dict[str, dict[str, Any]] = {}
        drafts: dict[str, dict[str, Any]] = {}
        with TestClient(create_app(settings), headers=TRUSTED_HEADERS) as client:
            board, league, players, snapshot_id = _seed_workspace(client, project_root)
            first = _create_mock(
                client,
                board["id"],
                league["id"],
                name="Balanced Audit Rehearsal",
                seed="6001",
                strategy="balanced",
            )
            alert_configuration = _attach_alerts(client, first, snapshot_id)
            first = _advance_mock(
                client,
                first,
                players,
                pivot_strategy="hero_rb",
                alert_configuration=alert_configuration,
            )
            second = _advance_mock(
                client,
                _create_mock(
                    client,
                    board["id"],
                    league["id"],
                    name="Productive Struggle Audit Rehearsal",
                    seed="6002",
                    strategy="productive_struggle",
                ),
                players,
                pivot_strategy="wr_heavy",
            )
            live = _complete_live(client, board["id"], league["id"], players)
            drafts = {
                "mock_one": first["draft"],
                "mock_two": second["draft"],
                "live": live,
            }
            source_before = _source_snapshot(
                client,
                board["id"],
                [first["draft"]["id"], second["draft"]["id"]],
                live["id"],
            )
            with patch.object(
                socket.socket,
                "connect",
                side_effect=AssertionError("network access attempted during offline report work"),
            ):
                generated: list[tuple[dict[str, Any], float]] = [
                    _generate(client, first["draft"]),
                    _generate(client, second["draft"]),
                    _generate(client, live),
                ]
            source_after = _source_snapshot(
                client,
                board["id"],
                [first["draft"]["id"], second["draft"]["id"]],
                live["id"],
            )
            if source_after != source_before:
                raise AssertionError("Report generation changed a source domain")
            generation_seconds = [elapsed for _, elapsed in generated]
            if max(generation_seconds) >= 1.0:
                raise AssertionError(f"Report generation exceeded target: {generation_seconds}")
            for name, (document, _) in zip(drafts, generated, strict=True):
                report = document["report"]
                report_documents[name] = report
                _privacy_scan(f"{name} report", _canonical(report))
                unsupported = {
                    section["section_key"]: section["availability"]
                    for section in report["sections"]
                    if section["section_key"]
                    in {"long_term_value", "liquidity", "player_fragility"}
                }
                if set(unsupported.values()) != {"unavailable"}:
                    raise AssertionError(f"Unsupported evidence was hidden: {unsupported}")
            draft_csv = client.get(
                f"/api/v1/draft-sessions/{live['id']}/export.csv"
            )
            if draft_csv.status_code != 200:
                raise AssertionError("The pre-existing draft CSV export failed")
            for phase_six_token in (
                "post_draft_report",
                "report_engine_version",
                "starter_coverage",
                "roster_concentration",
                "strategy_story",
            ):
                if phase_six_token in draft_csv.text.casefold():
                    raise AssertionError(
                        f"Draft CSV contains Phase 6 token {phase_six_token!r}"
                    )
            live_strategy = next(
                section
                for section in report_documents["live"]["sections"]
                if section["section_key"] == "strategy_story"
            )
            if live_strategy["availability"] != "not_applicable":
                raise AssertionError("Live strategy story was not marked not applicable")
            alert_section = next(
                section
                for section in report_documents["mock_one"]["sections"]
                if section["section_key"] == "recorded_alert_moments"
            )
            if alert_section["metrics"].get("event_count", 0) < 1:
                raise AssertionError("The attached saved alert was absent from the report")

        with TestClient(create_app(settings), headers=TRUSTED_HEADERS) as client:
            read_seconds: list[float] = []
            with patch.object(
                socket.socket,
                "connect",
                side_effect=AssertionError("network access attempted during offline report work"),
            ):
                for key, expected in report_documents.items():
                    started = perf_counter()
                    restored = _expect(
                        client.get(f"/api/v1/post-draft-reports/{expected['id']}"),
                        200,
                    )
                    read_seconds.append(perf_counter() - started)
                    if restored != expected:
                        raise AssertionError(f"Restart changed saved report {key}")
                idempotent_started = perf_counter()
                idempotent = _expect(
                    client.post(
                        f"/api/v1/draft-sessions/{drafts['mock_one']['id']}/post-draft-reports",
                        json={
                            "draft_revision": drafts["mock_one"]["revision"],
                            "expected_completed_at": drafts["mock_one"]["completed_at"],
                        },
                    ),
                    200,
                )
                idempotent_seconds = perf_counter() - idempotent_started
                comparison_started = perf_counter()
                comparison_response = client.post(
                    "/api/v1/post-draft-report-comparisons/preview",
                    json={
                        "report_ids": [
                            report_documents["mock_one"]["id"],
                            report_documents["mock_two"]["id"],
                        ]
                    },
                )
                comparison_seconds = perf_counter() - comparison_started
                comparison = _expect(comparison_response, 200)
                export_started = perf_counter()
                exported = client.get(
                    f"/api/v1/post-draft-reports/{report_documents['live']['id']}/export.html"
                )
                export_seconds = perf_counter() - export_started
            if idempotent["idempotent"] is not True:
                raise AssertionError("Identical generation was not idempotent after restart")
            if idempotent["report"] != report_documents["mock_one"]:
                raise AssertionError("Idempotent generation returned a different report")
            if max(read_seconds) >= 0.1:
                raise AssertionError(f"Saved report read exceeded target: {read_seconds}")
            if idempotent_seconds >= 1.0:
                raise AssertionError("Idempotent generation exceeded one second")
            if comparison_seconds >= 0.5:
                raise AssertionError("Comparison exceeded 500 milliseconds")
            if export_seconds >= 1.0:
                raise AssertionError("HTML export exceeded one second")
            if exported.status_code != 200:
                raise AssertionError(f"HTML export failed: {exported.text[:1_000]}")
            if len(exported.content) >= 2 * 1024 * 1024:
                raise AssertionError("HTML export exceeded two MiB")
            comparison_text = _canonical(comparison)
            _privacy_scan("comparison", comparison_text)
            for field in (
                '"winner":',
                '"ranking":',
                '"composite_score":',
                '"overall_score":',
            ):
                if field in comparison_text.casefold():
                    raise AssertionError(f"Comparison contains forbidden field {field!r}")
            html = exported.text
            _privacy_scan("HTML export", html)
            for fragment in ("<script", "http://", "https://", "src=", "href="):
                if fragment in html.casefold():
                    raise AssertionError(f"HTML export contains {fragment!r}")
            log_paths = list(settings.log_dir.glob("*.log*"))
            if not log_paths:
                raise AssertionError("The audit found no application log to scan")
            log_text = "\n".join(
                path.read_text(encoding="utf-8") for path in log_paths
            )
            _privacy_scan("application logs", log_text)

        return {
            "status": "passed",
            "shape": {
                "team_count": 10,
                "round_count": 24,
                "third_round_reversal": True,
                "completed_drafts": 3,
                "completed_picks": 720,
            },
            "reports": {
                "generated": 3,
                "restart_identical": 3,
                "idempotent": True,
                "saved_alert_present": True,
                "live_strategy_not_applicable": True,
            },
            "performance_seconds": {
                "generation": [round(value, 4) for value in generation_seconds],
                "read": [round(value, 4) for value in read_seconds],
                "idempotent_generation": round(idempotent_seconds, 4),
                "comparison": round(comparison_seconds, 4),
                "html_export": round(export_seconds, 4),
            },
            "privacy": {
                "source_domains_unchanged": True,
                "network_blocked_during_report_operations": True,
                "response_log_export_scans": "passed",
                "draft_csv_phase6_free": True,
                "html_bytes": len(exported.content),
            },
        }


if __name__ == "__main__":
    print(json.dumps(run_audit(), indent=2, sort_keys=True))
