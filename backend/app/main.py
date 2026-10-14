"""NekoAI backend application factory.

Use create_app() (the launcher does). `uvicorn app.main:app` still works for
development: the module-level `app` is built lazily on first access.
"""
from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from typing import Callable, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import protected, public
from app.api.static import mount_frontend
from app.accounts import ensure_demo_account
from app.core.config import Settings, load_settings
from app.security import AuthState, auth_router, host_guard, security_headers
from app.services.neko_state import DEFAULT_CONFIG, StateStabilizer
from app.services.tracker import build_default_tracker
from app.services.focus import FocusStore

logger = logging.getLogger("neko")


def _default_report():
    from app.services.analytics import generate_daily_report  # imported lazily
    return generate_daily_report()


def create_app(
    settings: Optional[Settings] = None,
    *,
    tracker=None,
    bootstrap_token: Optional[str] = None,
    report_fn: Optional[Callable[[], dict]] = None,
    on_startup: Optional[Callable[[], None]] = None,
) -> FastAPI:
    settings = settings or load_settings()
    ensure_demo_account(settings.data_dir)
    focus_store = FocusStore(settings.data_dir)
    tracker = tracker or build_default_tracker(settings, sample_sink=focus_store.record_activity_sample)
    token = bootstrap_token or os.environ.get("NEKO_BOOTSTRAP_TOKEN")
    generated = token is None
    token = token or secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        focus_store.recover_after_restart()
        # Uvicorn has bound its socket before entering lifespan. This lets the
        # launcher publish run.json only after its authenticated server is live.
        if on_startup:
            on_startup()
        if settings.tracking_enabled:
            tracker.start()
        else:
            logger.info("Tracking disabled by configuration")
        if generated and settings.dev:
            logger.warning("Dev login: http://127.0.0.1:%s/auth/start?t=%s", settings.port, token)
        try:
            yield
        finally:
            tracker.stop()      # also saves the session in progress
            focus_store.shutdown()

    app = FastAPI(
        title="NekoAI", lifespan=lifespan,
        docs_url="/docs" if settings.dev else None, redoc_url=None,
        openapi_url="/openapi.json" if settings.dev else None,
    )
    app.state.settings = settings
    app.state.tracker = tracker
    app.state.focus_store = focus_store
    app.state.auth = AuthState(token, settings.allowed_origins)
    app.state.stabilizer = StateStabilizer()
    app.state.state_config = DEFAULT_CONFIG
    app.state.report_fn = report_fn or _default_report
    app.state.request_shutdown = None   # set by the launcher

    app.middleware("http")(security_headers)
    app.middleware("http")(host_guard)  # added last = runs first

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s", request.url.path)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    app.include_router(public)
    app.include_router(auth_router)
    app.include_router(protected)
    mount_frontend(app, settings.frontend_dist)   # must stay last
    return app


_cached_app: Optional[FastAPI] = None


def __getattr__(name: str):
    """Lazy module-level `app` so importing this module has no side effects."""
    global _cached_app
    if name == "app":
        if _cached_app is None:
            _cached_app = create_app()
        return _cached_app
    raise AttributeError(name)
