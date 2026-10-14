"""HTTP routes. Business logic lives in services; these only translate."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import APP_NAME, VERSION
from app.security import COOKIE_NAME, require_auth, require_user_auth
from app.utils.categories import DEFAULT_PRODUCTIVE
from app.services.neko_state import StateDecision, decide_state
from app.services.analytics import generate_history_report
from app.services.focus import normalize_domains

public = APIRouter()
protected = APIRouter(dependencies=[Depends(require_auth)])


class FocusStartBody(BaseModel):
    task_title: str = Field(min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    duration_minutes: int = Field(ge=1, le=240)
    approved_domains: list[str] = Field(default_factory=list, max_length=50)
    enforcement_mode: Literal["monitor", "controlled_browser"] = "monitor"


class BrowserHeartbeatBody(BaseModel):
    enforced: bool = False
    domain: Optional[str] = Field(default=None, max_length=253)


class BrowserDistractionBody(BaseModel):
    domain: str = Field(min_length=1, max_length=253)
    reason: Literal["blocked_navigation", "unapproved_redirect"] = "blocked_navigation"


# ---- public: reveal nothing about the user -------------------------------
@public.get("/health")
def legacy_health():
    return {"status": "running"}


@public.get("/api/health")
def health():
    return {"status": "running", "app": APP_NAME, "version": VERSION}


# ---- protected -------------------------------------------------------------
@protected.get("/api/activity/current")
def current_activity(request: Request):
    s = request.app.state.tracker.snapshot()
    # The window title is deliberately not included; it can contain private text.
    return {
        "tracking": s.tracking, "app": s.app, "category": s.category,
        "source": s.source, "confidence": s.confidence,
        "session_seconds": round(s.session_seconds, 1), "user_idle": s.user_idle,
    }


@protected.get("/api/auth/me")
def account_me(username: str = Depends(require_user_auth)):
    return {"username": username}


@protected.post("/api/auth/logout")
def account_logout(request: Request, username: str = Depends(require_user_auth)):
    request.app.state.auth.revoke(request.cookies.get(COOKIE_NAME))
    from fastapi.responses import JSONResponse
    response = JSONResponse({"status": "signed_out"})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@protected.get("/api/neko/state")
def neko_state(request: Request):
    app = request.app
    s = app.state.tracker.snapshot()
    decision = decide_state(
        s.category,
        entertainment_today_seconds=s.entertainment_today_seconds,
        continuous_work_seconds=s.continuous_work_seconds,
        tracking_paused=s.tracking != "running",
        user_idle=s.user_idle,
        config=app.state.state_config,
    )
    if s.tracking == "unavailable":
        decision = StateDecision("idle", "Activity tracking is not available on this system")
    # Pause/unavailable must show immediately; everything else is de-flickered.
    stable = app.state.stabilizer.update(decision, force=s.tracking != "running")
    return {"state": stable.state, "reason": stable.reason,
            "category": s.category, "tracking": s.tracking}


@protected.get("/api/activity/today")
def today(request: Request):
    """Live time per category since NekoAI started; completed sessions use the local JSON log."""
    s = request.app.state.tracker.snapshot()
    totals = {k: round(v, 1) for k, v in s.totals.items() if v > 0}
    productive = sum(v for k, v in totals.items() if k in DEFAULT_PRODUCTIVE)
    return {"scope": "since_launch_today", "totals": totals,
            "total_seconds": round(sum(totals.values()), 1), "productive_seconds": round(productive, 1)}


@protected.get("/api/tracking/status")
def tracking_status(request: Request):
    s = request.app.state.tracker.snapshot()
    return {"tracking": s.tracking, "user_idle": s.user_idle}


@protected.post("/api/tracking/pause")
def pause(request: Request):
    request.app.state.tracker.pause()
    return {"tracking": request.app.state.tracker.snapshot().tracking}


@protected.post("/api/tracking/resume")
def resume(request: Request):
    request.app.state.tracker.resume()
    return {"tracking": request.app.state.tracker.snapshot().tracking}


@protected.post("/api/shutdown")
def shutdown(request: Request, background: BackgroundTasks):
    callback = request.app.state.request_shutdown
    if callback is None:
        raise HTTPException(501, "Shutdown is only available when started with Start_NekoAI.bat")
    background.add_task(callback)  # runs after the response is sent
    return {"status": "shutting_down"}


@protected.get("/api/analytics/daily")
@protected.get("/report")           # legacy path
def daily_report(request: Request):
    return request.app.state.report_fn()


@protected.get("/api/analytics/history")
def activity_history(days: int = 7):
    """Completed saved sessions by day, using the existing local JSON log."""
    return generate_history_report(days=days)


@protected.get("/api/analytics/focus")
def focus_analytics(request: Request, days: int = 7, _: str = Depends(require_user_auth)):
    return request.app.state.focus_store.analytics_report(days=days)


@protected.get("/api/focus/session")
def active_focus_session(request: Request, _: str = Depends(require_user_auth)):
    return {"session": request.app.state.focus_store.get_active()}


@protected.get("/api/focus/sessions")
def focus_sessions(request: Request, limit: int = 50, _: str = Depends(require_user_auth)):
    return {"sessions": request.app.state.focus_store.list_sessions(limit)}


@protected.get("/api/focus/sessions/{session_id}")
def focus_session_detail(session_id: str, request: Request, _: str = Depends(require_user_auth)):
    session = request.app.state.focus_store.get(session_id)
    if not session:
        raise HTTPException(404, "Focus session not found")
    return session


@protected.post("/api/focus/sessions")
def start_focus_session(body: FocusStartBody, request: Request, _: str = Depends(require_user_auth)):
    try:
        return request.app.state.focus_store.start(
            body.task_title, body.description, body.duration_minutes,
            normalize_domains(body.approved_domains), body.enforcement_mode,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@protected.post("/api/focus/session/pause")
def pause_focus_session(request: Request, _: str = Depends(require_user_auth)):
    try:
        return request.app.state.focus_store.pause()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@protected.post("/api/focus/session/resume")
def resume_focus_session(request: Request, _: str = Depends(require_user_auth)):
    try:
        return request.app.state.focus_store.resume()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@protected.post("/api/focus/session/end")
def end_focus_session(request: Request, _: str = Depends(require_user_auth)):
    try:
        return request.app.state.focus_store.end()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@protected.get("/api/focus/browser-policy")
def focus_browser_policy(request: Request, _: str = Depends(require_user_auth)):
    return request.app.state.focus_store.browser_policy()


@protected.post("/api/focus/browser-heartbeat")
def focus_browser_heartbeat(body: BrowserHeartbeatBody, request: Request,
                            _: str = Depends(require_user_auth)):
    try:
        return request.app.state.focus_store.browser_heartbeat(body.enforced, body.domain)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@protected.post("/api/focus/browser-distraction")
def focus_browser_distraction(body: BrowserDistractionBody, request: Request,
                              _: str = Depends(require_user_auth)):
    try:
        normalize_domains([body.domain])
        return request.app.state.focus_store.record_browser_distraction(body.domain, body.reason)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@protected.get("/current-activity")  # legacy path, same shape as before
def legacy_current_activity(request: Request):
    s = request.app.state.tracker.snapshot()
    return {"window_title": s.window_title or "Unknown", "category": s.category or "Unknown"}
