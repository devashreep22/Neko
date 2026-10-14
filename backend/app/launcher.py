"""Starts NekoAI: single-instance check, server, browser.

Run with `python run_neko.py` (what Start_NekoAI.bat does).
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import secrets
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

from app.core.config import APP_NAME, VERSION, load_settings

RUN_FILE = "run.json"


@dataclass(frozen=True)
class RunInfo:
    pid: int
    port: int
    token: str
    version: str = VERSION


def auth_url(info: RunInfo) -> str:
    return f"http://127.0.0.1:{info.port}/auth/start?t={info.token}"


def write_run_info(data_dir: Path, info: RunInfo) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    tmp = data_dir / (RUN_FILE + ".tmp")
    tmp.write_text(json.dumps(asdict(info)), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)       # effective on POSIX; Windows uses the profile folder ACL
    except OSError:
        pass
    os.replace(tmp, data_dir / RUN_FILE)
    logging.getLogger("neko.launcher").info("Authenticated run file created: %s", data_dir / RUN_FILE)


def read_run_info(data_dir: Path) -> Optional[RunInfo]:
    try:
        data = json.loads((data_dir / RUN_FILE).read_text(encoding="utf-8"))
        return RunInfo(pid=int(data["pid"]), port=int(data["port"]), token=str(data["token"]),
                       version=str(data.get("version", "")))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def remove_run_info(data_dir: Path, only_pid: Optional[int] = None) -> None:
    if only_pid is not None:
        info = read_run_info(data_dir)
        if info is None or info.pid != only_pid:
            return
    try:
        (data_dir / RUN_FILE).unlink()
    except OSError:
        pass


_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # ignore system proxies


def fetch_health(port: int, timeout: float = 1.5) -> Optional[dict]:
    try:
        with _opener.open(f"http://127.0.0.1:{port}/api/health", timeout=timeout) as resp:
            return json.load(resp)
    except (OSError, ValueError):
        return None


def verify_run_info(info: RunInfo, timeout: float = 1.5) -> bool:
    """Prove the server owns this run file's one-launch bootstrap token."""
    try:
        with _opener.open(
            f"http://127.0.0.1:{info.port}/auth/verify?t={info.token}", timeout=timeout
        ) as resp:
            return resp.status == 204
    except (OSError, ValueError):
        return False


def find_running_instance(data_dir: Path, fetch: Callable[[int], Optional[dict]] = fetch_health,
                          verify: Callable[[RunInfo], bool] = verify_run_info,
                          pid_alive: Callable[[int], bool] | None = None) -> Optional[RunInfo]:
    """Return the running NekoAI instance, or None (removing a stale run file)."""
    info = read_run_info(data_dir)
    if info is None:
        return None
    health = fetch(info.port)
    if isinstance(health, dict) and health.get("app") == APP_NAME and verify(info):
        return info
    is_alive = pid_alive or process_is_running
    # A second launcher can observe a newly published run file before Uvicorn
    # finishes startup. Never delete the first launcher's file while that PID
    # is still alive; its owner will either become healthy or clean up on exit.
    if is_alive(info.pid):
        logging.getLogger("neko.launcher").info(
            "Run file belongs to live launcher PID %s; preserving it while startup completes", info.pid
        )
        return None
    remove_run_info(data_dir)       # crashed earlier, or the port now belongs to something else
    return None


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def process_is_running(pid: int) -> bool:
    """Check whether the process recorded in run.json is still alive."""
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (ProcessLookupError, OSError):
        return False


def configure_logging(data_dir: Path) -> None:
    handlers = [logging.StreamHandler()]
    try:
        log_dir = data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(
            log_dir / "neko.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.INFO, force=True, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _open_when_ready(url: str, port: int) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        health = fetch_health(port, timeout=0.5)
        if isinstance(health, dict) and health.get("app") == APP_NAME:
            webbrowser.open(url)
            return
        time.sleep(0.3)


def main() -> int:
    import uvicorn
    from app.main import create_app

    settings = load_settings()
    configure_logging(settings.data_dir)
    logging.getLogger("neko.launcher").info("Resolved backend data directory: %s", settings.data_dir.resolve())

    existing = find_running_instance(settings.data_dir)
    if existing:
        print(f"NekoAI is already running on port {existing.port}.")
        if settings.open_browser:
            webbrowser.open(auth_url(existing))
        return 0
    if not port_is_free(settings.host, settings.port):
        print(f"Port {settings.port} is in use by another program.\n"
              f"Close it, or set a different port first:  set NEKO_PORT=8766")
        return 2

    token = secrets.token_urlsafe(32)
    info = RunInfo(pid=os.getpid(), port=settings.port, token=token)
    app = create_app(settings, bootstrap_token=token,
                     on_startup=lambda: write_run_info(settings.data_dir, info))
    server = uvicorn.Server(uvicorn.Config(
        app, host=settings.host, port=settings.port, log_level="info", access_log=False))
    app.state.request_shutdown = lambda: setattr(server, "should_exit", True)

    if settings.open_browser:
        threading.Thread(target=_open_when_ready, args=(auth_url(info), info.port), daemon=True).start()

    print(f"NekoAI {VERSION} is running at http://127.0.0.1:{settings.port}")
    print("Tracking continues if you close the browser. Press Ctrl+C here to stop NekoAI.")
    try:
        server.run()
    finally:
        logging.getLogger("neko.launcher").info("Removing run file for launcher PID %s", os.getpid())
        remove_run_info(settings.data_dir, only_pid=os.getpid())
    return 0


if __name__ == "__main__":
    sys.exit(main())
