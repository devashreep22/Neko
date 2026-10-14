"""Real server process: launch, login, API, duplicate launch, shutdown."""
import http.client
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def request(port, method, path, cookie=None, origin=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    if origin:
        headers["Origin"] = origin
    conn.request(method, path, headers=headers)
    resp = conn.getresponse()
    body = resp.read().decode()
    return resp.status, dict(resp.getheaders()), body


@pytest.fixture
def env(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>REAL-INDEX</html>")
    port = free_port()
    e = dict(os.environ, NEKO_PORT=str(port), NEKO_DATA_DIR=str(tmp_path / "data"),
             NEKO_NO_BROWSER="1", NEKO_TRACKING="0", NEKO_FRONTEND_DIST=str(dist),
             PYTHONUNBUFFERED="1")
    return e, port, tmp_path / "data"


def wait_healthy(port, proc, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise AssertionError("server exited early: " + proc.stdout.read())
        try:
            status, _, body = request(port, "GET", "/api/health")
            if status == 200:
                return
        except OSError:
            time.sleep(0.2)
    raise AssertionError("server did not become healthy")


def test_full_lifecycle(env):
    e, port, data = env
    proc = subprocess.Popen([sys.executable, "run_neko.py"], cwd=BACKEND, env=e,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        wait_healthy(port, proc)
        run = json.loads((data / "run.json").read_text())
        # Windows Store/venv launchers can spawn the actual interpreter as a
        # child, so its process ID need not match subprocess.Popen's wrapper.
        assert run["port"] == port and run["pid"] > 0

        assert request(port, "GET", "/api/neko/state")[0] == 401          # not logged in
        status, headers, _ = request(port, "GET", f"/auth/start?t={run['token']}")
        assert status == 303
        cookie = headers["set-cookie"].split(";")[0]

        status, _, body = request(port, "GET", "/api/neko/state", cookie=cookie)
        assert status == 200 and json.loads(body)["state"] in (
            "idle", "coding", "learning", "watching", "happy", "angry", "sleepy", "celebrating", "drink")
        assert request(port, "GET", "/api/activity/current", cookie=cookie)[0] == 200
        assert request(port, "GET", "/api/activity/today", cookie=cookie)[0] == 200
        history_status, _, history_body = request(port, "GET", "/api/analytics/history?days=3", cookie=cookie)
        assert history_status == 200 and len(json.loads(history_body)["days"]) == 3
        origin = f"http://127.0.0.1:{port}"
        paused_status, _, paused_body = request(port, "POST", "/api/tracking/pause", cookie=cookie, origin=origin)
        assert paused_status == 200 and json.loads(paused_body)["tracking"] == "paused"
        resumed_status, _, resumed_body = request(port, "POST", "/api/tracking/resume", cookie=cookie, origin=origin)
        assert resumed_status == 200 and json.loads(resumed_body)["tracking"] == "running"
        assert "REAL-INDEX" in request(port, "GET", "/")[2]               # frontend is served

        # A second launch must detect the running instance and exit cleanly.
        second = subprocess.run([sys.executable, "run_neko.py"], cwd=BACKEND, env=e,
                                capture_output=True, text=True, timeout=30)
        assert second.returncode == 0 and "already running" in second.stdout

        assert request(port, "POST", "/api/shutdown", cookie=cookie)[0] == 403   # missing Origin
        assert request(port, "POST", "/api/shutdown", cookie=cookie, origin=origin)[0] == 200
        assert proc.wait(timeout=15) == 0
        assert not (data / "run.json").exists()                           # cleaned up
    finally:
        if proc.poll() is None:
            proc.kill()


def test_port_conflict_gives_clear_message(env):
    e, port, _ = env
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", port))
        blocker.listen()
        res = subprocess.run([sys.executable, "run_neko.py"], cwd=BACKEND, env=e,
                             capture_output=True, text=True, timeout=30)
    assert res.returncode == 2 and "in use" in res.stdout
