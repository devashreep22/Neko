"""A real loopback HTTP smoke test for health, login, and an authenticated API read."""
import http.cookiejar
import json
import socket
import threading
import time
import urllib.request

import uvicorn

from app.core.config import Settings
from app.main import create_app
from app.services.tracker import Snapshot


class IdleTracker:
    def start(self): pass
    def stop(self): pass
    def snapshot(self):
        return Snapshot("running", "Coding", "test", "high", "Code.exe", None,
                        5.0, 0.0, 0.0, False, {"Coding": 5.0})
    def pause(self): pass
    def resume(self): pass


def test_live_loopback_login_and_protected_activity_api(tmp_path):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    application = create_app(Settings(data_dir=tmp_path, port=port), tracker=IdleTracker(),
                             bootstrap_token="live-smoke-token")
    server = uvicorn.Server(uvicorn.Config(application, log_level="critical", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(origin + "/api/health", timeout=0.3) as response:
                    health = json.load(response)
                break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("loopback server failed to start")
        assert health["app"] == "nekoai" and health["status"] == "running"

        cookies = http.cookiejar.CookieJar()
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
        request = urllib.request.Request(origin + "/api/auth/login", data=json.dumps({
            "username": "Devashree", "password": "NekoDemo2026!",
        }).encode(), headers={"Content-Type": "application/json", "Origin": origin})
        with client.open(request, timeout=2) as response:
            assert response.status == 200
            assert json.load(response) == {"username": "Devashree"}
        with client.open(origin + "/api/auth/me", timeout=2) as response:
            assert json.load(response) == {"username": "Devashree"}
        with client.open(origin + "/api/activity/current", timeout=2) as response:
            activity = json.load(response)
            assert activity["category"] == "Coding" and activity["app"] == "Code.exe"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
