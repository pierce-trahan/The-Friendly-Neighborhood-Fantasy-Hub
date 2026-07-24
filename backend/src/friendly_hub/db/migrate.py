from __future__ import annotations

from alembic import command
from alembic.config import Config

from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.db.engine import sqlite_url


def run_migrations(settings: RuntimeSettings) -> None:
    backend_root = settings.project_root / "backend"
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))
    config.set_main_option("sqlalchemy.url", sqlite_url(settings.database_path))
    command.upgrade(config, "head")
