from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.domains.alerts import configuration_service
from friendly_hub.domains.alerts.models import (
    DraftAlertConfigurationRevisionRow,
    DraftAlertConfigurationRow,
)
from friendly_hub.domains.drafts.models import DraftSessionRow
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}


def _fixture_root() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _seed_workspace(
    client: TestClient,
) -> tuple[dict[str, object], dict[str, object]]:
    preview = client.post("/api/v1/player-imports/fixture/preview")
    assert preview.status_code == 201
    committed = client.post(f"/api/v1/player-imports/{preview.json()['id']}/commit")
    assert committed.status_code == 200
    players = client.get("/api/v1/players", params={"limit": 100}).json()["items"]

    board_response = client.post(
        "/api/v1/boards",
        json={"name": "Phase 5 Board", "scope": "overall"},
    )
    assert board_response.status_code == 201
    board = board_response.json()
    for player in players[:3]:
        response = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": player["id"]},
        )
        assert response.status_code == 200

    profile_response = client.post("/api/v1/league-profiles/samples/entropy")
    assert profile_response.status_code == 201
    return board, profile_response.json()


def _create_draft(
    client: TestClient,
    board_id: str,
    *,
    profile_id: str | None,
    name: str,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/boards/{board_id}/draft-sessions",
        json={
            "name": name,
            "mode": "live",
            "league_profile_id": profile_id,
            "draft_format": "snake",
            "third_round_reversal": True,
            "team_count": 10,
            "round_count": 24,
            "user_slot": 7,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _evidence_payload(**overrides: object) -> dict[str, object]:
    evidence_root = _fixture_root() / "alert_evidence"
    metadata: dict[str, object] = {
        "snapshot_key": "phase-5-alert-config-exact",
        "source_label": "Neighborhood Synthetic Market",
        "source_kind": "synthetic",
        "source_namespace": "sanitized_fixture",
        "permitted_use_confirmed": True,
        "private_source_reference": "configuration-private-reference",
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
    return {
        "player_filename": "player-signals.synthetic.csv",
        "player_csv_text": (evidence_root / "player-signals.synthetic.csv").read_text(
            encoding="utf-8"
        ),
        "pick_filename": "pick-values.synthetic.csv",
        "pick_csv_text": (evidence_root / "pick-values.synthetic.csv").read_text(encoding="utf-8"),
        "metadata": metadata,
    }


def _commit_evidence(
    client: TestClient,
    **metadata_overrides: object,
) -> dict[str, object]:
    preview = client.post(
        "/api/v1/alert-evidence-imports/preview",
        json=_evidence_payload(**metadata_overrides),
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
    return committed.json()["snapshot"]


def _attach(
    client: TestClient,
    draft: dict[str, object],
    snapshot_id: str,
) -> object:
    return client.post(
        f"/api/v1/draft-sessions/{draft['id']}/alert-configuration",
        json={
            "draft_revision": draft["revision"],
            "evidence_snapshot_id": snapshot_id,
        },
    )


def test_configuration_attach_update_history_and_restart(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, profile = _seed_workspace(client)
        draft = _create_draft(
            client,
            str(board["id"]),
            profile_id=str(profile["id"]),
            name="Configured Draft",
        )
        snapshot = _commit_evidence(client)

        attached = _attach(client, draft, str(snapshot["id"]))
        assert attached.status_code == 201, attached.text
        body = attached.json()
        assert body["draft_revision"] == 0
        assert body["revision"] == 0
        assert body["enabled"] is True
        assert body["personal_qualifier_mode"] == "tier_or_favorite"
        assert body["eligible_tier_count"] == 2
        assert body["minimum_conservative_gap"] == 6
        assert body["snooze_pick_count"] == 5
        assert body["engine_version"] == "alert-engine-v1"
        assert body["rule_version"] == "alert-rules-v1"
        assert body["freshness_policy_version"] == "alert-freshness-v1"
        assert body["format_compatibility"] == "exact"
        assert body["compatibility_reasons"] == []
        assert body["evidence_snapshot"]["compatibility_state"] == "exact"
        assert "configuration-private-reference" not in attached.text
        assert "demo-qb-001" not in attached.text

        updated = client.patch(
            f"/api/v1/draft-sessions/{draft['id']}/alert-configuration",
            json={
                "draft_revision": 0,
                "configuration_revision": 0,
                "enabled": False,
                "minimum_conservative_gap": 8,
            },
        )
        assert updated.status_code == 200, updated.text
        changed = updated.json()
        assert changed["draft_revision"] == 0
        assert changed["revision"] == 1
        assert changed["enabled"] is False
        assert changed["minimum_conservative_gap"] == 8

        with client.app.state.session_factory() as session:
            saved_draft = session.get(DraftSessionRow, str(draft["id"]))
            configuration = session.scalar(
                select(DraftAlertConfigurationRow).where(
                    DraftAlertConfigurationRow.draft_session_id == draft["id"]
                )
            )
            revisions = list(
                session.scalars(
                    select(DraftAlertConfigurationRevisionRow)
                    .where(DraftAlertConfigurationRevisionRow.configuration_id == configuration.id)
                    .order_by(DraftAlertConfigurationRevisionRow.sequence_number)
                )
            )
            assert saved_draft is not None
            assert saved_draft.revision == 0
            assert configuration is not None
            assert configuration.revision == 1
            assert [row.sequence_number for row in revisions] == [1, 2]
            assert [row.reason for row in revisions] == [
                "initial",
                "settings_changed",
            ]
            assert revisions[0].previous_evidence_snapshot_id is None
            assert json.loads(revisions[1].previous_settings_json)["enabled"] is True
            assert json.loads(revisions[1].next_settings_json)["enabled"] is False
        session_id = str(draft["id"])

    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        restored = client.get(f"/api/v1/draft-sessions/{session_id}/alert-configuration")
        assert restored.status_code == 200
        assert restored.json()["revision"] == 1
        assert restored.json()["enabled"] is False
        assert restored.json()["format_compatibility"] == "exact"


def test_snapshot_replacement_and_both_revision_guards(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, profile = _seed_workspace(client)
        draft = _create_draft(
            client,
            str(board["id"]),
            profile_id=str(profile["id"]),
            name="Replacement Draft",
        )
        first = _commit_evidence(client)
        second = _commit_evidence(
            client,
            snapshot_key="phase-5-alert-config-replacement",
            source_label="Neighborhood Synthetic Market Update",
            as_of="2026-07-29T00:00:00Z",
        )
        incompatible = _commit_evidence(
            client,
            snapshot_key="phase-5-alert-config-replacement-incompatible",
            source_label="Incompatible Replacement",
            quarterback_mode="one_qb",
        )
        attached = _attach(client, draft, str(first["id"]))
        assert attached.status_code == 201

        paused = client.patch(
            f"/api/v1/draft-sessions/{draft['id']}",
            json={"revision": 0, "status": "paused"},
        )
        assert paused.status_code == 200
        assert paused.json()["revision"] == 1

        stale_draft = client.patch(
            f"/api/v1/draft-sessions/{draft['id']}/alert-configuration",
            json={
                "draft_revision": 0,
                "configuration_revision": 0,
                "evidence_snapshot_id": second["id"],
            },
        )
        assert stale_draft.status_code == 409
        assert stale_draft.json()["error"]["code"] == "ALERT_DRAFT_STALE_REVISION"

        replaced = client.patch(
            f"/api/v1/draft-sessions/{draft['id']}/alert-configuration",
            json={
                "draft_revision": 1,
                "configuration_revision": 0,
                "evidence_snapshot_id": second["id"],
            },
        )
        assert replaced.status_code == 200, replaced.text
        assert replaced.json()["revision"] == 1
        assert replaced.json()["draft_revision"] == 1
        assert replaced.json()["evidence_snapshot_id"] == second["id"]

        blocked_replacement = client.patch(
            f"/api/v1/draft-sessions/{draft['id']}/alert-configuration",
            json={
                "draft_revision": 1,
                "configuration_revision": 1,
                "evidence_snapshot_id": incompatible["id"],
            },
        )
        assert blocked_replacement.status_code == 409
        assert blocked_replacement.json()["error"]["code"] == "ALERT_EVIDENCE_INCOMPATIBLE"

        stale_configuration = client.patch(
            f"/api/v1/draft-sessions/{draft['id']}/alert-configuration",
            json={
                "draft_revision": 1,
                "configuration_revision": 0,
                "enabled": False,
            },
        )
        assert stale_configuration.status_code == 409
        assert stale_configuration.json()["error"]["code"] == "ALERT_CONFIGURATION_STALE_REVISION"

        with client.app.state.session_factory() as session:
            configuration = session.scalar(
                select(DraftAlertConfigurationRow).where(
                    DraftAlertConfigurationRow.draft_session_id == draft["id"]
                )
            )
            assert configuration is not None
            assert configuration.evidence_snapshot_id == second["id"]
            assert configuration.revision == 1
            revisions = list(
                session.scalars(
                    select(DraftAlertConfigurationRevisionRow)
                    .where(DraftAlertConfigurationRevisionRow.configuration_id == configuration.id)
                    .order_by(DraftAlertConfigurationRevisionRow.sequence_number)
                )
            )
            assert [row.reason for row in revisions] == [
                "initial",
                "snapshot_replaced",
            ]
            assert revisions[1].previous_evidence_snapshot_id == first["id"]
            assert revisions[1].next_evidence_snapshot_id == second["id"]


def test_format_compatibility_and_incompatible_or_unknown_blocking(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, profile = _seed_workspace(client)
        exact = _commit_evidence(client)
        family = _commit_evidence(
            client,
            snapshot_key="phase-5-alert-config-family",
            source_label="Family Format Evidence",
            round_count=20,
        )
        partial = _commit_evidence(
            client,
            snapshot_key="phase-5-alert-config-partial",
            source_label="Partial Format Evidence",
            tight_end_premium=False,
        )
        incompatible = _commit_evidence(
            client,
            snapshot_key="phase-5-alert-config-incompatible",
            source_label="Incompatible Format Evidence",
            quarterback_mode="one_qb",
        )

        family_draft = _create_draft(
            client,
            str(board["id"]),
            profile_id=str(profile["id"]),
            name="Family Draft",
        )
        family_response = _attach(client, family_draft, str(family["id"]))
        assert family_response.status_code == 201, family_response.text
        assert family_response.json()["format_compatibility"] == "family"
        assert family_response.json()["compatibility_reasons"] == ["ROUND_COUNT_DIFFERS"]

        partial_draft = _create_draft(
            client,
            str(board["id"]),
            profile_id=str(profile["id"]),
            name="Partial Draft",
        )
        partial_response = _attach(client, partial_draft, str(partial["id"]))
        assert partial_response.status_code == 201, partial_response.text
        assert partial_response.json()["format_compatibility"] == "partial"
        assert partial_response.json()["compatibility_reasons"] == ["TIGHT_END_PREMIUM_DIFFERS"]

        blocked_draft = _create_draft(
            client,
            str(board["id"]),
            profile_id=str(profile["id"]),
            name="Blocked Draft",
        )
        blocked = _attach(client, blocked_draft, str(incompatible["id"]))
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "ALERT_EVIDENCE_INCOMPATIBLE"
        assert "QUARTERBACK_MODE_DIFFERS" in blocked.json()["error"]["message"]

        unknown_draft = _create_draft(
            client,
            str(board["id"]),
            profile_id=None,
            name="Unknown Format Draft",
        )
        unknown = _attach(client, unknown_draft, str(exact["id"]))
        assert unknown.status_code == 409
        assert unknown.json()["error"]["code"] == "ALERT_EVIDENCE_INCOMPATIBLE"
        assert "(unknown:" in unknown.json()["error"]["message"]

        with client.app.state.session_factory() as session:
            configuration_count = session.scalar(
                select(func.count()).select_from(DraftAlertConfigurationRow)
            )
            assert configuration_count == 2


def test_configuration_not_found_guard_validation_and_openapi(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, profile = _seed_workspace(client)
        draft = _create_draft(
            client,
            str(board["id"]),
            profile_id=str(profile["id"]),
            name="Unconfigured Draft",
        )

        missing = client.get(f"/api/v1/draft-sessions/{draft['id']}/alert-configuration")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "ALERT_CONFIGURATION_NOT_FOUND"

        unguarded = client.post(
            f"/api/v1/draft-sessions/{draft['id']}/alert-configuration",
            headers={"X-Friendly-Hub-Request": "0"},
            json={
                "draft_revision": 0,
                "evidence_snapshot_id": "missing-snapshot",
            },
        )
        assert unguarded.status_code == 403
        assert unguarded.json()["error"]["code"] == "SECURITY.REQUEST.GUARD_REQUIRED"

        schema = client.get("/openapi.json")
        assert schema.status_code == 200
        path = schema.json()["paths"]["/api/v1/draft-sessions/{session_id}/alert-configuration"]
        assert {"get", "post", "patch"}.issubset(path)


def test_configuration_late_failure_rolls_back_all_rows(
    runtime_settings: RuntimeSettings,
    monkeypatch: object,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        board, profile = _seed_workspace(client)
        draft = _create_draft(
            client,
            str(board["id"]),
            profile_id=str(profile["id"]),
            name="Rollback Draft",
        )
        snapshot = _commit_evidence(client)

        def fail_commit(_: object) -> None:
            raise RuntimeError("forced late failure")

        monkeypatch.setattr(
            configuration_service,
            "_commit_transaction",
            fail_commit,
        )
        failed = _attach(client, draft, str(snapshot["id"]))
        assert failed.status_code == 500
        assert failed.json()["error"]["code"] == "ALERT_CONFIGURATION_SAVE_FAILED"

        with client.app.state.session_factory() as session:
            configuration_count = session.scalar(
                select(func.count()).select_from(DraftAlertConfigurationRow)
            )
            revision_count = session.scalar(
                select(func.count()).select_from(DraftAlertConfigurationRevisionRow)
            )
            saved_draft = session.get(DraftSessionRow, str(draft["id"]))
            assert configuration_count == 0
            assert revision_count == 0
            assert saved_draft is not None
            assert saved_draft.revision == 0
