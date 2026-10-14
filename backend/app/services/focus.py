"""Local, transactional focus-session storage and accounting."""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
ACTIVE_STATES = ("active", "paused")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.astimezone()
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def normalize_domains(values: list[str]) -> list[str]:
    """Normalize domain entries; '*.example.com' explicitly includes subdomains."""
    if not isinstance(values, list) or len(values) > 50:
        raise ValueError("Enter up to 50 approved domains")
    result: list[str] = []
    for item in values:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("Approved domains must be non-empty domain names or HTTP(S) URLs")
        raw = item.strip()
        wildcard = raw.startswith("*.")
        if wildcard:
            raw = raw[2:]
        if "*" in raw:
            raise ValueError("Use *.example.com only to explicitly include subdomains")
        candidate = raw if "://" in raw else f"https://{raw}"
        parsed = urlsplit(candidate)
        if parsed.scheme.lower() not in {"http", "https"} or parsed.username or parsed.password:
            raise ValueError(f"Invalid website: {item}")
        if parsed.port is not None or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise ValueError("Enter a domain or its origin only, without a port, path, query, or fragment")
        host = parsed.hostname
        if not host:
            raise ValueError(f"Invalid website: {item}")
        try:
            host = host.rstrip(".").encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError(f"Invalid domain: {item}") from exc
        labels = host.split(".")
        if len(labels) < 2 or any(not DOMAIN_LABEL.fullmatch(label) for label in labels):
            raise ValueError(f"Invalid domain: {item}")
        normalized = f"*.{host}" if wildcard else host
        if normalized not in result:
            result.append(normalized)
    return result


def domain_allowed(host: str, domains: list[str]) -> bool:
    candidate = host.rstrip(".").lower()
    try:
        candidate = candidate.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    return any(candidate == item or (item.startswith("*.") and candidate.endswith("." + item[2:]))
               for item in domains)


