"""Native multi-AI coordination (ADR-0024).

One live, per-project picture of *who is working what, on which files* so
concurrent AI coders (Claude Code, Codex, squad workers, humans) stop
hand-parsing markdown and hand-noticing overlaps.

Two primitives live here:

* **Presence** -- ``agent_sessions``: a heartbeat registry of active agent
  sessions. Rows with no heartbeat within :data:`SESSION_STALE_SECONDS` are
  derived as *stale* and excluded from overlap warnings; a sweep
  (:func:`expire_stale_sessions`) marks them ``gone`` and releases their lanes.
* **File lanes** -- ``file_lanes``: *advisory* claims of the path globs an
  agent intends to edit. Claiming returns any overlapping claims by OTHER
  sessions so the caller can hold. Lanes are advisory only -- external CLI
  processes edit disk directly and the daemon cannot hard-lock them (ADR-0024).
  The one enforceable choke point is the pre-commit overlap check in
  ``scripts/coordination-preflight.ps1``.

CRUD is module-level functions taking a ``sqlite3.Connection``, matching the
convention in :mod:`project_records` / :mod:`agent_squads`. Routes call them
inside ``storage.transaction()``. A ``project_id`` of ``None`` addresses the
*repo-level* scope (``project_id IS NULL``) -- the scope two CLIs working the
Synapse repo itself share.
"""

from __future__ import annotations

import fnmatch
import json
import re
import secrets
import sqlite3
import subprocess
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from .errors import invalid, not_found
from .time_utils import from_iso, to_iso, utc_now

# A session with no heartbeat within this window is considered stale/gone.
SESSION_STALE_SECONDS = 90

_LANE_ADVISORY = (
    "File lanes are ADVISORY -- Synapse cannot block edits made by external CLI "
    "processes. Hold voluntarily when a conflict is returned; the enforceable "
    "check is the pre-commit overlap gate (scripts/coordination-preflight.ps1)."
)


# -- Enums --------------------------------------------------------------------


class AgentSessionStatus(str, Enum):
    ACTIVE = "active"
    IDLE = "idle"
    BLOCKED = "blocked"
    HOLDING = "holding"
    GONE = "gone"


class FileLaneStatus(str, Enum):
    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"


# -- Models -------------------------------------------------------------------


class AgentSession(BaseModel):
    id: str
    project_id: str | None = None
    runtime_id: str = ""
    agent_label: str = ""
    coder_thread_id: str | None = None
    task: str = ""
    status: AgentSessionStatus = AgentSessionStatus.ACTIVE
    last_intent: str = ""
    registered_at: datetime
    last_heartbeat_at: datetime
    ended_at: datetime | None = None
    # Derived, not stored: heartbeat older than SESSION_STALE_SECONDS.
    stale: bool = False


class AgentSessionRegister(BaseModel):
    project_id: str | None = None
    runtime_id: str = ""
    agent_label: str = ""
    coder_thread_id: str | None = None
    task: str = ""
    last_intent: str = ""


class AgentSessionHeartbeat(BaseModel):
    status: AgentSessionStatus | None = None
    task: str | None = None
    last_intent: str | None = None


class FileLane(BaseModel):
    id: str
    project_id: str | None = None
    session_id: str | None = None
    owner_label: str = ""
    runtime_id: str = ""
    path_globs: list[str] = Field(default_factory=list)
    task_ref: str = ""
    note: str = ""
    status: FileLaneStatus = FileLaneStatus.ACTIVE
    claimed_at: datetime
    heartbeat_at: datetime
    released_at: datetime | None = None


class LaneClaim(BaseModel):
    session_id: str
    path_globs: list[str] = Field(default_factory=list)
    task_ref: str = ""
    note: str = ""


class LaneConflict(BaseModel):
    lane_id: str
    owner_label: str
    runtime_id: str
    session_id: str | None = None
    task_ref: str = ""
    overlapping: list[str] = Field(default_factory=list)


class LaneClaimResult(BaseModel):
    granted: bool
    lane: FileLane | None = None
    conflicts: list[LaneConflict] = Field(default_factory=list)
    advisory: str = _LANE_ADVISORY


class CollisionHit(BaseModel):
    path: str
    lane_id: str
    owner_label: str
    session_id: str | None = None


class CoordinationSnapshot(BaseModel):
    project_id: str | None = None
    generated_at: datetime
    sessions: list[AgentSession] = Field(default_factory=list)
    lanes: list[FileLane] = Field(default_factory=list)
    stale_session_ids: list[str] = Field(default_factory=list)


