from fastapi.testclient import TestClient
from jsonschema import validate

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.main import create_app

TRUSTED_HEADERS = {"X-Friendly-Hub-Request": "1"}


def test_health_and_default_configuration(runtime_settings: RuntimeSettings) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.json()["app_version"] == "1.0.0"

        configuration = client.get("/api/v1/config")
        assert configuration.status_code == 200
        assert configuration.json()["display"]["timezone"] == "America/Chicago"


def test_configuration_survives_restart(runtime_settings: RuntimeSettings) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        configuration = client.get("/api/v1/config").json()
        configuration["display"]["theme"] = "dark"
        saved = client.put("/api/v1/config", json=configuration)
        assert saved.status_code == 200

    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as restarted_client:
        restored = restarted_client.get("/api/v1/config")
        assert restored.status_code == 200
        assert restored.json()["display"]["theme"] == "dark"


def test_entropy_fixture_loads_without_network(runtime_settings: RuntimeSettings) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        imported = client.post("/api/v1/league-profiles/samples/entropy")
        assert imported.status_code == 201
        assert imported.json()["name"] == "Entropy"
        assert imported.json()["team_count"] == 10
        assert imported.json()["sanitized"] is True
        assert imported.json()["source_as_of"] == "2026-08-03T13:39:45Z"

        profiles = client.get("/api/v1/league-profiles")
        assert profiles.status_code == 200
        assert [profile["name"] for profile in profiles.json()] == ["Entropy"]


def test_invalid_configuration_uses_safe_error_envelope(
    runtime_settings: RuntimeSettings,
    api_error_schema: dict[str, object],
) -> None:
    with TestClient(create_app(runtime_settings), headers=TRUSTED_HEADERS) as client:
        response = client.put(
            "/api/v1/config",
            json={
                "schema_version": 1,
                "active_league_season_id": None,
                "display": {
                    "timezone": "America/Chicago",
                    "theme": "neon",
                    "reduced_motion": False,
                },
                "backups": {"automatic": True, "retention_count": 10},
                "safety": {"confirm_reset": True, "confirm_delete": True},
            },
        )

    assert response.status_code == 422
    payload = response.json()["error"]
    assert payload["code"] == "VALIDATION.REQUEST.INVALID"
    assert "correlation_id" in payload
    assert "neon" not in response.text
    validate(response.json(), api_error_schema)


def test_local_write_guard_rejects_untrusted_requests(
    runtime_settings: RuntimeSettings,
    api_error_schema: dict[str, object],
) -> None:
    with TestClient(create_app(runtime_settings)) as client:
        response = client.post("/api/v1/league-profiles/samples/entropy")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SECURITY.REQUEST.GUARD_REQUIRED"
    validate(response.json(), api_error_schema)
