"""Local security for the NekoAI server.

Threats handled: other websites in the user's browser calling localhost
(CSRF, DNS rebinding) and unauthenticated reads of activity data.

  * Host guard      - only 127.0.0.1 / localhost / ::1 Host headers are accepted.
  * Launch token    - random per launch, shared only with the launcher through a
                      file in the user's data folder. Exchanged once at
                      /auth/start for an HttpOnly, SameSite=Strict session cookie.
  * Origin check    - POST/PUT/PATCH/DELETE must come from our own origin.
  * No CORS         - the UI is served from the same origin.

Residual risk: any program running as the same Windows user can read the token
file and use the API. That is inherent to a local app without OS-level isolation.
"""
from __future__ import annotations

import hmac
import secrets
import threading
from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse, RedirectResponse, Response

COOKIE_NAME = "neko_session"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
MAX_SESSIONS = 20
COOKIE_MAX_AGE = 30 * 24 * 3600


def hostname(host_header: str) -> str:
    """Strip the port from a Host header, handling bracketed IPv6 like [::1]:8765."""
    host = host_header.strip().lower()
    if host.startswith("["):
        return host[1:].split("]", 1)[0]
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


class AuthState:
    def __init__(self, bootstrap_token: str, allowed_origins) -> None:
        self._token = bootstrap_token.encode()
        self.allowed_origins = frozenset(allowed_origins)
        self._sessions: "OrderedDict[str, str | None]" = OrderedDict()
        self._lock = threading.Lock()

    def exchange(self, candidate: str):
        """Trade the launch token for a new session id (or None)."""
        if not self.verify_token(candidate):
            return None
        return self._new_session(None)

    def verify_token(self, candidate: str) -> bool:
        return bool(candidate) and hmac.compare_digest(candidate.encode(), self._token)

    def login(self, username: str) -> str:
        return self._new_session(username)

    def _new_session(self, username: str | None) -> str:
        sid = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[sid] = username
            while len(self._sessions) > MAX_SESSIONS:
                self._sessions.popitem(last=False)
        return sid

    def valid(self, sid) -> bool:
        if not sid:
            return False
        with self._lock:
            return any(hmac.compare_digest(sid.encode(), s.encode()) for s in self._sessions)

    def principal(self, sid) -> str | None:
        if not sid:
            return None
        with self._lock:
            return next((name for key, name in self._sessions.items()
                         if hmac.compare_digest(sid.encode(), key.encode())), None)

    def revoke(self, sid) -> None:
        if not sid:
            return
        with self._lock:
            for key in tuple(self._sessions):
                if hmac.compare_digest(sid.encode(), key.encode()):
                    self._sessions.pop(key, None)
                    break


def require_auth(request: Request) -> None:
    """FastAPI dependency for every route that exposes or changes user data."""
    auth: AuthState = request.app.state.auth
    if not auth.valid(request.cookies.get(COOKIE_NAME)):
        raise HTTPException(401, "Not authenticated. Open NekoAI with Start_NekoAI.bat.")
    if request.method in UNSAFE_METHODS and request.headers.get("origin") not in auth.allowed_origins:
        raise HTTPException(403, "Origin not allowed")


def require_user_auth(request: Request) -> str:
    require_auth(request)
    username = request.app.state.auth.principal(request.cookies.get(COOKIE_NAME))
    if username is None:
        raise HTTPException(401, "Sign in with your NekoAI account to continue")
    return username


async def host_guard(request: Request, call_next):
    if hostname(request.headers.get("host", "")) not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "Invalid host"}, status_code=400)
    return await call_next(request)


async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")  # keep the token out of Referer
    if request.url.path.startswith(("/api", "/auth", "/report", "/current-activity")):
        response.headers["Cache-Control"] = "no-store"
    return response


auth_router = APIRouter()


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


@auth_router.post("/api/auth/login")
def account_login(body: LoginBody, request: Request):
    auth: AuthState = request.app.state.auth
    if request.headers.get("origin") not in auth.allowed_origins:
        raise HTTPException(403, "Origin not allowed")
    from app.accounts import authenticate
    username = authenticate(request.app.state.settings.data_dir, body.username, body.password)
    if username is None:
        raise HTTPException(401, "Invalid username or password")
    response = JSONResponse({"username": username})
    # Account login is a session cookie. The desktop bootstrap cookie below
    # keeps its existing lifetime and remains a distinct, local-app credential.
    response.set_cookie(COOKIE_NAME, auth.login(username), httponly=True, samesite="strict", path="/")
    return response


@auth_router.get("/auth/start", include_in_schema=False)
def auth_start(request: Request, t: str = ""):
    sid = request.app.state.auth.exchange(t)
    if sid is None:
        return JSONResponse({"detail": "Invalid or missing launch token"}, status_code=403)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(COOKIE_NAME, sid, httponly=True, samesite="strict",
                        max_age=COOKIE_MAX_AGE, path="/")
    return response


@auth_router.get("/auth/verify", include_in_schema=False)
def auth_verify(request: Request, t: str = ""):
    """Let Electron verify run.json against this backend without exposing a cookie."""
    if not request.app.state.auth.verify_token(t):
        return JSONResponse({"detail": "Invalid or missing launch token"}, status_code=403)
    return Response(status_code=204)