# -- Helpers ------------------------------------------------------------------


def _new_id() -> str:
    return secrets.token_hex(6)


def _dumps(values: list[str]) -> str:
    return json.dumps(list(values))


def _loads_list(payload: str | None) -> list[str]:
    if not payload:
        return []
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in raw] if isinstance(raw, list) else []


def _norm(path: str) -> str:
    """Normalise a path/glob for comparison: forward slashes, no leading ``./``,
    no trailing slash."""
    cleaned = str(path).strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned.rstrip("/")


def _one_overlap(a: str, b: str) -> bool:
    """True if two path/glob tokens could refer to overlapping files."""
    a_n, b_n = _norm(a), _norm(b)
    if not a_n or not b_n:
        return False
    if a_n == b_n:
        return True
    # fnmatch each direction -- either side may be the glob.
    if fnmatch.fnmatch(a_n, b_n) or fnmatch.fnmatch(b_n, a_n):
        return True
    # directory-prefix containment ("renderer" vs "renderer/pages/X.tsx").
    if a_n.startswith(b_n + "/") or b_n.startswith(a_n + "/"):
        return True
    return False


def _globs_overlap(a_globs: list[str], b_tokens: list[str]) -> list[str]:
    """Return the b-side tokens that overlap any a-side token (deduped, ordered)."""
    hits: list[str] = []
    for b in b_tokens:
        if b not in hits and any(_one_overlap(a, b) for a in a_globs):
            hits.append(b)
    return hits


def _row_to_session(row: sqlite3.Row, *, now: datetime | None = None) -> AgentSession:
    last_hb = from_iso(row["last_heartbeat_at"])
    ref = now or utc_now()
    stale = (ref - last_hb) > timedelta(seconds=SESSION_STALE_SECONDS)
    return AgentSession(
        id=row["id"],
        project_id=row["project_id"],
        runtime_id=row["runtime_id"] or "",
        agent_label=row["agent_label"] or "",
        coder_thread_id=row["coder_thread_id"],
        task=row["task"] or "",
        status=AgentSessionStatus(row["status"]),
        last_intent=row["last_intent"] or "",
        registered_at=from_iso(row["registered_at"]),
        last_heartbeat_at=last_hb,
        ended_at=from_iso(row["ended_at"]) if row["ended_at"] else None,
        stale=stale,
    )


def _row_to_lane(row: sqlite3.Row) -> FileLane:
    return FileLane(
        id=row["id"],
        project_id=row["project_id"],
        session_id=row["session_id"],
        owner_label=row["owner_label"] or "",
        runtime_id=row["runtime_id"] or "",
        path_globs=_loads_list(row["path_globs_json"]),
        task_ref=row["task_ref"] or "",
        note=row["note"] or "",
        status=FileLaneStatus(row["status"]),
        claimed_at=from_iso(row["claimed_at"]),
        heartbeat_at=from_iso(row["heartbeat_at"]),
        released_at=from_iso(row["released_at"]) if row["released_at"] else None,
    )


# -- Presence CRUD ------------------------------------------------------------


def register_session(conn: sqlite3.Connection, payload: AgentSessionRegister) -> AgentSession:
    now = to_iso(utc_now())
    session_id = _new_id()
    conn.execute(
        "INSERT INTO agent_sessions "
        "(id, project_id, runtime_id, agent_label, coder_thread_id, task, status, "
        " last_intent, registered_at, last_heartbeat_at, ended_at, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, NULL, '{}')",
        (
            session_id,
            payload.project_id,
            payload.runtime_id.strip(),
            payload.agent_label.strip(),
            payload.coder_thread_id,
            payload.task.strip(),
            payload.last_intent.strip(),
            now,
            now,
        ),
    )
    return get_session(conn, session_id)


