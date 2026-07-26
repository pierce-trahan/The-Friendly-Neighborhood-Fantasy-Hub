import csv
import io

from fastapi.testclient import TestClient

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}


def _seed_players(client: TestClient) -> list[dict[str, object]]:
    preview = client.post("/api/v1/player-imports/fixture/preview")
    assert preview.status_code == 201
    committed = client.post(
        f"/api/v1/player-imports/{preview.json()['id']}/commit"
    )
    assert committed.status_code == 200
    players = client.get("/api/v1/players", params={"limit": 100})
    assert players.status_code == 200
    return players.json()["items"]


def _create_board(
    client: TestClient,
    *,
    name: str = "Dynasty Startup",
    scope: str = "overall",
) -> dict[str, object]:
    response = client.post("/api/v1/boards", json={"name": name, "scope": scope})
    assert response.status_code == 201
    return response.json()


def test_board_and_player_add_are_persistent_and_idempotent(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        players = _seed_players(client)
        board = _create_board(client)
        player_id = players[0]["id"]

        added = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": player_id},
        )
        assert added.status_code == 200
        assert added.json()["entry_count"] == 1

        repeated = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": player_id},
        )
        assert repeated.status_code == 200
        assert repeated.json()["entry_count"] == 1
        assert repeated.json()["entries"][0]["player"]["id"] == player_id

        rookie_board = _create_board(client, name="Rookie Board", scope="rookie")
        independent = client.post(
            f"/api/v1/boards/{rookie_board['id']}/entries",
            json={"player_id": player_id},
        )
        assert independent.status_code == 200
        assert independent.json()["entry_count"] == 1

    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        restored = client.get(f"/api/v1/boards/{board['id']}")
        assert restored.status_code == 200
        assert restored.json()["entry_count"] == 1


