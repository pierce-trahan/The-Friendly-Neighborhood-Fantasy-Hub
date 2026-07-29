from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from friendly_hub import __version__
from friendly_hub.api.correlation import CorrelationIdMiddleware
from friendly_hub.api.errors import register_error_handlers
from friendly_hub.api.router import router as api_router
from friendly_hub.core.logging import configure_logging
from friendly_hub.core.settings import RuntimeSettings
from friendly_hub.db.engine import create_database_engine, create_session_factory
from friendly_hub.db.migrate import run_migrations
from friendly_hub.domains.alerts.service import AlertEvidencePreviewStore
from friendly_hub.domains.configuration.service import ensure_default_configuration


def create_app(runtime: RuntimeSettings | None = None) -> FastAPI:
    runtime_settings = runtime or RuntimeSettings.from_environment()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        runtime_settings.ensure_directories()
        configure_logging(runtime_settings.log_dir)
        run_migrations(runtime_settings)
        engine = create_database_engine(runtime_settings.database_path)
        session_factory = create_session_factory(engine)
        application.state.runtime = runtime_settings
        application.state.engine = engine
        application.state.session_factory = session_factory
        application.state.alert_evidence_preview_store = AlertEvidencePreviewStore()
        with session_factory() as session:
            ensure_default_configuration(session)
        yield
        engine.dispose()

    application = FastAPI(
        title="Friendly Neighborhood Fantasy Hub",
        version=__version__,
        lifespan=lifespan,
    )
    application.add_middleware(CorrelationIdMiddleware)
    register_error_handlers(application)
    application.include_router(api_router)

    assets_dir = runtime_settings.frontend_dist / "assets"
    if assets_dir.is_dir():
        application.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @application.get("/{requested_path:path}", include_in_schema=False, response_model=None)
    def frontend(requested_path: str) -> Response:
        index_file = runtime_settings.frontend_dist / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
        return JSONResponse(
            {
                "name": "Friendly Neighborhood Fantasy Hub",
                "status": "backend-ready",
                "message": "Build the frontend to open the local interface.",
            }
        )

    return application


app = create_app()