def get_session(conn: sqlite3.Connection, session_id: str) -> AgentSession:
    row = conn.execute("SELECT * FROM agent_sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        raise not_found("agent_session", session_id)
    return _row_to_session(row)


def heartbeat_session(
    conn: sqlite3.Connection, session_id: str, payload: AgentSessionHeartbeat
) -> AgentSession:
    existing = get_session(conn, session_id)
    now = to_iso(utc_now())
    status = payload.status.value if payload.status is not None else existing.status.value
    # A heartbeat always re-activates a gone/stale session unless it explicitly
    # sets another status.
    if payload.status is None and existing.status == AgentSessionStatus.GONE:
        status = AgentSessionStatus.ACTIVE.value
    task = payload.task if payload.task is not None else existing.task
    last_intent = payload.last_intent if payload.last_intent is not None else existing.last_intent
    conn.execute(
        "UPDATE agent_sessions SET status = ?, task = ?, last_intent = ?, "
        "last_heartbeat_at = ?, ended_at = NULL WHERE id = ?",
        (status, task, last_intent, now, session_id),
    )
    return get_session(conn, session_id)


def end_session(conn: sqlite3.Connection, session_id: str) -> None:
    get_session(conn, session_id)  # 404 if missing
    now = to_iso(utc_now())
    conn.execute(
        "UPDATE agent_sessions SET status = 'gone', ended_at = ? WHERE id = ?",
        (now, session_id),
    )
    conn.execute(
        "UPDATE file_lanes SET status = 'released', released_at = ? "
        "WHERE session_id = ? AND status = 'active'",
        (now, session_id),
    )


def list_sessions(
    conn: sqlite3.Connection, project_id: str | None = None, *, include_gone: bool = False
) -> list[AgentSession]:
    now = utc_now()
    if project_id is None:
        rows = conn.execute(
            "SELECT * FROM agent_sessions WHERE project_id IS NULL "
            "ORDER BY last_heartbeat_at DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agent_sessions WHERE project_id = ? "
            "ORDER BY last_heartbeat_at DESC",
            (project_id,),
        ).fetchall()
    sessions = [_row_to_session(row, now=now) for row in rows]
    if not include_gone:
        sessions = [s for s in sessions if s.status != AgentSessionStatus.GONE]
    return sessions


def expire_stale_sessions(conn: sqlite3.Connection) -> int:
    """Mark sessions with no recent heartbeat as ``gone`` and expire their active
    lanes. Returns the count expired. Safe to call on every heartbeat/snapshot."""
    now = utc_now()
    cutoff = to_iso(now - timedelta(seconds=SESSION_STALE_SECONDS))
    rows = conn.execute(
        "SELECT id FROM agent_sessions WHERE status != 'gone' AND last_heartbeat_at < ?",
        (cutoff,),
    ).fetchall()
    ids = [row["id"] for row in rows]
    now_iso = to_iso(now)
    for sid in ids:
        conn.execute(
            "UPDATE agent_sessions SET status = 'gone', ended_at = ? WHERE id = ?",
            (now_iso, sid),
        )
        conn.execute(
            "UPDATE file_lanes SET status = 'expired', released_at = ? "
            "WHERE session_id = ? AND status = 'active'",
            (now_iso, sid),
        )
    return len(ids)


# -- Lane CRUD + overlap ------------------------------------------------------


def list_active_lanes(conn: sqlite3.Connection, project_id: str | None = None) -> list[FileLane]:
    if project_id is None:
        rows = conn.execute(
            "SELECT * FROM file_lanes WHERE status = 'active' AND project_id IS NULL "
            "ORDER BY claimed_at DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM file_lanes WHERE status = 'active' AND project_id = ? "
            "ORDER BY claimed_at DESC",
            (project_id,),
        ).fetchall()
    return [_row_to_lane(row) for row in rows]


def get_lane(conn: sqlite3.Connection, lane_id: str) -> FileLane:
    row = conn.execute("SELECT * FROM file_lanes WHERE id = ?", (lane_id,)).fetchone()
    if row is None:
        raise not_found("file_lane", lane_id)
    return _row_to_lane(row)


def detect_overlap(
    conn: sqlite3.Connection,
    project_id: str | None,
    paths: list[str],
    *,
    exclude_session_id: str | None = None,
) -> list[LaneConflict]:
    """Which active lanes (owned by OTHER sessions) do these paths overlap?"""
    tokens = [str(p) for p in (paths or []) if str(p).strip()]
    conflicts: list[LaneConflict] = []
    for lane in list_active_lanes(conn, project_id):
        if exclude_session_id is not None and lane.session_id == exclude_session_id:
            continue
        hits = _globs_overlap(lane.path_globs, tokens)
        if hits:
            conflicts.append(
                LaneConflict(
                    lane_id=lane.id,
                    owner_label=lane.owner_label,
                    runtime_id=lane.runtime_id,
                    session_id=lane.session_id,
                    task_ref=lane.task_ref,
                    overlapping=hits,
                )
            )
    return conflicts


def claim_lane(
    conn: sqlite3.Connection, project_id: str | None, payload: LaneClaim
) -> LaneClaimResult:
    session = get_session(conn, payload.session_id)  # 404 if missing
    globs = [_norm(g) for g in payload.path_globs if str(g).strip()]
    if not globs:
        raise invalid("file_lane", "A lane claim needs at least one path or glob.")
    conflicts = detect_overlap(conn, project_id, globs, exclude_session_id=payload.session_id)
    now = to_iso(utc_now())
    lane_id = _new_id()
    conn.execute(
        "INSERT INTO file_lanes "
        "(id, project_id, session_id, owner_label, runtime_id, path_globs_json, "
        " task_ref, note, status, claimed_at, heartbeat_at, released_at, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, NULL, '{}')",
        (
            lane_id,
            project_id,
            session.id,
            session.agent_label or session.runtime_id,
            session.runtime_id,
            _dumps(globs),
            payload.task_ref.strip(),
            payload.note.strip(),
            now,
            now,
        ),
    )
    lane = get_lane(conn, lane_id)
    # granted is always True -- claims are advisory; conflicts are informational.
    return LaneClaimResult(granted=True, lane=lane, conflicts=conflicts)


def release_lane(conn: sqlite3.Connection, lane_id: str) -> FileLane:
    get_lane(conn, lane_id)  # 404 if missing
    now = to_iso(utc_now())
    conn.execute(
        "UPDATE file_lanes SET status = 'released', released_at = ? "
        "WHERE id = ? AND status = 'active'",
        (now, lane_id),
    )
    return get_lane(conn, lane_id)


# -- Collision detector (git working-tree backstop) ---------------------------


def _parse_git_status(output: str) -> list[str]:
    """Parse ``git status --short --porcelain`` output into dirty paths."""
    paths: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        # Porcelain v1: "XY <path>" (XY = 2 status chars). Renames: "old -> new".
        payload = line[3:] if len(line) > 3 else line.strip()
        payload = payload.strip().strip('"')
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1].strip().strip('"')
        norm = _norm(payload)
        if norm and norm not in paths:
            paths.append(norm)
    return paths


