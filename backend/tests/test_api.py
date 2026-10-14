import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.tracker import Snapshot

ORIGIN = "http://127.0.0.1:8765"
TOKEN = "test-launch-token"


class FakeTracker:
    def __init__(self):
        self.started = self.stopped = 0
        self.paused = False
        self.category = "Coding"
        self.entertainment = 0.0

    def start(self): self.started += 1
    def stop(self): self.stopped += 1
    def pause(self): self.paused = True
    def resume(self): self.paused = False

    def snapshot(self):
        return Snapshot(
            tracking="paused" if self.paused else "running",
            category=None if self.paused else self.category, source="process:code.exe",
            confidence="high", app="Code.exe", window_title="secret-plans.docx - Word",
            session_seconds=12.34, entertainment_today_seconds=self.entertainment,
            continuous_work_seconds=0.0, user_idle=False, totals={})


@pytest.fixture
def dist(tmp_path):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<html>NEKO-INDEX</html>")
    (d / "assets" / "app.js").write_text("console.log('app')")
    (tmp_path / "secret.txt").write_text("TOP-SECRET")
    return d


def build(tmp_path, dist=None, tracker=None, **kw):
    settings = Settings(data_dir=tmp_path, frontend_dist=dist, tracking_enabled=True)
    tracker = tracker or FakeTracker()
    app = create_app(settings, tracker=tracker, bootstrap_token=TOKEN, **kw)
    return app, tracker


def test_launcher_startup_callback_runs_inside_server_lifespan(tmp_path):
    created = []
    app = create_app(Settings(data_dir=tmp_path, tracking_enabled=False), tracker=FakeTracker(),
                     bootstrap_token=TOKEN,
                     on_startup=lambda: created.append(tmp_path / "run.json"))
    with TestClient(app):
        assert created == [tmp_path / "run.json"]


@pytest.fixture
def anon(tmp_path, dist):
    app, tracker = build(tmp_path, dist)
    with TestClient(app, base_url=ORIGIN) as c:
        c.tracker, c.app_obj = tracker, app
        yield c


@pytest.fixture
def client(anon):
    r = anon.get(f"/auth/start?t={TOKEN}", follow_redirects=False)
    assert r.status_code == 303
    return anon


POST = {"Origin": ORIGIN}


def test_public_endpoints_need_no_login(anon):
    assert anon.get("/health").json() == {"status": "running"}
    body = anon.get("/api/health").json()
    assert body["status"] == "running" and body["app"] == "nekoai"


def test_account_login_valid_invalid_and_bootstrap_separation(anon, tmp_path):
    from app.accounts import account_path
    stored = account_path(tmp_path).read_text(encoding="utf-8")
    assert "NekoDemo2026!" not in stored
    assert anon.get("/api/auth/me").status_code == 401
    assert anon.post("/api/auth/login", json={"username": "Devashree", "password": "wrong"}, headers=POST).status_code == 401
    valid = anon.post("/api/auth/login", json={"username": "Devashree", "password": "NekoDemo2026!"}, headers=POST)
    assert valid.status_code == 200 and valid.json() == {"username": "Devashree"}
    cookie = valid.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert "max-age=" not in cookie
    assert anon.get("/api/auth/me").json() == {"username": "Devashree"}


def test_login_rejects_missing_or_untrusted_origin(anon):
    payload = {"username": "Devashree", "password": "NekoDemo2026!"}
    assert anon.post("/api/auth/login", json=payload).status_code == 403
    assert anon.post("/api/auth/login", json=payload, headers={"Origin": "https://evil.example"}).status_code == 403


def test_bootstrap_session_does_not_sign_in_to_user_account(anon):
    assert anon.get(f"/auth/start?t={TOKEN}", follow_redirects=False).status_code == 303
    assert anon.get("/api/neko/state").status_code == 200
    assert anon.get("/api/auth/me").status_code == 401


def test_bootstrap_verification_is_non_mutating(anon):
    assert anon.get(f"/auth/verify?t={TOKEN}").status_code == 204
    assert anon.get("/api/neko/state").status_code == 401
    assert anon.get("/auth/verify?t=wrong").status_code == 403


@pytest.mark.parametrize("path", [
    "/api/activity/current", "/api/neko/state", "/api/tracking/status",
    "/api/analytics/daily", "/api/analytics/history", "/report", "/current-activity"])
