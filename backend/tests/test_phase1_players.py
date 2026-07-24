from fastapi.testclient import TestClient

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}


def _preview_and_commit_fixture(client: TestClient) -> dict[str, object]:
    preview = client.post("/api/v1/player-imports/fixture/preview")
    assert preview.status_code == 201
    assert preview.json()["new_count"] == 6
    committed = client.post(
        f"/api/v1/player-imports/{preview.json()['id']}/commit"
    )
    assert committed.status_code == 200
    assert committed.json()["created_players"] == 6
    return committed.json()


def test_fixture_import_is_idempotent(runtime_settings: RuntimeSettings) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        _preview_and_commit_fixture(client)

        repeat_preview = client.post("/api/v1/player-imports/fixture/preview")
        assert repeat_preview.status_code == 201
        assert repeat_preview.json()["matched_count"] == 6
        assert repeat_preview.json()["new_count"] == 0

        repeat_commit = client.post(
            f"/api/v1/player-imports/{repeat_preview.json()['id']}/commit"
        )
        assert repeat_commit.status_code == 200
        assert repeat_commit.json()["created_players"] == 0

        players = client.get("/api/v1/players")
        assert players.status_code == 200
        assert players.json()["total"] == 6
        assert len({player["id"] for player in players.json()["items"]}) == 6


def test_name_match_requires_review_and_manual_mapping_persists(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        _preview_and_commit_fixture(client)
        csv_text = (
            "name,position,provider,external_id\n"
            "Devin Cross Jr.,RB,csv,d-cross\n"
        )
        preview = client.post(
            "/api/v1/player-imports/csv/preview",
            json={"filename": "review.csv", "csv_text": csv_text},
        )
        assert preview.status_code == 201
        row = preview.json()["rows"][0]
        assert row["outcome"] == "ambiguous"
        assert len(row["candidate_players"]) == 1

        blocked = client.post(
            f"/api/v1/player-imports/{preview.json()['id']}/commit"
        )
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "IMPORT.PLAYER.REVIEW_REQUIRED"

        decided = client.put(
            f"/api/v1/player-imports/{preview.json()['id']}/rows/{row['id']}/decision",
            json={
                "decision": "match_existing",
                "player_id": row["candidate_players"][0]["id"],
            },
        )
        assert decided.status_code == 200
        assert decided.json()["matched_count"] == 1

        committed = client.post(
            f"/api/v1/player-imports/{preview.json()['id']}/commit"
        )
        assert committed.status_code == 200
        assert committed.json()["created_players"] == 0
        preserved = client.get(
            f"/api/v1/players/{row['candidate_players'][0]['id']}"
        )
        assert preserved.json()["team"] == "ATL"
        assert preserved.json()["status"] == "active"

        repeat = client.post(
            "/api/v1/player-imports/csv/preview",
            json={"filename": "review.csv", "csv_text": csv_text},
        )
        assert repeat.status_code == 201
        assert repeat.json()["matched_count"] == 1
        assert repeat.json()["ambiguous_count"] == 0


def test_duplicate_external_id_is_never_silently_committed(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        preview = client.post(
            "/api/v1/player-imports/csv/preview",
            json={
                "filename": "duplicate.csv",
                "csv_text": (
                    "name,position,provider,external_id\n"
                    "First Runner,RB,csv,same-id\n"
                    "Second Runner,RB,csv,same-id\n"
                ),
            },
        )
        assert preview.status_code == 201
        assert preview.json()["new_count"] == 1
        assert preview.json()["invalid_count"] == 1
        invalid = next(
            row for row in preview.json()["rows"] if row["outcome"] == "invalid"
        )
        assert invalid["reason_code"] == "IMPORT.PLAYER.DUPLICATE_EXTERNAL_ID"
        assert (
            client.post(
                f"/api/v1/player-imports/{preview.json()['id']}/commit"
            ).status_code
            == 409
        )


def test_invalid_row_can_be_ignored_before_atomic_commit(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        preview = client.post(
            "/api/v1/player-imports/csv/preview",
            json={
                "filename": "mixed.csv",
                "csv_text": "name,position\nValid Runner,RB\nMissing Position,\n",
            },
        )
        assert preview.status_code == 201
        assert preview.json()["new_count"] == 1
        assert preview.json()["invalid_count"] == 1

        blocked = client.post(
            f"/api/v1/player-imports/{preview.json()['id']}/commit"
        )
        assert blocked.status_code == 409
        assert client.get("/api/v1/players").json()["total"] == 0

        invalid_row = next(
            row for row in preview.json()["rows"] if row["outcome"] == "invalid"
        )
        ignored = client.put(
            f"/api/v1/player-imports/{preview.json()['id']}/rows/{invalid_row['id']}/decision",
            json={"decision": "ignore"},
        )
        assert ignored.status_code == 200
        assert ignored.json()["invalid_count"] == 0
        assert ignored.json()["ignored_count"] == 1

        restored = client.put(
            f"/api/v1/player-imports/{preview.json()['id']}/rows/{invalid_row['id']}/decision",
            json={"decision": "clear"},
        )
        assert restored.status_code == 200
        assert restored.json()["invalid_count"] == 1
        assert restored.json()["ignored_count"] == 0

        ignored = client.put(
            f"/api/v1/player-imports/{preview.json()['id']}/rows/{invalid_row['id']}/decision",
            json={"decision": "ignore"},
        )
        assert ignored.status_code == 200

        committed = client.post(
            f"/api/v1/player-imports/{preview.json()['id']}/commit"
        )
        assert committed.status_code == 200
        assert committed.json()["created_players"] == 1
        assert client.get("/api/v1/players").json()["total"] == 1


def test_search_filters_manual_correction_and_csv_export(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        _preview_and_commit_fixture(client)

        search = client.get("/api/v1/players", params={"search": "CROSS JR"})
        assert search.status_code == 200
        assert [player["display_name"] for player in search.json()["items"]] == [
            "Devin Cross Jr."
        ]

        rookies = client.get(
            "/api/v1/players",
            params={"position": "WR", "rookie_class": 2026, "status": "active"},
        )
        assert rookies.status_code == 200
        assert [player["display_name"] for player in rookies.json()["items"]] == [
            "Elias North"
        ]

        player_id = search.json()["items"][0]["id"]
        corrected = client.patch(
            f"/api/v1/players/{player_id}",
            json={"display_name": "Devin Cross II", "team": "NYJ"},
        )
        assert corrected.status_code == 200
        assert corrected.json()["suffix"] == "II"
        assert corrected.json()["team"] == "NYJ"

        exported = client.get("/api/v1/players/export.csv")
        assert exported.status_code == 200
        assert "canonical_id,name,position" in exported.text
        assert player_id in exported.text
