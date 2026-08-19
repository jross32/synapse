"""AI-facing playbooks: procedures for driving something outside this codebase.

The first one is "how do I get ChatGPT to actually use the Synapse MCP connector in its own
chat tab" -- discovered once, by hand, through real browser automation (Settings -> Plugins ->
find the connector -> its "..." menu -> View plugin detail -> Try in chat -> switch to the Chat
tab, not Work). Nothing forces the next AI session to rediscover that.

Steps are semantic ("click the ... menu next to the connector"), never pixel coordinates --
coordinates rot the instant a layout shifts, and a playbook that stops matching reality should
say so rather than fail silently. record_verification() is that self-report: an executing AI
calls it the moment a step doesn't match what's on screen, so the next AI sees needs_attention
before it burns time on a step that no longer exists.
"""

from __future__ import annotations

import json
import sqlite3
from enum import Enum

from pydantic import BaseModel, Field

from .errors import invalid, not_found
from .time_utils import to_iso, utc_now

CHATGPT_CONNECTOR_PLAYBOOK_ID = "chatgpt-connector-setup"
CHATGPT_AUTONOMOUS_BUILD_PLAYBOOK_ID = "chatgpt-autonomous-app-build"


class PlaybookStatus(str, Enum):
    HEALTHY = "healthy"
    NEEDS_ATTENTION = "needs_attention"
    BROKEN = "broken"


class Playbook(BaseModel):
    id: str
    title: str
    summary: str = ""
    steps: list[str] = Field(default_factory=list)
    status: PlaybookStatus = PlaybookStatus.HEALTHY
    status_note: str | None = None
    last_verified_at: str | None = None
    verified_by: str | None = None
    created_at: str
    updated_at: str


class PlaybookSummary(BaseModel):
    """The compact form for list views -- steps are the expensive part of the payload,
    so a listing that's just "what playbooks exist and are they healthy" skips them."""

    id: str
    title: str
    summary: str = ""
    status: PlaybookStatus = PlaybookStatus.HEALTHY
    status_note: str | None = None
    step_count: int = 0