class FocusStore:
    def __init__(self, data_dir: Path, *, clock: Callable[[], float] = time.monotonic,
                 wall: Callable[[], datetime] = utc_now) -> None:
        self.path = Path(data_dir) / "focus.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._clock = clock
        self._wall = wall
        self._active_session_id: Optional[str] = None
        self._monotonic: dict[str, float] = {}
        self._current_distraction: dict[str, tuple[str, Optional[str]]] = {}
        self._category_pending: dict[str, dict[str, float]] = {}
        self._outside_pending: dict[str, float] = {}
        self._category_flush_at: dict[str, float] = {}
        self._initialize()

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10, isolation_level="DEFERRED")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript("""
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS focus_sessions (
                    id TEXT PRIMARY KEY,
                    task_title TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL CHECK(status IN ('active','paused','completed','cancelled','interrupted')),
                    created_at TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    planned_seconds INTEGER NOT NULL,
                    active_seconds REAL NOT NULL DEFAULT 0,
                    paused_seconds REAL NOT NULL DEFAULT 0,
                    last_resumed_at TEXT,
                    pause_started_at TEXT,
                    enforcement_mode TEXT NOT NULL CHECK(enforcement_mode IN ('monitor','controlled_browser')),
                    approved_domains TEXT NOT NULL,
                    distraction_count INTEGER NOT NULL DEFAULT 0,
                    outside_task_seconds REAL NOT NULL DEFAULT 0,
                    completion_reason TEXT,
                    current_domain TEXT,
                    browser_heartbeat_at TEXT,
                    browser_enforcement_active INTEGER NOT NULL DEFAULT 0
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_open_focus_session
                    ON focus_sessions(status) WHERE status IN ('active','paused');
                CREATE TABLE IF NOT EXISTS focus_distractions (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES focus_sessions(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    app_name TEXT,
                    domain TEXT,
                    duration_seconds REAL NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS focus_distractions_session
                    ON focus_distractions(session_id, started_at);
                CREATE TABLE IF NOT EXISTS focus_activity_categories (
                    session_id TEXT NOT NULL REFERENCES focus_sessions(id) ON DELETE CASCADE,
                    category TEXT NOT NULL, seconds REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY(session_id, category)
                );
            """)

    def recover_after_restart(self) -> None:
        """Finalize sessions left active by a crash as interrupted, never resume enforcement."""
        now = self._wall()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT * FROM focus_sessions WHERE status='active'").fetchall()
            for row in rows:
                db.execute("""UPDATE focus_sessions SET status='interrupted', ended_at=?,
                    last_resumed_at=NULL,
                    completion_reason='application_restarted', browser_enforcement_active=0
                    WHERE id=? AND status='active'""", (_stamp(now), row["id"]))
                self._close_distraction(db, row["id"], now)
            db.commit()
            self._active_session_id = None
            self._monotonic.clear()
            self._current_distraction.clear()

    def start(self, title: str, description: Optional[str], duration_minutes: int,
              domains: list[str], mode: str) -> dict:
        title = title.strip()
        if not title or len(title) > 160:
            raise ValueError("Task title must be 1 to 160 characters")
        if description is not None and len(description) > 2000:
            raise ValueError("Task description cannot exceed 2000 characters")
        if not isinstance(duration_minutes, int) or not 1 <= duration_minutes <= 240:
            raise ValueError("Duration must be from 1 to 240 minutes")
        if mode not in {"monitor", "controlled_browser"}:
            raise ValueError("Choose monitoring or Neko Focus Browser enforcement")
        approved = normalize_domains(domains)
        if mode == "controlled_browser" and not approved:
            raise ValueError("Add at least one approved domain to use Neko Focus Browser")
        now = self._wall()
        session_id = str(uuid.uuid4())
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM focus_sessions WHERE status IN ('active','paused')").fetchone():
                db.rollback()
                raise RuntimeError("A focus session is already active or paused")
            stamp = _stamp(now)
            db.execute("""INSERT INTO focus_sessions
                (id,task_title,description,status,created_at,started_at,planned_seconds,
                 last_resumed_at,enforcement_mode,approved_domains)
                 VALUES (?,?,?,'active',?,?,?,?,?,?)""",
                (session_id, title, description.strip() if description else None, stamp, stamp,
                 duration_minutes * 60, stamp, mode, json.dumps(approved)))
            db.commit()
        self._monotonic[session_id] = self._clock()
        self._active_session_id = session_id
        self._category_pending[session_id] = {}
        self._outside_pending[session_id] = 0.0
        self._category_flush_at[session_id] = self._clock()
        return self.get(session_id)

    def get_active(self) -> Optional[dict]:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM focus_sessions WHERE status IN ('active','paused') ORDER BY created_at DESC LIMIT 1").fetchone()
            if row and row["status"] == "active" and row["active_seconds"] + self._active_delta(row, self._wall()) >= row["planned_seconds"]:
                now = self._wall()
                active = float(row["active_seconds"]) + self._active_delta(row, now)
                db.execute("UPDATE focus_sessions SET status='completed',ended_at=?,active_seconds=?,last_resumed_at=NULL,completion_reason='duration_elapsed',browser_enforcement_active=0 WHERE id=?",
                           (_stamp(now), active, row["id"]))
                self._close_distraction(db, row["id"], now)
                self._flush_categories(db, row["id"])
                self._monotonic.pop(row["id"], None)
                self._active_session_id = None
                row = db.execute("SELECT * FROM focus_sessions WHERE id=?", (row["id"],)).fetchone()
            return self._serialize(db, row) if row else None

    def get(self, session_id: str) -> Optional[dict]:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM focus_sessions WHERE id=?", (session_id,)).fetchone()
            return self._serialize(db, row) if row else None

    def _active_delta(self, row, now: datetime) -> float:
        mono = self._monotonic.get(row["id"])
        if mono is not None:
            return max(0.0, self._clock() - mono)
        resumed = _parse(row["last_resumed_at"])
        return max(0.0, (now - resumed).total_seconds()) if resumed else 0.0

    def _serialize(self, db, row) -> dict:
        now = self._wall()
        active = float(row["active_seconds"])
        if row["status"] == "active":
            active += self._active_delta(row, now)
        paused = float(row["paused_seconds"])
        if row["status"] == "paused" and row["pause_started_at"]:
            paused += max(0.0, (now - _parse(row["pause_started_at"])).total_seconds())
        events = db.execute("SELECT * FROM focus_distractions WHERE session_id=? ORDER BY started_at", (row["id"],)).fetchall()
        category_seconds = {item["category"]: float(item["seconds"]) for item in db.execute(
            "SELECT category,seconds FROM focus_activity_categories WHERE session_id=?", (row["id"],)).fetchall()}
        for category, seconds in self._category_pending.get(row["id"], {}).items():
            category_seconds[category] = category_seconds.get(category, 0.0) + seconds
        outside_seconds = float(row["outside_task_seconds"]) + self._outside_pending.get(row["id"], 0.0)
        return {
            "id": row["id"], "task_title": row["task_title"], "description": row["description"],
            "status": row["status"], "created_at": row["created_at"], "started_at": row["started_at"],
            "ended_at": row["ended_at"], "planned_seconds": row["planned_seconds"],
            "active_seconds": round(active, 1), "paused_seconds": round(paused, 1),
            "remaining_seconds": max(0, int(row["planned_seconds"] - active)),
            "progress": min(1.0, active / row["planned_seconds"]),
            "enforcement_mode": row["enforcement_mode"],
            "approved_domains": json.loads(row["approved_domains"]),
            "distraction_count": row["distraction_count"],
            "outside_task_seconds": round(outside_seconds, 1),
            "completion_reason": row["completion_reason"],
            "current_domain": row["current_domain"],
            "enforcement_status": self._enforcement_status(row, now),
            "distractions": [self._event(e, now) for e in events],
            "activity_categories": [{"category": category, "seconds": round(seconds, 1)}
                                    for category, seconds in sorted(category_seconds.items(), key=lambda pair: -pair[1])],
        }

    @staticmethod
    def _enforcement_status(row, now):
        if row["status"] == "paused":
            return "paused"
        if row["status"] != "active":
            return "inactive"
        if row["enforcement_mode"] == "monitor":
            return "monitoring"
        heartbeat = _parse(row["browser_heartbeat_at"])
        if not heartbeat or (now - heartbeat).total_seconds() > 30:
            return "degraded"
        return "enforced" if row["browser_enforcement_active"] else "degraded"

    @staticmethod
    def _event(row, now):
        ended = _parse(row["ended_at"])
        duration = float(row["duration_seconds"])
        if ended is None:
            duration += max(0.0, (now - _parse(row["started_at"])).total_seconds())
        return {"id": row["id"], "kind": row["kind"], "started_at": row["started_at"],
                "ended_at": row["ended_at"], "app_name": row["app_name"], "domain": row["domain"],
                "duration_seconds": round(duration, 1)}

    def pause(self) -> dict:
        now = self._wall()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM focus_sessions WHERE status='active'").fetchone()
            if not row:
                db.rollback()
                raise RuntimeError("There is no active focus session to pause")
            delta = self._active_delta(row, now)
            db.execute("UPDATE focus_sessions SET status='paused',active_seconds=active_seconds+?,last_resumed_at=NULL,pause_started_at=?,browser_enforcement_active=0 WHERE id=?",
                       (delta, _stamp(now), row["id"]))
            self._close_distraction(db, row["id"], now)
            self._flush_categories(db, row["id"])
            db.commit()
        self._monotonic.pop(row["id"], None)
        self._active_session_id = None
        self._current_distraction.pop(row["id"], None)
        return self.get(row["id"])

    def resume(self) -> dict:
        now = self._wall()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM focus_sessions WHERE status='paused'").fetchone()
            if not row:
                db.rollback()
                raise RuntimeError("There is no paused focus session to resume")
            paused = max(0.0, (now - _parse(row["pause_started_at"])).total_seconds())
            db.execute("UPDATE focus_sessions SET status='active',paused_seconds=paused_seconds+?,pause_started_at=NULL,last_resumed_at=?,browser_enforcement_active=0 WHERE id=?",
                       (paused, _stamp(now), row["id"]))
            self._flush_categories(db, row["id"])
            db.commit()
        self._monotonic[row["id"]] = self._clock()
        self._active_session_id = row["id"]
        return self.get(row["id"])

    def end(self, reason: str = "user_ended") -> dict:
        now = self._wall()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM focus_sessions WHERE status IN ('active','paused')").fetchone()
            if not row:
                db.rollback()
                raise RuntimeError("There is no open focus session to end")
            active = float(row["active_seconds"])
            if row["status"] == "active":
                active += self._active_delta(row, now)
            else:
                paused_since = _parse(row["pause_started_at"])
                if paused_since:
                    db.execute("UPDATE focus_sessions SET paused_seconds=paused_seconds+? WHERE id=?",
                               (max(0.0, (now - paused_since).total_seconds()), row["id"]))
                    row = db.execute("SELECT * FROM focus_sessions WHERE id=?", (row["id"],)).fetchone()
            status = "completed" if active >= row["planned_seconds"] else "cancelled"
            db.execute("""UPDATE focus_sessions SET status=?,ended_at=?,active_seconds=?,
                last_resumed_at=NULL,pause_started_at=NULL,completion_reason=?,browser_enforcement_active=0
                WHERE id=?""", (status, _stamp(now), active, reason, row["id"]))
            self._close_distraction(db, row["id"], now)
            self._flush_categories(db, row["id"])
            db.commit()
        self._monotonic.pop(row["id"], None)
        self._active_session_id = None
        self._current_distraction.pop(row["id"], None)
        self._category_pending.pop(row["id"], None)
        self._outside_pending.pop(row["id"], None)
        self._category_flush_at.pop(row["id"], None)
        return self.get(row["id"])

    def list_sessions(self, limit: int = 50) -> list[dict]:
        limit = min(200, max(1, int(limit)))
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT * FROM focus_sessions ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
            return [self._serialize(db, row) for row in rows]

    def analytics_report(self, days: int = 7, today: Optional[date] = None) -> dict:
        """Aggregate persisted focus sessions by their local start date."""
        days = min(31, max(1, int(days)))
        today = today or self._wall().astimezone().date()
        start_day = today - timedelta(days=days - 1)
        prior_day = start_day - timedelta(days=days)
        with self._lock, self._connect() as db:
            stored = db.execute("SELECT * FROM focus_sessions ORDER BY started_at DESC").fetchall()
            sessions = [self._serialize(db, row) for row in stored]
        buckets: dict[date, dict] = {}
        for offset in range(days * 2):
            day = prior_day + timedelta(days=offset)
            buckets[day] = {"focus_seconds": 0.0, "planned_seconds": 0,
                            "completed": 0, "interrupted": 0, "distractions": 0,
                            "outside_task_seconds": 0.0}
        for item in sessions:
            try:
                started = _parse(item["started_at"]).astimezone().date()
            except (TypeError, ValueError, AttributeError):
                continue
            bucket = buckets.get(started)
            if bucket is None:
                continue
            bucket["focus_seconds"] += float(item["active_seconds"])
            bucket["distractions"] += int(item["distraction_count"])
            bucket["outside_task_seconds"] += float(item["outside_task_seconds"])
            if item["status"] == "completed":
                bucket["completed"] += 1
                bucket["planned_seconds"] += int(item["planned_seconds"])
            elif item["status"] == "interrupted":
                bucket["interrupted"] += 1
        rows = []
        for offset in range(days):
            day = start_day + timedelta(days=offset)
            row = buckets[day]
            rows.append({"date": day.isoformat(), "label": day.strftime("%a"),
                         **{key: round(value, 1) if key == "focus_seconds" else value
                            for key, value in row.items()}})
        current = [item for item in sessions if start_day <= _parse(item["started_at"]).astimezone().date() <= today]
        previous = [item for item in sessions if prior_day <= _parse(item["started_at"]).astimezone().date() < start_day]
        completed = [item for item in current if item["status"] == "completed"]
        planned = sum(int(item["planned_seconds"]) for item in completed)
        actual = sum(float(item["active_seconds"]) for item in completed)
        total_sessions = sum(item["status"] in ("completed", "interrupted", "cancelled") for item in current)
        previous_seconds = sum(float(item["active_seconds"]) for item in previous)
        current_seconds = sum(float(item["active_seconds"]) for item in current)
        return {
            "scope": "focus_sessions_by_local_start_date", "days": rows,
            "weekly": {
                "focus_seconds": round(current_seconds, 1),
                "previous_focus_seconds": round(previous_seconds, 1),
                "change_seconds": round(current_seconds - previous_seconds, 1),
                "completed_sessions": len(completed),
                "interrupted_sessions": sum(item["status"] == "interrupted" for item in current),
                "session_completion_rate": round(len(completed) / total_sessions, 3) if total_sessions else None,
                "average_completed_seconds": round(actual / len(completed), 1) if completed else 0,
                "planned_completed_seconds": planned, "actual_completed_seconds": round(actual, 1),
                "longest_completed_seconds": round(max((float(item["active_seconds"]) for item in completed), default=0), 1),
                "distractions": sum(int(item["distraction_count"]) for item in current),
                "outside_task_seconds": round(sum(float(item["outside_task_seconds"]) for item in current), 1),
            },
        }

    def browser_policy(self) -> dict:
        session = self.get_active()
        if not session:
            return {"active": False, "mode": "inactive", "domains": [], "session_id": None}
        return {"active": session["status"] == "active", "mode": session["enforcement_mode"],
                "domains": session["approved_domains"], "session_id": session["id"]}

    def browser_heartbeat(self, enforced: bool, domain: Optional[str]) -> dict:
        now = self._wall()
        with self._lock, self._connect() as db:
            row = db.execute("SELECT id,status,approved_domains,enforcement_mode FROM focus_sessions WHERE status IN ('active','paused')").fetchone()
            if not row:
                raise RuntimeError("No active focus session")
            domains = json.loads(row["approved_domains"])
            if domain and not domain_allowed(domain, domains):
                domain = None
            db.execute("UPDATE focus_sessions SET browser_heartbeat_at=?,browser_enforcement_active=?,current_domain=? WHERE id=?",
                       (_stamp(now), int(bool(enforced and row["status"] == "active" and row["enforcement_mode"] == "controlled_browser")), domain, row["id"]))
        return self.get(row["id"])

    def record_browser_distraction(self, domain: str, reason: str = "blocked_navigation") -> dict:
        now = self._wall()
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM focus_sessions WHERE status='active'").fetchone()
            if not row:
                raise RuntimeError("No active focus session")
            event_id = str(uuid.uuid4())
            db.execute("INSERT INTO focus_distractions(id,session_id,kind,started_at,ended_at,domain) VALUES(?,?,?,?,?,?)",
                       (event_id, row["id"], reason, _stamp(now), _stamp(now), domain[:253]))
            db.execute("UPDATE focus_sessions SET distraction_count=distraction_count+1 WHERE id=?", (row["id"],))
        return self.get(row["id"])

    def record_activity_sample(self, process_name: Optional[str], title: Optional[str],
                               category: Optional[str], at: datetime, delta: float, idle: bool) -> None:
        if not self._active_session_id:
            return
        with self._lock, self._connect() as db:
            row = db.execute("SELECT id,status FROM focus_sessions WHERE status='active'").fetchone()
            if not row:
                self._current_distraction.clear()
                return
            session_id = row["id"]
            if not idle and category and delta > 0:
                pending = self._category_pending.setdefault(session_id, {})
                pending[category] = pending.get(category, 0.0) + min(float(delta), 5.0)
            last_flush = self._category_flush_at.setdefault(session_id, self._clock())
            if self._clock() - last_flush >= 15:
                self._flush_categories(db, session_id)
            app = (process_name or "unknown").lower()
            internal_neko = app == "electron.exe" and bool(title and ("neko focus browser" in title.lower() or "nekoai dashboard" in title.lower()))
            outside = not idle and not internal_neko
            current_key = (app, category or "Unknown") if outside else None
            previous = self._current_distraction.get(session_id)
            if current_key != previous:
                self._close_distraction(db, session_id, at)
                self._flush_categories(db, session_id)
                self._current_distraction.pop(session_id, None)
                if current_key:
                    event_id = str(uuid.uuid4())
                    db.execute("INSERT INTO focus_distractions(id,session_id,kind,started_at,app_name) VALUES(?,?,?,?,?)",
                               (event_id, session_id, "application_switch", _stamp(at), process_name))
                    db.execute("UPDATE focus_sessions SET distraction_count=distraction_count+1 WHERE id=?", (session_id,))
                    self._current_distraction[session_id] = current_key
            if outside and delta > 0:
                self._outside_pending[session_id] = self._outside_pending.get(session_id, 0.0) + min(float(delta), 5.0)

    def _flush_categories(self, db, session_id: str) -> None:
        pending = self._category_pending.setdefault(session_id, {})
        if pending:
            db.executemany("""INSERT INTO focus_activity_categories(session_id,category,seconds) VALUES(?,?,?)
                ON CONFLICT(session_id,category) DO UPDATE SET seconds=seconds+excluded.seconds""",
                [(session_id, category, seconds) for category, seconds in pending.items()])
            pending.clear()
        outside = self._outside_pending.get(session_id, 0.0)
        if outside:
            db.execute("UPDATE focus_sessions SET outside_task_seconds=outside_task_seconds+? WHERE id=?", (outside, session_id))
            self._outside_pending[session_id] = 0.0
        self._category_flush_at[session_id] = self._clock()

    def shutdown(self) -> None:
        now = self._wall()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT * FROM focus_sessions WHERE status='active'").fetchall()
            for row in rows:
                active = float(row["active_seconds"]) + self._active_delta(row, now)
                db.execute("UPDATE focus_sessions SET status='interrupted',ended_at=?,active_seconds=?,last_resumed_at=NULL,completion_reason='application_shutdown',browser_enforcement_active=0 WHERE id=?",
                           (_stamp(now), active, row["id"]))
                self._close_distraction(db, row["id"], now)
                self._flush_categories(db, row["id"])
            for session_id in tuple(self._current_distraction):
                self._close_distraction(db, session_id, now)
            db.commit()
            self._monotonic.clear()
            self._active_session_id = None
            self._category_pending.clear()
            self._outside_pending.clear()
            self._category_flush_at.clear()
        self._current_distraction.clear()

    def _close_distraction(self, db, session_id: str, at: datetime) -> None:
        event = db.execute("SELECT id,started_at FROM focus_distractions WHERE session_id=? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
                           (session_id,)).fetchone()
        if not event:
            return
        started = _parse(event["started_at"])
        seconds = max(0.0, (at - started).total_seconds()) if started else 0.0
        db.execute("UPDATE focus_distractions SET ended_at=?,duration_seconds=? WHERE id=?",
                   (_stamp(at), seconds, event["id"]))
