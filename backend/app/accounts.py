"""Small local account store for the single-user desktop demonstration.

Only salted PBKDF2 password hashes are persisted. The starter account is copied
to the user's data directory only when no account file exists; later launches
never replace an existing credential.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from pathlib import Path

DEMO_USERNAME = "Devashree"
_ITERATIONS = 310_000
_DEMO_SALT = "6fdc15409d2b2642dc823a87255340a4"
_DEMO_HASH = "cbaf520ac891c08d1bdb15a6fad515250e8403bd133cbb977aed4864cbfbb4a2"
_DUMMY_HASH = bytes.fromhex("4f" * 32)


def account_path(data_dir: Path) -> Path:
    return data_dir / "accounts.json"


def ensure_demo_account(data_dir: Path) -> None:
    """Create the demo account once; never reset an existing user's password."""
    data_dir.mkdir(parents=True, exist_ok=True)
    target = account_path(data_dir)
    if target.exists():
        # Parse existing data so corrupt stores fail closed instead of being replaced.
        _read_accounts(target)
        return
    payload = {"version": 1, "users": [{
        "username": DEMO_USERNAME, "salt": _DEMO_SALT,
        "password_hash": _DEMO_HASH, "iterations": _ITERATIONS,
    }]}
    fd, temporary = tempfile.mkstemp(prefix="accounts-", suffix=".tmp", dir=data_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        try:
            os.link(temporary, target)  # atomic create-if-absent; don't overwrite concurrent changes
        except FileExistsError:
            _read_accounts(target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _read_accounts(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        users = data["users"]
        if data.get("version") != 1 or not isinstance(users, list):
            raise ValueError
        return users
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"The local account store at {path} is invalid; it was left unchanged.") from exc


def authenticate(data_dir: Path, username: str, password: str) -> str | None:
    """Return canonical account name on success, with constant-time hash checks."""
    users = _read_accounts(account_path(data_dir))
    candidate = next((u for u in users if isinstance(u, dict) and
                      str(u.get("username", "")).casefold() == username.casefold()), None)
    salt = _DEMO_SALT if candidate is None else str(candidate.get("salt", ""))
    iterations = _ITERATIONS if candidate is None else int(candidate.get("iterations", _ITERATIONS))
    expected = _DUMMY_HASH if candidate is None else bytes.fromhex(str(candidate.get("password_hash", "")))
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    if hmac.compare_digest(actual, expected) and candidate is not None:
        return str(candidate["username"])
    return None