def _row_to_playbook(row: sqlite3.Row) -> Playbook:
    try:
        steps = json.loads(row["steps_json"])
    except Exception:  # noqa: BLE001
        steps = []
    return Playbook(
        id=row["id"],
        title=row["title"],
        summary=row["summary"] or "",
        steps=steps,
        status=PlaybookStatus(row["status"]),
        status_note=row["status_note"],
        last_verified_at=row["last_verified_at"],
        verified_by=row["verified_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_playbooks(conn: sqlite3.Connection) -> list[PlaybookSummary]:
    rows = conn.execute("SELECT * FROM playbooks ORDER BY title").fetchall()
    out: list[PlaybookSummary] = []
    for row in rows:
        try:
            steps = json.loads(row["steps_json"])
        except Exception:  # noqa: BLE001
            steps = []
        out.append(
            PlaybookSummary(
                id=row["id"],
                title=row["title"],
                summary=row["summary"] or "",
                status=PlaybookStatus(row["status"]),
                status_note=row["status_note"],
                step_count=len(steps),
            )
        )
    return out


def get_playbook(conn: sqlite3.Connection, playbook_id: str) -> Playbook:
    row = conn.execute("SELECT * FROM playbooks WHERE id = ?", (playbook_id,)).fetchone()
    if row is None:
        raise not_found("playbook", playbook_id)
    return _row_to_playbook(row)


def upsert_playbook(
    conn: sqlite3.Connection,
    *,
    playbook_id: str,
    title: str,
    summary: str,
    steps: list[str],
) -> Playbook:
    """Seed or refresh a playbook's content (title/summary/steps). Never touches
    status -- that's record_verification()'s job, and a re-seed on daemon startup
    should not silently erase "an AI already reported this is broken"."""

    if not playbook_id or not title:
        raise invalid("playbook", "A playbook needs at least an id and a title.")
    now = to_iso(utc_now())
    existing = conn.execute("SELECT id FROM playbooks WHERE id = ?", (playbook_id,)).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO playbooks (id, title, summary, steps_json, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (playbook_id, title, summary, json.dumps(steps), PlaybookStatus.HEALTHY.value, now, now),
        )
    else:
        conn.execute(
            "UPDATE playbooks SET title = ?, summary = ?, steps_json = ?, updated_at = ? WHERE id = ?",
            (title, summary, json.dumps(steps), now, playbook_id),
        )
    return get_playbook(conn, playbook_id)


def record_verification(
    conn: sqlite3.Connection,
    playbook_id: str,
    *,
    status: PlaybookStatus,
    note: str | None = None,
    verified_by: str | None = None,
) -> Playbook:
    """An executing AI calls this after following (or trying to follow) a playbook.

    healthy -> "I followed these steps and it worked." needs_attention -> "a step didn't match
    what's on screen, here's what I saw instead." broken -> "this approach no longer works at
    all." The note is what the NEXT AI reads before deciding whether to trust the steps."""

    get_playbook(conn, playbook_id)  # 404s if unknown
    now = to_iso(utc_now())
    conn.execute(
        "UPDATE playbooks SET status = ?, status_note = ?, last_verified_at = ?, "
        "verified_by = ?, updated_at = ? WHERE id = ?",
        (status.value, note, now, verified_by, now, playbook_id),
    )
    return get_playbook(conn, playbook_id)


def ensure_bootstrap_chatgpt_connector_playbook(conn: sqlite3.Connection) -> Playbook:
    """Seed the ChatGPT-connector-setup playbook, learned by hand in this session.

    Idempotent and content-only (see upsert_playbook) -- safe to call on every daemon
    startup without clobbering a status an AI already reported."""

    steps = [
        "Open chatgpt.com in a real, signed-in browser tab (Chrome MCP tools or equivalent "
        "UI automation -- ChatGPT connectors are per-account, not something you can configure "
        "over an API).",
        "Click the account name/avatar at the bottom of the left sidebar, then click "
        "'Settings' in the menu that opens.",
        "In Settings, click 'Plugins' in the left-hand settings list (this is where custom "
        "MCP connectors live in the current ChatGPT UI -- NOT a section literally labeled "
        "'Connectors'; that label has moved across OpenAI UI revisions, so if 'Plugins' is "
        "missing, search the settings search box for the connector's name instead).",
        "Scroll the plugin list to find the target connector by name (e.g. the Synapse "
        "connector). If it isn't listed yet, it needs to be added first via whatever "
        "'add custom connector' entry point Settings -> Plugins currently exposes, pasting "
        "in the connector's MCP URL.",
        "Click the '...' (more options) menu next to the connector's name, then click "
        "'View plugin detail'. This opens a dedicated full-page view for that connector -- "
        "not the settings modal.",
        "On that page, click the 'Try in chat' button. This is the mechanism that actually "
        "attaches the connector to a new chat's message composer (as a visible chip) -- "
        "typing the connector's name into a regular chat does NOT reliably do this.",
        "'Try in chat' opens ChatGPT's separate 'Work' surface by default, which has its own, "
        "often-exhausted weekly usage limit distinct from normal chat. Click the 'Chat' tab "
        "at the top of the page (next to 'Work') to switch to a normal chat -- the connector "
        "chip carries over automatically.",
        "Send a prompt that explicitly asks the model to use the connector's tools and to "
        "report back the exact tool call and exact result (e.g. 'use the <connector> tool to "
        "list my current projects'). A vague prompt lets the model describe the connector "
        "instead of actually calling it.",
        "Verify by expanding the 'Called tool' disclosure under the assistant's reply -- it "
        "shows the literal request/response JSON. Independently re-check anything "
        "file-related on disk yourself; don't trust the transcript alone.",
    ]
    return upsert_playbook(
        conn,
        playbook_id=CHATGPT_CONNECTOR_PLAYBOOK_ID,
        title="Get ChatGPT to actually use a Synapse MCP connector in its own chat",
        summary=(
            "ChatGPT can list a connector's tools from Settings without ever being able to "
            "call them in a normal chat -- ChatGPT only actually calls tools when the connector "
            "was attached via a plugin detail page's 'Try in chat' button, and 'Try in chat' "
            "lands in the separate 'Work' surface, not the 'Chat' tab the user actually wants."
        ),
        steps=steps,
    )


def ensure_bootstrap_chatgpt_autonomous_build_playbook(conn: sqlite3.Connection) -> Playbook:
    """Seed the playbook for having ChatGPT build a real app entirely on its own through the
    connector -- proven once on FlipLedger (a clothes-resale tracker): real scraped pricing
    data, a real Reflex-driven UI check that caught and fixed its own bug, real passing tests,
    a real git history, all with zero delegation to another coding runtime.

    Depends on chatgpt-connector-setup already being healthy -- this playbook assumes a
    working, full-access, Chat-tab connector session, not how to get one."""

    steps = [
        "Prerequisite: follow the chatgpt-connector-setup playbook first if it isn't already "
        "healthy. This playbook assumes a working connector attached in the normal Chat tab "
        "with writes enabled.",
        "Open ONE new, dedicated chat for this build (via the connector's plugin page -> "
        "'Try in chat' -> switch to Chat tab) -- don't reuse an unrelated existing chat. "
        "ChatGPT titles the chat from the first message, so a focused brief gives you a "
        "recognizable conversation to return to across check-ins.",
        "Write a single, explicit brief in one message covering: (1) the exact target "
        "workspace path -- give it one, don't let it improvise a location; (2) an explicit, "
        "unambiguous no-delegation rule naming the forbidden tools by name (synapse_delegate_module, "
        "and synapse_run_command specifically to invoke claude/codex/copilot CLIs) and stating "
        "what non-coding shell use IS fine (npm install, git, running tests) -- this is the "
        "entire point of the exercise and the one rule most worth over-specifying; "
        "(3) concrete, falsifiable feature requirements, not vague goals -- things you can "
        "personally check are true or false afterward; (4) explicit permission and encouragement "
        "to use OTHER registered MCP servers where genuinely useful (e.g. the web-scraper for "
        "real external data, Reflex for a real UI check) rather than describing those steps "
        "without doing them; (5) explicit permission to do its own web research where relevant; "
        "(6) ask it to register the finished result as a Synapse project via synapse_http "
        "POST to /api/v1/projects -- but see the known-gap note below, this commonly fails "
        "and that is fine.",
        "Send it, then pace check-ins with a scheduling tool every several minutes -- do not "
        "poll every few seconds. A real build with real tool calls (web scraping, file writes, "
        "test runs) genuinely takes many minutes; the first FlipLedger pass took ~16 minutes, "
        "a follow-up correction pass took ~32.",
        "When it reports done, do NOT trust the summary prose by itself. Independently verify: "
        "the target folder and its files actually exist and aren't a stub (read a real source "
        "file, not just a listing); re-run any test suite it claims passed, yourself, from a "
        "shell; if it claims a git history, run git log yourself; if it claims external data "
        "(scraped prices, research findings), open the actual file/response and read it.",
        "If specific requirements you asked for are unconfirmed or silently absent from its "
        "own summary, ask directly and by name: 'did you actually call X, or did you skip it -- "
        "if skipped, do it now.' Proven case: it had quietly skipped the web-scraper pricing "
        "step on the first pass; asking directly by tool name caught it, and it genuinely went "
        "back, called the tool for real, and said so plainly rather than backfilling a claim.",
        "Known gap, not a bug to chase: as of this writing the connector has no create-project "
        "MCP tool, so 'register it as a Synapse project' will likely fail on ChatGPT's end no "
        "matter how it tries (direct HTTP calls to the local API from a remote chat can also "
        "time out). Finish that one step yourself afterward with a direct POST to "
        "/api/v1/projects -- it is an administrative step, not part of 'ChatGPT built it "
        "itself', so doing it yourself does not violate the no-delegation rule.",
        "Known gotcha: the ChatGPT browser tab can freeze mid-long-generation (screenshot "
        "timeouts, 'extension not connected' errors) during a long tool-heavy turn. Don't fight "
        "the frozen tab -- open a fresh tab to the exact same chat URL, which reliably recovers "
        "and shows the live, current state; close the frozen one after.",
        "Known gotcha: creating a brand-new custom connector can return 424 from OpenAI's own "
        "connector-creation endpoint even when the MCP server itself is completely healthy "
        "(verified externally: the handshake succeeds from outside the operator's network). "
        "This is not diagnosable or fixable from the Synapse side -- it just needs a retry "
        "after some time, not a code change.",
    ]
    return upsert_playbook(
        conn,
        playbook_id=CHATGPT_AUTONOMOUS_BUILD_PLAYBOOK_ID,
        title="Have ChatGPT build a real app on its own through the Synapse connector",
        summary=(
            "The brief structure, verification discipline, and pacing that got ChatGPT to "
            "build a complete, independently-verified app (FlipLedger, a clothes-resale "
            "tracker) end to end through the connector with zero delegation to another coding "
            "runtime -- real scraped data, a real self-caught bug fix via Reflex, real passing "
            "tests, real git history. The two load-bearing moves: an explicit brief that names "
            "the forbidden delegation tools outright, and never trusting a 'done' summary "
            "without independently re-checking it yourself."
        ),
        steps=steps,
    )
