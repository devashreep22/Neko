"""Runtime settings, read from environment variables with safe defaults."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, Optional, Tuple

APP_NAME = "nekoai"
VERSION = "0.2.0"
DEFAULT_PORT = 8765


def default_data_dir() -> Path:
    override = os.environ.get("NEKO_DATA_DIR")
    if override:
        configured = Path(override).expanduser()
        # Relative overrides are anchored to the project root so Electron (whose
        # cwd is desktop/) and the Python launcher (whose cwd is backend/) agree.
        project_root = Path(__file__).resolve().parents[3]
        return (configured if configured.is_absolute() else project_root / configured).resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "NekoAI"
    return Path.home() / ".local" / "share" / "nekoai"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


def find_frontend_dist() -> Optional[Path]:
    """Locate the production React build (folder containing index.html)."""
    override = os.environ.get("NEKO_FRONTEND_DIST")
    if override:
        path = Path(override)
        return path if (path / "index.html").is_file() else None
    repo_root = Path(__file__).resolve().parents[3]  # backend/app/core/config.py -> repo root
    for candidate in (repo_root / "frontend" / "dist", repo_root / "desktop" / "dist"):
        if (candidate / "index.html").is_file():
            return candidate
    return None


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    frontend_dist: Optional[Path] = None
    host: str = "127.0.0.1"          # loopback only, deliberately not configurable
    port: int = DEFAULT_PORT
    poll_interval: float = 1.0
    idle_threshold: float = 300.0
    tracking_enabled: bool = True
    open_browser: bool = True
    dev: bool = False
    extra_origins: Tuple[str, ...] = ()

    @property
    def allowed_origins(self) -> FrozenSet[str]:
        own = {f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}"}
        return frozenset(own | set(self.extra_origins))


def load_settings() -> Settings:
    extra = tuple(o.strip() for o in os.environ.get("NEKO_EXTRA_ORIGINS", "").split(",") if o.strip())
    return Settings(
        data_dir=default_data_dir(),
        frontend_dist=find_frontend_dist(),
        port=_env_int("NEKO_PORT", DEFAULT_PORT),
        poll_interval=max(0.2, _env_float("NEKO_POLL_INTERVAL", 1.0)),
        idle_threshold=max(10.0, _env_float("NEKO_IDLE_SECONDS", 300.0)),
        tracking_enabled=_env_flag("NEKO_TRACKING", True),
        open_browser=not _env_flag("NEKO_NO_BROWSER", False),
        dev=_env_flag("NEKO_DEV", False),
        extra_origins=extra,
    )
