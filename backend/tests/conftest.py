import json
from pathlib import Path

import pytest

from friendly_hub.core.settings import RuntimeSettings


@pytest.fixture
def runtime_settings(tmp_path: Path) -> RuntimeSettings:
    project_root = Path(__file__).resolve().parents[2]
    data_dir = tmp_path / "data"
    return RuntimeSettings(
        project_root=project_root,
        data_dir=data_dir,
        database_path=data_dir / "hub.sqlite3",
        log_dir=data_dir / "logs",
        frontend_dist=tmp_path / "missing-frontend",
        sample_fixture_path=project_root
        / "tests"
        / "fixtures"
        / "league_profiles"
        / "entropy-2026.sanitized.json",
    )


@pytest.fixture
def api_error_schema() -> dict[str, object]:
    project_root = Path(__file__).resolve().parents[2]
    schema_path = project_root / "docs" / "schemas" / "api-error.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))
