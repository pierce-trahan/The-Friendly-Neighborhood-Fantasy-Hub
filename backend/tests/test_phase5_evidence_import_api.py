from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.domains.alerts.models import (
    AlertEvidenceSnapshotRow,
    AlertPickValueSignalRow,
    AlertPlayerSignalRow,
)
from friendly_hub.domains.players.models import PlayerExternalIdRow
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}
SYNTHETIC_HASH = (
    "fc93019416c2b31d9ce0598b1fa278a530df2022ee4e74f89f14161bbcc26274"
)


def _fixture_root() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _seed_players(client: TestClient) -> None:
    preview = client.post("/api/v1/player-imports/fixture/preview")
    assert preview.status_code == 201
    committed = client.post(
        f"/api/v1/player-imports/{preview.json()['id']}/commit"
    )
    assert committed.status_code == 200


def _metadata(**overrides: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "snapshot_key": "entropy-alert-evidence-synthetic-2026-07-28",
        "source_label": "Neighborhood Synthetic Market",
        "source_kind": "synthetic",
        "source_namespace": "sanitized_fixture",
        "permitted_use_confirmed": True,
        "private_source_reference": "private-local-reference",
        "as_of": "2026-07-28T00:00:00Z",
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
    }
    metadata.update(overrides)
    return metadata


def _synthetic_payload(**metadata_overrides: object) -> dict[str, object]:
    fixture_root = _fixture_root() / "alert_evidence"
    return {
        "player_filename": "player-signals.synthetic.csv",
        "player_csv_text": (
            fixture_root / "player-signals.synthetic.csv"
        ).read_text(encoding="utf-8"),
        "pick_filename": "pick-values.synthetic.csv",
        "pick_csv_text": (
            fixture_root / "pick-values.synthetic.csv"
        ).read_text(encoding="utf-8"),
        "metadata": _metadata(**metadata_overrides),
    }


def _single_player_payload(
    player_row: str,
    *,
    namespace: str = "manual_market",
    permission: bool = True,
) -> dict[str, object]:
    return {
        "player_filename": "one-player.csv",
        "player_csv_text": (
            "source_player_key,display_name,position,team,"
            "expected_pick_low,expected_pick_high,market_band,"
            "win_now_production_band,age_risk_band,evidence_as_of,"
            "limitation_codes\n"
            f"{player_row}\n"
        ),
        "metadata": _metadata(
            snapshot_key=f"{namespace}-2026-07-28",
            source_namespace=namespace,
            source_label="Local Manual Market",
            source_kind="user_entered",
            permitted_use_confirmed=permission,
            private_source_reference="do-not-return-this",
        ),
    }


def _database_counts(client: TestClient) -> tuple[int, int, int]:
    with client.app.state.session_factory() as session:
        snapshot_count = session.scalar(
            select(func.count()).select_from(AlertEvidenceSnapshotRow)
        )
        player_count = session.scalar(
            select(func.count()).select_from(AlertPlayerSignalRow)
        )
        pick_count = session.scalar(
            select(func.count()).select_from(AlertPickValueSignalRow)
        )
    return (
        int(snapshot_count or 0),
        int(player_count or 0),
        int(pick_count or 0),
    )