def git_dirty_paths(repo_root: Path) -> list[str]:
    try:
        # --untracked-files=all lists individual files (not collapsed
        # ``dir/`` entries) so lane matching is file-level.
        completed = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return []
    if completed.returncode != 0:
        return []
    return _parse_git_status(completed.stdout)


def detect_collisions(
    conn: sqlite3.Connection, project_id: str | None, repo_root: Path
) -> list[CollisionHit]:
    """Cross-reference dirty working-tree paths against active lanes.

    Advisory backstop for raw (non-Synapse-mediated) edits: reports dirty files
    that fall inside a claimed lane. Git does not record WHO made the edit, so
    this is a tripwire, not attribution/proof.
    """
    dirty = git_dirty_paths(repo_root)
    hits: list[CollisionHit] = []
    for lane in list_active_lanes(conn, project_id):
        for path in _globs_overlap(lane.path_globs, dirty):
            hits.append(
                CollisionHit(
                    path=path,
                    lane_id=lane.id,
                    owner_label=lane.owner_label,
                    session_id=lane.session_id,
                )
            )
    return hits


# -- Snapshot -----------------------------------------------------------------


def get_snapshot(conn: sqlite3.Connection, project_id: str | None = None) -> CoordinationSnapshot:
    sessions = list_sessions(conn, project_id, include_gone=False)
    lanes = list_active_lanes(conn, project_id)
    stale = [s.id for s in sessions if s.stale]
    return CoordinationSnapshot(
        project_id=project_id,
        generated_at=utc_now(),
        sessions=sessions,
        lanes=lanes,
        stale_session_ids=stale,
    )


# -- Disk-truth numbering (fixes stale hand-written advice) -------------------

_MIGRATION_RE = re.compile(r"^(\d+)_")
_ADR_RE = re.compile(r"^(\d+)-")


def _next_numbered(directory: Path, pattern: str, regex: re.Pattern[str]) -> int:
    highest = 0
    if directory.is_dir():
        for path in directory.glob(pattern):
            match = regex.match(path.name)
            if match:
                highest = max(highest, int(match.group(1)))
    return highest + 1


def next_migration_number(repo_root: Path) -> int:
    """Next free migration number, computed from disk incl. untracked files."""
    return _next_numbered(
        repo_root / "daemon" / "synapse_daemon" / "migrations", "*.sql", _MIGRATION_RE
    )


def next_adr_number(repo_root: Path) -> int:
    """Next free ADR number, computed from disk incl. untracked files."""
    return _next_numbered(repo_root / "docs" / "adr", "*.md", _ADR_RE)
