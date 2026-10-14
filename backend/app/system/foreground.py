"""Windows foreground-window and idle-time probe.

This is the only module that touches the OS. It imports pywin32 lazily so the
rest of the backend can be imported and tested on any platform.

Privacy: reads the window title, owning process name and time since the last
input event. It never reads keystrokes, screen contents or clipboard.
"""
from __future__ import annotations

import ctypes
import logging
import sys
from dataclasses import dataclass
from typing import Optional, Tuple

log = logging.getLogger("neko.probe")


@dataclass(frozen=True)
class WindowInfo:
    title: str
    process_name: Optional[str]


class NullProbe:
    """Used where foreground tracking is unsupported (non-Windows)."""

    def foreground(self) -> Optional[WindowInfo]:
        return None

    def idle_seconds(self) -> float:
        return 0.0


class WindowsProbe:
    def __init__(self) -> None:
        import psutil            # noqa: F401  (fail early if missing)
        import win32gui          # noqa: F401
        import win32process      # noqa: F401

    def foreground(self) -> Optional[WindowInfo]:
        import psutil
        import win32gui
        import win32process

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        title = win32gui.GetWindowText(hwnd)
        process_name: Optional[str] = None
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name = psutil.Process(pid).name()
        except (psutil.Error, OSError):
            pass  # e.g. elevated windows we may not inspect; title-only is fine
        return WindowInfo(title=title, process_name=process_name)

    def idle_seconds(self) -> float:
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        elapsed_ms = (ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF
        return elapsed_ms / 1000.0


def create_probe() -> Tuple[object, bool]:
    """Return (probe, available)."""
    if sys.platform == "win32":
        try:
            return WindowsProbe(), True
        except ImportError as exc:
            log.warning("pywin32/psutil not available (%s); tracking disabled", exc)
    return NullProbe(), False