def test_synthetic_preview_commit_reads_and_idempotency(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        _seed_players(client)
        assert _database_counts(client) == (0, 0, 0)

        preview = client.post(
            "/api/v1/alert-evidence-imports/preview",
            json=_synthetic_payload(),
        )
        assert preview.status_code == 201
        body = preview.json()
        assert body["content_hash"] == SYNTHETIC_HASH
        assert body["matched_player_count"] == 6
        assert body["review_required_player_count"] == 0
        assert body["total_pick_value_count"] == 17
        assert body["expected_selection_available"] is True
        assert body["pick_curve_available"] is True
        assert body["freshness_states"] == {
            "expected_selection": "fresh",
            "dynasty_market": "fresh",
            "pick_value": "fresh",
            "in_season_production": "fresh",
        }
        assert _database_counts(client) == (0, 0, 0)

        commit = client.post(
            f"/api/v1/alert-evidence-imports/{body['id']}/commit",
            json={
                "content_hash": body["content_hash"],
                "permitted_use_confirmed": True,
            },
        )
        assert commit.status_code == 200
        committed = commit.json()
        assert committed["idempotent"] is False
        snapshot_id = committed["snapshot"]["id"]
        assert committed["snapshot"]["mapped_player_count"] == 6
        assert committed["snapshot"]["expected_selection_count"] == 5
        assert committed["snapshot"]["pick_value_count"] == 17
        assert _database_counts(client) == (1, 6, 17)

        repeated = client.post(
            f"/api/v1/alert-evidence-imports/{body['id']}/commit",
            json={
                "content_hash": body["content_hash"],
                "permitted_use_confirmed": True,
            },
        )
        assert repeated.status_code == 200
        assert repeated.json()["idempotent"] is True
        assert repeated.json()["snapshot"]["id"] == snapshot_id

        equivalent_payload = _synthetic_payload()
        equivalent_payload["metadata"]["private_source_reference"] = (
            "different-private-reference"
        )
        equivalent = client.post(
            "/api/v1/alert-evidence-imports/preview",
            json=equivalent_payload,
        )
        assert equivalent.status_code == 201
        assert equivalent.json()["content_hash"] == SYNTHETIC_HASH
        duplicate = client.post(
            f"/api/v1/alert-evidence-imports/{equivalent.json()['id']}/commit",
            json={
                "content_hash": SYNTHETIC_HASH,
                "permitted_use_confirmed": True,
            },
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["idempotent"] is True
        assert duplicate.json()["snapshot"]["id"] == snapshot_id
        assert _database_counts(client) == (1, 6, 17)

        listing = client.get("/api/v1/alert-evidence-snapshots")
        detail = client.get(f"/api/v1/alert-evidence-snapshots/{snapshot_id}")
        assert listing.status_code == detail.status_code == 200
        assert listing.json()["total"] == 1
        for response_text in (listing.text, detail.text, commit.text):
            assert "private-local-reference" not in response_text
            assert "different-private-reference" not in response_text
            assert "demo-qb-001" not in response_text


def test_name_suggestion_requires_confirmation_and_mapping_is_reused(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        _seed_players(client)
        payload = _single_player_payload(
            "manual-qb-1,Marcus Hale,QB,CHI,4,8,premium,high,middle,"
            "2026-07-28T00:00:00Z,"
        )
        preview = client.post(
            "/api/v1/alert-evidence-imports/preview",
            json=payload,
        )
        assert preview.status_code == 201
        body = preview.json()
        assert body["matched_player_count"] == 0
        assert body["review_required_player_count"] == 1
        row = body["rows"][0]
        assert len(row["candidates"]) == 1

        blocked = client.post(
            f"/api/v1/alert-evidence-imports/{body['id']}/commit",
            json={
                "content_hash": body["content_hash"],
                "permitted_use_confirmed": True,
            },
        )
        assert blocked.status_code == 409
        assert (
            blocked.json()["error"]["code"]
            == "IMPORT.ALERT_EVIDENCE.NO_USABLE_PLAYERS"
        )
        assert _database_counts(client) == (0, 0, 0)

        decided = client.put(
            f"/api/v1/alert-evidence-imports/{body['id']}/rows/"
            f"{row['id']}/decision",
            json={
                "decision": "confirm",
                "player_id": row["candidates"][0]["id"],
            },
        )
        assert decided.status_code == 200
        assert decided.json()["matched_player_count"] == 1
        committed = client.post(
            f"/api/v1/alert-evidence-imports/{body['id']}/commit",
            json={
                "content_hash": body["content_hash"],
                "permitted_use_confirmed": True,
            },
        )
        assert committed.status_code == 200
        assert committed.json()["snapshot"]["mapped_player_count"] == 1

        repeat_payload = _single_player_payload(
            "manual-qb-1,Renamed Source Label,QB,NYJ,5,9,strong,medium,middle,"
            "2026-07-28T00:00:00Z,"
        )
        repeat = client.post(
            "/api/v1/alert-evidence-imports/preview",
            json=repeat_payload,
        )
        assert repeat.status_code == 201
        assert repeat.json()["matched_player_count"] == 1
        assert repeat.json()["review_required_player_count"] == 0
        assert (
            repeat.json()["rows"][0]["resolved_player_id"]
            == row["candidates"][0]["id"]
        )

        with client.app.state.session_factory() as session:
            mapping = session.scalar(
                select(PlayerExternalIdRow).where(
                    PlayerExternalIdRow.provider == "manual_market",
                    PlayerExternalIdRow.external_id == "manual-qb-1",
                )
            )
            assert mapping is not None
            assert mapping.is_manual_override is True


def test_unmatched_and_ignored_rows_never_become_active_signals(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        _seed_players(client)
        payload = _synthetic_payload()
        payload["pick_filename"] = None
        payload["pick_csv_text"] = None
        payload["player_csv_text"] = (
            "source_player_key,display_name,position,team,"
            "expected_pick_low,expected_pick_high,market_band,"
            "win_now_production_band,age_risk_band,evidence_as_of,"
            "limitation_codes\n"
            "demo-qb-001,Marcus Hale,QB,CHI,4,8,premium,high,middle,"
            "2026-07-28T00:00:00Z,\n"
            "unknown-1,Unknown Prospect,WR,FA,20,30,standard,medium,lower,"
            "2026-07-28T00:00:00Z,\n"
        )
        preview = client.post(
            "/api/v1/alert-evidence-imports/preview",
            json=payload,
        )
        assert preview.status_code == 201
        assert preview.json()["matched_player_count"] == 1
        assert preview.json()["unmatched_player_count"] == 1

        committed = client.post(
            f"/api/v1/alert-evidence-imports/{preview.json()['id']}/commit",
            json={
                "content_hash": preview.json()["content_hash"],
                "permitted_use_confirmed": True,
            },
        )
        assert committed.status_code == 200
        assert committed.json()["snapshot"]["mapped_player_count"] == 1
        assert _database_counts(client) == (1, 1, 0)


def test_invalid_player_can_be_ignored_but_unsafe_package_inputs_are_rejected(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        _seed_players(client)
        payload = _synthetic_payload()
        payload["pick_filename"] = None
        payload["pick_csv_text"] = None
        payload["player_csv_text"] = (
            "source_player_key,display_name,position,team,"
            "expected_pick_low,expected_pick_high,market_band,"
            "win_now_production_band,age_risk_band,evidence_as_of,"
            "limitation_codes\n"
            "demo-qb-001,Marcus Hale,QB,CHI,4,8,premium,high,middle,"
            "2026-07-28T00:00:00Z,\n"
            "bad-range,Bad Range,RB,ATL,30,20,strong,medium,middle,"
            "2026-07-28T00:00:00Z,\n"
        )
        preview = client.post(
            "/api/v1/alert-evidence-imports/preview",
            json=payload,
        )
        assert preview.status_code == 201
        assert preview.json()["invalid_player_count"] == 1
        invalid_row = next(
            row for row in preview.json()["rows"] if row["status"] == "invalid"
        )
        blocked = client.post(
            f"/api/v1/alert-evidence-imports/{preview.json()['id']}/commit",
            json={
                "content_hash": preview.json()["content_hash"],
                "permitted_use_confirmed": True,
            },
        )
        assert blocked.status_code == 409
        assert (
            blocked.json()["error"]["code"]
            == "VALIDATION.ALERT_EVIDENCE.INVALID_ROW"
        )
        ignored = client.put(
            f"/api/v1/alert-evidence-imports/{preview.json()['id']}/rows/"
            f"{invalid_row['id']}/decision",
            json={"decision": "ignore"},
        )
        assert ignored.status_code == 200
        assert ignored.json()["invalid_player_count"] == 0
        committed = client.post(
            f"/api/v1/alert-evidence-imports/{preview.json()['id']}/commit",
            json={
                "content_hash": preview.json()["content_hash"],
                "permitted_use_confirmed": True,
            },
        )
        assert committed.status_code == 200
        assert committed.json()["snapshot"]["mapped_player_count"] == 1

        duplicate = _single_player_payload(
            "same,Marcus Hale,QB,CHI,4,8,premium,high,middle,"
            "2026-07-28T00:00:00Z,\n"
            "same,Devin Cross Jr.,RB,ATL,12,20,strong,high,higher,"
            "2026-07-28T00:00:00Z,"
        )
        duplicate_response = client.post(
            "/api/v1/alert-evidence-imports/preview",
            json=duplicate,
        )
        assert duplicate_response.status_code == 422
        assert (
            duplicate_response.json()["error"]["code"]
            == "VALIDATION.ALERT_EVIDENCE.DUPLICATE_PLAYER"
        )

        bad_header = _single_player_payload(
            "one,Marcus Hale,QB,CHI,4,8,premium,high,middle,"
            "2026-07-28T00:00:00Z,"
        )
        bad_header["player_csv_text"] = str(
            bad_header["player_csv_text"]
        ).replace("limitation_codes", "extra_column")
        header_response = client.post(
            "/api/v1/alert-evidence-imports/preview",
            json=bad_header,
        )
        assert header_response.status_code == 422
        assert (
            header_response.json()["error"]["code"]
            == "VALIDATION.ALERT_EVIDENCE.INVALID_HEADER"
        )

        bad_curve = _synthetic_payload()
        bad_curve["pick_csv_text"] = str(bad_curve["pick_csv_text"]).replace(
            "startup-pick-010,current_draft_pick,10,,,850,900",
            "startup-pick-010,current_draft_pick,10,,,1100,1200",
        )
        curve_response = client.post(
            "/api/v1/alert-evidence-imports/preview",
            json=bad_curve,
        )
        assert curve_response.status_code == 422
        assert (
            curve_response.json()["error"]["code"]
            == "VALIDATION.ALERT_EVIDENCE.INVALID_CURVE"
        )


def test_permission_hash_and_future_timestamp_guards(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        _seed_players(client)
        unconfirmed = client.post(
            "/api/v1/alert-evidence-imports/preview",
            json=_single_player_payload(
                "permission-1,Marcus Hale,QB,CHI,4,8,premium,high,middle,"
                "2026-07-28T00:00:00Z,",
                permission=False,
            ),
        )
        assert unconfirmed.status_code == 201
        blocked_permission = client.post(
            f"/api/v1/alert-evidence-imports/{unconfirmed.json()['id']}/commit",
            json={
                "content_hash": unconfirmed.json()["content_hash"],
                "permitted_use_confirmed": True,
            },
        )
        assert blocked_permission.status_code == 409
        assert (
            blocked_permission.json()["error"]["code"]
            == "IMPORT.ALERT_EVIDENCE.PERMISSION_UNCONFIRMED"
        )

        preview = client.post(
            "/api/v1/alert-evidence-imports/preview",
            json=_single_player_payload(
                "hash-1,Marcus Hale,QB,CHI,4,8,premium,high,middle,"
                "2026-07-28T00:00:00Z,"
            ),
        )
        assert preview.status_code == 201
        changed = client.post(
            f"/api/v1/alert-evidence-imports/{preview.json()['id']}/commit",
            json={
                "content_hash": "0" * 64,
                "permitted_use_confirmed": True,
            },
        )
        assert changed.status_code == 409
        assert (
            changed.json()["error"]["code"]
            == "IMPORT.ALERT_EVIDENCE.PREVIEW_CHANGED"
        )

        future = _single_player_payload(
            "future-1,Marcus Hale,QB,CHI,4,8,premium,high,middle,"
            "2099-01-01T00:00:00Z,"
        )
        future["metadata"]["as_of"] = "2099-01-01T00:00:00Z"
        future_response = client.post(
            "/api/v1/alert-evidence-imports/preview",
            json=future,
        )
        assert future_response.status_code == 422
        assert (
            future_response.json()["error"]["code"]
            == "VALIDATION.ALERT_EVIDENCE.FUTURE_TIMESTAMP"
        )
        assert _database_counts(client) == (0, 0, 0)


def test_commit_rolls_back_all_rows_on_late_failure(
    runtime_settings: RuntimeSettings,
    monkeypatch: object,
) -> None:
    from friendly_hub.domains.alerts import service as alert_service

    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        _seed_players(client)
        preview = client.post(
            "/api/v1/alert-evidence-imports/preview",
            json=_synthetic_payload(),
        )
        assert preview.status_code == 201

        def fail_commit(_: object) -> None:
            raise RuntimeError("forced late failure")

        monkeypatch.setattr(alert_service, "_commit_transaction", fail_commit)
        failed = client.post(
            f"/api/v1/alert-evidence-imports/{preview.json()['id']}/commit",
            json={
                "content_hash": preview.json()["content_hash"],
                "permitted_use_confirmed": True,
            },
        )
        assert failed.status_code == 500
        assert (
            failed.json()["error"]["code"]
            == "IMPORT.ALERT_EVIDENCE.COMMIT_FAILED"
        )
        assert _database_counts(client) == (0, 0, 0)


def test_alert_evidence_routes_are_in_openapi(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        schema = client.get("/openapi.json")
        assert schema.status_code == 200
        paths = schema.json()["paths"]
        assert "/api/v1/alert-evidence-imports/preview" in paths
        assert "/api/v1/alert-evidence-imports/{preview_id}/commit" in paths
        assert "/api/v1/alert-evidence-snapshots" in paths
        assert "/api/v1/alert-evidence-snapshots/{snapshot_id}" in paths
