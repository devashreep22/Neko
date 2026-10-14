"""Process-level launcher check: the real launcher writes a verifiable run.json."""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from app.launcher import read_run_info, verify_run_info


def test_launcher_writes_token_bound_run_file_and_starts_api(tmp_path):
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    backend = Path(__file__).resolve().parents[1]
    env_data_dir = tmp_path / "env-value-must-not-win"
    env = {**os.environ, "NEKO_DATA_DIR": str(env_data_dir), "NEKO_PORT": str(port),
           "NEKO_NO_BROWSER": "1", "NEKO_TRACKING": "0"}
    process = subprocess.Popen([sys.executable, "run_neko.py", "--data-dir", str(tmp_path)], cwd=backend, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        info = None
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline and process.poll() is None:
            info = read_run_info(tmp_path)
            if info and info.port == port and verify_run_info(info):
                break
            time.sleep(0.1)
        assert process.poll() is None, "launcher exited before the server became available"
        assert info is not None and info.port == port
        assert not (env_data_dir / "run.json").exists()
        assert verify_run_info(info)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
            assert json.load(response)["app"] == "nekoai"

        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(
            __import__("http.cookiejar").cookiejar.CookieJar()))
        with opener.open(f"http://127.0.0.1:{port}/auth/start?t={info.token}", timeout=2) as response:
            assert response.status == 200
        request = urllib.request.Request(f"http://127.0.0.1:{port}/api/shutdown", data=b"",
                                         headers={"Origin": f"http://127.0.0.1:{port}"}, method="POST")
        with opener.open(request, timeout=2) as response:
            assert json.load(response)["status"] == "shutting_down"
        process.wait(timeout=5)
        assert read_run_info(tmp_path) is None
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