def test_data_routes_require_login(anon, path):
    assert anon.get(path).status_code == 401


@pytest.mark.parametrize("path", ["/api/tracking/pause", "/api/tracking/resume", "/api/shutdown"])
def test_control_routes_require_login(anon, path):
    assert anon.post(path, headers=POST).status_code == 401
    assert not anon.tracker.paused


def test_bad_launch_token_is_rejected(anon):
    assert anon.get("/auth/start?t=wrong", follow_redirects=False).status_code == 403
    assert anon.get("/auth/start", follow_redirects=False).status_code == 403
    assert anon.get("/auth/start?t=" + "é" * 5, follow_redirects=False).status_code == 403
    assert anon.get("/api/neko/state").status_code == 401


def test_login_sets_strict_httponly_cookie(anon):
    r = anon.get(f"/auth/start?t={TOKEN}", follow_redirects=False)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert r.headers["location"] == "/" and r.headers["referrer-policy"] == "no-referrer"


def test_forged_cookie_is_rejected(anon):
    anon.cookies.set("neko_session", "made-up-value")
    assert anon.get("/api/neko/state").status_code == 401


def test_pause_resume_need_our_origin(client):
    assert client.post("/api/tracking/pause").status_code == 403                       # no Origin
    assert client.post("/api/tracking/pause", headers={"Origin": "https://evil.example"}).status_code == 403
    assert not client.tracker.paused
    assert client.post("/api/tracking/pause", headers=POST).json() == {"tracking": "paused"}
    assert client.tracker.paused
    assert client.post("/api/tracking/resume", headers=POST).json() == {"tracking": "running"}


def test_current_activity_hides_window_title(client):
    body = client.get("/api/activity/current").json()
    assert body["category"] == "Coding" and body["app"] == "Code.exe"
    assert body["session_seconds"] == 12.3
    assert "secret-plans" not in str(body) and "window_title" not in body


def test_legacy_current_activity_keeps_old_shape(client):
    assert client.get("/current-activity").json() == {
        "window_title": "secret-plans.docx - Word", "category": "Coding"}


def test_neko_state_follows_activity_and_pause_is_immediate(client):
    body = client.get("/api/neko/state").json()
    assert body["state"] == "coding" and body["tracking"] == "running" and body["reason"]
    client.post("/api/tracking/pause", headers=POST)
    body = client.get("/api/neko/state").json()
    assert body["state"] == "idle" and body["tracking"] == "paused"


def test_entertainment_limit_makes_neko_angry(client):
    client.tracker.category = "Entertainment"
    client.tracker.entertainment = 95 * 60
    assert client.get("/api/neko/state").json()["state"] == "angry"


def test_bad_host_header_is_rejected(client):
    assert client.get("/health", headers={"host": "evil.example.com"}).status_code == 400
    assert client.get("/health", headers={"host": "127.0.0.1.evil.com:8765"}).status_code == 400
    for h in ("localhost:8765", "127.0.0.1", "[::1]:8765"):
        assert client.get("/health", headers={"host": h}).status_code == 200, h


def test_security_headers(client):
    r = client.get("/api/neko/state")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY" and r.headers["cache-control"] == "no-store"


def test_shutdown_calls_launcher_callback(client):
    calls = []
    client.app_obj.state.request_shutdown = lambda: calls.append(1)
    assert client.post("/api/shutdown", headers=POST).json() == {"status": "shutting_down"}
    assert calls == [1]


def test_shutdown_unavailable_without_launcher(client):
    assert client.post("/api/shutdown", headers=POST).status_code == 501


def test_lifespan_starts_and_stops_tracker(tmp_path, dist):
    app, tracker = build(tmp_path, dist)
    with TestClient(app, base_url=ORIGIN):
        assert tracker.started == 1 and tracker.stopped == 0
    assert tracker.stopped == 1


def test_tracking_can_be_disabled_by_config(tmp_path):
    tracker = FakeTracker()
    app = create_app(Settings(data_dir=tmp_path, tracking_enabled=False), tracker=tracker, bootstrap_token=TOKEN)
    with TestClient(app, base_url=ORIGIN):
        assert tracker.started == 0
    assert tracker.stopped == 1