def test_manual_order_is_atomic_and_authoritative(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        players = _seed_players(client)
        board = _create_board(client)
        player_ids = [player["id"] for player in players[:3]]
        for player_id in player_ids:
            assert (
                client.post(
                    f"/api/v1/boards/{board['id']}/entries",
                    json={"player_id": player_id},
                ).status_code
                == 200
            )

        requested_order = list(reversed(player_ids))
        reordered = client.put(
            f"/api/v1/boards/{board['id']}/order",
            json={"player_ids": requested_order},
        )
        assert reordered.status_code == 200
        assert [
            entry["player"]["id"] for entry in reordered.json()["entries"]
        ] == requested_order
        assert [entry["rank"] for entry in reordered.json()["entries"]] == [1, 2, 3]

        incomplete = client.put(
            f"/api/v1/boards/{board['id']}/order",
            json={"player_ids": requested_order[:-1]},
        )
        assert incomplete.status_code == 409
        duplicate = client.put(
            f"/api/v1/boards/{board['id']}/order",
            json={"player_ids": [requested_order[0]] * 3},
        )
        assert duplicate.status_code == 409

        unchanged = client.get(f"/api/v1/boards/{board['id']}")
        assert [
            entry["player"]["id"] for entry in unchanged.json()["entries"]
        ] == requested_order


def test_tiers_notes_favorites_and_tier_removal_persist(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        players = _seed_players(client)
        board = _create_board(client)
        player_id = players[0]["id"]
        board = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": player_id},
        ).json()

        lower = client.post(
            f"/api/v1/boards/{board['id']}/tiers",
            json={"name": "Tier 2", "color": "#8aa09a"},
        )
        assert lower.status_code == 200
        upper = client.post(
            f"/api/v1/boards/{board['id']}/tiers",
            json={"name": "Tier 1", "color": "#a8ff60", "tier_order": 1},
        )
        assert upper.status_code == 200
        assert [tier["name"] for tier in upper.json()["tiers"]] == [
            "Tier 1",
            "Tier 2",
        ]
        tier_id = upper.json()["tiers"][0]["id"]
        entry_id = upper.json()["entries"][0]["id"]

        updated = client.patch(
            f"/api/v1/boards/{board['id']}/entries/{entry_id}",
            json={
                "tier_id": tier_id,
                "note": "My conviction is higher than the market.",
                "favorite": True,
            },
        )
        assert updated.status_code == 200
        entry = updated.json()["entries"][0]
        assert entry["tier_id"] == tier_id
        assert entry["favorite"] is True
        assert entry["note"] == "My conviction is higher than the market."

        other_board = _create_board(client, name="Other Board")
        foreign_tier = client.post(
            f"/api/v1/boards/{other_board['id']}/tiers",
            json={"name": "Foreign Tier"},
        ).json()["tiers"][0]
        rejected_foreign_tier = client.patch(
            f"/api/v1/boards/{board['id']}/entries/{entry_id}",
            json={"tier_id": foreign_tier["id"]},
        )
        assert rejected_foreign_tier.status_code == 404
        unchanged_entry = client.get(f"/api/v1/boards/{board['id']}").json()[
            "entries"
        ][0]
        assert unchanged_entry["tier_id"] == tier_id

        duplicate = client.post(
            f"/api/v1/boards/{board['id']}/tiers",
            json={"name": "tier 1"},
        )
        assert duplicate.status_code == 409

        tier_removed = client.delete(
            f"/api/v1/boards/{board['id']}/tiers/{tier_id}"
        )
        assert tier_removed.status_code == 200
        preserved_entry = tier_removed.json()["entries"][0]
        assert preserved_entry["tier_id"] is None
        assert preserved_entry["favorite"] is True
        assert preserved_entry["note"] == "My conviction is higher than the market."


def test_remove_and_readd_restores_player_work(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        players = _seed_players(client)
        board = _create_board(client)
        first_id, second_id, third_id = [player["id"] for player in players[:3]]
        for player_id in (first_id, second_id, third_id):
            board = client.post(
                f"/api/v1/boards/{board['id']}/entries",
                json={"player_id": player_id},
            ).json()

        last_entry = board["entries"][2]
        customized = client.patch(
            f"/api/v1/boards/{board['id']}/entries/{last_entry['id']}",
            json={"note": "Keep this note.", "favorite": True},
        )
        assert customized.status_code == 200

        removed = client.delete(
            f"/api/v1/boards/{board['id']}/entries/{last_entry['id']}"
        )
        assert removed.status_code == 200
        assert [entry["player"]["id"] for entry in removed.json()["entries"]] == [
            first_id,
            second_id
        ]
        assert [entry["rank"] for entry in removed.json()["entries"]] == [1, 2]

        restored = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": third_id},
        )
        assert restored.status_code == 200
        restored_entry = restored.json()["entries"][2]
        assert restored_entry["player"]["id"] == third_id
        assert restored_entry["rank"] == 3
        assert restored_entry["note"] == "Keep this note."
        assert restored_entry["favorite"] is True


def test_board_archive_errors_and_csv_export_are_safe(
    runtime_settings: RuntimeSettings,
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        players = _seed_players(client)
        board = _create_board(client)
        player_id = players[0]["id"]
        board = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": player_id},
        ).json()
        entry_id = board["entries"][0]["id"]
        note = "=private spreadsheet formula"
        client.patch(
            f"/api/v1/boards/{board['id']}/entries/{entry_id}",
            json={"note": note},
        )

        exported = client.get(f"/api/v1/boards/{board['id']}/export.csv")
        assert exported.status_code == 200
        rows = list(csv.DictReader(io.StringIO(exported.text)))
        assert rows[0]["rank"] == "1"
        assert rows[0]["canonical_player_id"] == player_id
        assert rows[0]["note"] == f"'{note}"
        assert "external_id" not in exported.text

        missing_id = "00000000-0000-0000-0000-000000000000"
        missing = client.post(
            f"/api/v1/boards/{board['id']}/entries",
            json={"player_id": missing_id},
        )
        assert missing.status_code == 404
        assert missing_id not in missing.text
        assert note not in missing.text

        archived = client.patch(
            f"/api/v1/boards/{board['id']}",
            json={"archived": True},
        )
        assert archived.status_code == 200
        assert archived.json()["archived"] is True
        assert client.get("/api/v1/boards").json()["items"] == []
        included = client.get(
            "/api/v1/boards", params={"include_archived": True}
        ).json()
        assert included["items"][0]["id"] == board["id"]
        blocked = client.patch(
            f"/api/v1/boards/{board['id']}/entries/{entry_id}",
            json={"favorite": True},
        )
        assert blocked.status_code == 409

        restored = client.patch(
            f"/api/v1/boards/{board['id']}",
            json={"archived": False},
        )
        assert restored.status_code == 200
        assert restored.json()["archived"] is False