def test_errors_do_not_leak_details(tmp_path):
    def boom(): raise RuntimeError("C:\\Users\\devashree\\secret")
    app, _ = build(tmp_path, report_fn=boom)
    with TestClient(app, base_url=ORIGIN, raise_server_exceptions=False) as c:
        c.get(f"/auth/start?t={TOKEN}")
        r = c.get("/report")
        assert r.status_code == 500 and "devashree" not in r.text


def test_report_uses_injected_function(tmp_path):
    app, _ = build(tmp_path, report_fn=lambda: {"category_totals": {"Coding": 60}})
    with TestClient(app, base_url=ORIGIN) as c:
        c.get(f"/auth/start?t={TOKEN}")
        assert c.get("/api/analytics/daily").json() == {"category_totals": {"Coding": 60}}


def test_saved_history_route_returns_date_rows_and_no_window_titles(client):
    response = client.get("/api/analytics/history?days=3")
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "saved_completed_sessions"
    assert len(body["days"]) == 3
    assert {"date", "label", "category_totals", "total_seconds", "productive_seconds"} <= body["days"][0].keys()
    assert "window_title" not in response.text


def test_focus_routes_are_user_authenticated_and_preserve_state(client, anon):
    assert anon.get("/api/focus/session").status_code == 401
    assert anon.post("/api/focus/sessions", headers=POST, json={"task_title": "Test", "duration_minutes": 25}).status_code == 401
    login = client.post("/api/auth/login", headers=POST, json={"username": "Devashree", "password": "NekoDemo2026!"})
    assert login.status_code == 200
    started = client.post("/api/focus/sessions", headers=POST, json={
        "task_title": "Test authenticated session", "duration_minutes": 25,
        "approved_domains": ["example.com"], "enforcement_mode": "controlled_browser",
    })
    assert started.status_code == 200
    paused = client.post("/api/focus/session/pause", headers=POST)
    assert paused.status_code == 200 and paused.json()["status"] == "paused"
    resumed = client.post("/api/focus/session/resume", headers=POST)
    assert resumed.status_code == 200 and resumed.json()["status"] == "active"
    ended = client.post("/api/focus/session/end", headers=POST)
    assert ended.status_code == 200 and ended.json()["status"] == "cancelled"


def test_focus_start_rejects_deceptive_allowlist_and_returns_empty_analytics(client):
    login = client.post("/api/auth/login", headers=POST, json={"username": "Devashree", "password": "NekoDemo2026!"})
    assert login.status_code == 200
    bad = client.post("/api/focus/sessions", headers=POST, json={
        "task_title": "Test", "duration_minutes": 25,
        "approved_domains": ["leetcode.com.attacker.example"], "enforcement_mode": "controlled_browser",
    })
    assert bad.status_code == 422
    report = client.get("/api/analytics/focus?days=7")
    assert report.status_code == 200
    assert len(report.json()["days"]) == 7
    assert report.json()["weekly"]["session_completion_rate"] is None


# ---- static frontend ----
def test_serves_index_assets_and_spa_routes(anon):
    assert "NEKO-INDEX" in anon.get("/").text
    assert anon.get("/assets/app.js").text == "console.log('app')"
    assert "NEKO-INDEX" in anon.get("/dashboard/history").text


def test_unknown_api_path_is_404_not_index(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and "NEKO-INDEX" not in r.text


def test_cannot_read_files_outside_the_build(anon):
    for path in ("/%2e%2e/secret.txt", "/..%2fsecret.txt", "/assets/..%2f..%2fsecret.txt", "/%00"):
        r = anon.get(path)
        assert "TOP-SECRET" not in r.text, path


def test_without_a_build_root_explains_itself(tmp_path):
    app, _ = build(tmp_path, dist=None)
    with TestClient(app, base_url=ORIGIN) as c:
        assert c.get("/").json()["frontend"] == "not built"


def test_unavailable_tracking_has_an_honest_reason(client):
    client.tracker.snapshot = lambda: Snapshot(
        tracking="unavailable", category=None, source=None, confidence=None, app=None,
        window_title=None, session_seconds=0.0, entertainment_today_seconds=0.0,
        continuous_work_seconds=0.0, user_idle=False, totals={})
    body = client.get("/api/neko/state").json()
    assert body["state"] == "idle" and "not available" in body["reason"]
