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
CHATGPT_WORKFLOW_NOTES_PLAYBOOK_ID = "chatgpt-workflow-design-notes"
TOKEN_LEAN_DELEGATION_PLAYBOOK_ID = "token-lean-delegation"


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
        "Two things worth knowing before you brief it, both sources of real confusion the first "
        "time this was run: (1) if this codebase also has a 'scaffold'/'blueprint' system "
        "(local Ollama models coding small pieces for testing/benchmarking, see scaffold/runner.py) "
        "-- that is a different subsystem entirely. ChatGPT building an app itself via "
        "synapse_write_file never touches it and shouldn't be confused with it when reviewing "
        "what actually got built. (2) ChatGPT Plus has its own native web browsing/search built "
        "into the product, separate from and complementary to Synapse's web-scraper MCP tool -- "
        "say explicitly in the brief that both are fair game, since it may otherwise assume only "
        "the MCP tool counts as 'real' research.",
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


def ensure_bootstrap_token_lean_delegation_playbook(conn: sqlite3.Connection) -> Playbook:
    """Seed the playbook for keeping an orchestrating AI's own token spend low on autonomous
    Synapse work, by delegating implementation rather than writing it all in its own turn.

    Depends on chatgpt-connector-setup already being healthy for the ChatGPT-UI path -- this
    playbook assumes a working connector, not how to get one."""

    steps = [
        "Purpose: on an indefinite/long-running autonomous Synapse session, keep the "
        "orchestrating AI's own token spend low by delegating the actual implementation "
        "instead of writing every diff itself. The orchestrator's job narrows to: scope the "
        "unit precisely, hand it to a cheap path, then review like a code reviewer -- read the "
        "diff, run the tests, don't regenerate what a delegate already got right.",
        "Two delegation paths, pick by shape of the task. (a) LOCAL: for a small, "
        "well-defined, single-module task, use coder_runtimes.write_module / the "
        "synapse_delegate_module MCP tool -- free, but the free tier's own measured pass rate "
        "is roughly one attempt in five (see ADR-0035/0036), so it suits an overnight batch "
        "more than an interactive wait. (b) CHATGPT UI: for anything bigger, more novel, or "
        "that benefits from ChatGPT's own reasoning about design tradeoffs (a redesign, a "
        "cross-cutting fix, something needing live verification) -- see "
        "chatgpt-autonomous-app-build for the full brief-writing and verification discipline; "
        "this playbook covers the delegation-setup and pacing pieces that discipline assumes.",
        "Before delegating to ChatGPT, confirm the connector is actually reachable: "
        "GET /api/v1/remote-access on the running daemon and read wan.public_url plus "
        "wan.verification.health_ok -- do NOT reuse a tunnel URL you saw in an earlier log "
        "line or an earlier turn. The Cloudflare quick-tunnel URL rotates on every daemon "
        "restart, and using a stale one is a real, confirmed failure mode: it produces a 424 "
        "from OpenAI's own connector-creation endpoint that looks identical to the unrelated, "
        "genuinely-transient 424 already documented in chatgpt-autonomous-app-build -- the "
        "first thing to check is not 'retry later', it's 'is this even the current URL'.",
        "ChatGPT's custom-connector UI has NO way to edit an existing connector's server URL "
        "in place (checked the '...' menu and the plugin detail page directly -- only "
        "rename/edit-description/disconnect/delete exist). After a daemon restart rotates the "
        "tunnel, the old connector cannot be repointed -- create a fresh one via Plugins -> "
        "the '+' next to the search box -> fill Name/Description/Server URL/Authentication: "
        "No Auth -> check the risk-acknowledgment box -> Create -> Connect -> set its "
        "Permissions to 'Allow all actions (ELEVATED RISK)'. A genuinely stable URL (a named "
        "Cloudflare tunnel instead of the ephemeral quick-tunnel) would remove this whole "
        "problem, but setting one up needs the operator's own Cloudflare account login -- that "
        "crosses into 'authenticate on the user's behalf', which stays off-limits regardless "
        "of how much autonomy has been granted. Flag it as a real improvement for the operator "
        "to do themselves rather than attempting it.",
        "Because reconnecting costs real setup effort, restart the daemon judiciously during a "
        "delegation-heavy stretch -- batch commits between restarts rather than restarting "
        "reflexively after each one, even when the operator has granted standing permission to "
        "restart freely.",
        "When typing into ChatGPT's Server URL field (or any long/exact-value field), do NOT "
        "use a plain synthesized keystroke-by-keystroke type action -- it has silently dropped "
        "the last character of a long URL before, producing a 424 that looks like a server "
        "problem but is actually a truncated URL. Use the browser tool's direct form-value "
        "setter, or set the DOM value via JS and dispatch input/change events, then read the "
        "value back and compare length/content before submitting.",
        "Before typing a NEW message into an existing project's 'new chat' composer, verify "
        "it is actually empty first (read its innerText, don't just trust that navigating to "
        "the project URL gives a blank box) -- stale draft text can persist across navigation "
        "and silently prepend itself to what you type next, sending a corrupted or unintended "
        "message. If it's not empty, select-all and delete before typing.",
        "For a long, structured brief (multiple paragraphs, numbered lists), don't type it "
        "with literal newline characters via a synthesized keystroke action -- a bare Enter "
        "mid-string can be interpreted as 'send' and fire the message early, before you're "
        "done composing it. Insert the full text at once via the browser tool's direct "
        "JS/execCommand insertion into the focused composer instead, which respects an "
        "already-attached connector mention pill and does not synthesize real keydown events.",
        "Multiple simultaneous ChatGPT conversations against the same connector already work "
        "with zero extra setup -- the MCP endpoint is stateless per request. Use this to run "
        "more than one delegated task in parallel (separate chats in the same project), rather "
        "than serializing everything through one conversation.",
        "Pace dispatches -- ChatGPT's own rate limiting (a rolling multi-hour message quota "
        "plus a separate burst/frequency limiter) has been hit more than once this way. Sending "
        "a small number of substantial, well-scoped briefs and letting each run for real "
        "minutes is sustainable; firing many small messages back-to-back is not.",
        "The orchestrator's remaining job after dispatch is real review, not trust: read the "
        "actual diff, run the actual test suite from a shell, check the actual git log -- same "
        "verification discipline as chatgpt-autonomous-app-build, applied to every delegated "
        "unit, not just full-app builds.",
    ]
    return upsert_playbook(
        conn,
        playbook_id=TOKEN_LEAN_DELEGATION_PLAYBOOK_ID,
        title="Delegate implementation to minimize the orchestrating AI's own token usage",
        summary=(
            "How to keep an autonomous Synapse session's own token spend low by handing "
            "implementation work to a cheaper path (local models via coder_runtimes, or "
            "ChatGPT UI via the Synapse connector) instead of writing every diff in the "
            "orchestrator's own turn -- including the real connector-reconnection gotchas "
            "(the tunnel URL rotates on restart, ChatGPT has no in-place URL edit) discovered "
            "the hard way in 2026-08."
        ),
        steps=steps,
    )


def ensure_bootstrap_chatgpt_workflow_notes_playbook(conn: sqlite3.Connection) -> Playbook:
    """Seed a living, append-only design-notes playbook -- unlike the other two, this is NOT an
    operating procedure. It's where ideas, gaps, and decisions about evolving the ChatGPT<->Synapse
    workflow itself get written down so they survive between sessions instead of living only in
    one conversation's memory.

    Content-only via upsert_playbook, same re-seed-safe pattern as the other two -- but since
    this one is meant to grow over time, treat future re-seeds here as append-only in spirit:
    extend the steps list, don't shrink it."""

    steps = [
        "Purpose: append-only running log of ideas, gaps, and decisions for evolving the "
        "ChatGPT<->Synapse workflow itself -- not an operating procedure (those stay in "
        "chatgpt-connector-setup and chatgpt-autonomous-app-build). Add a new dated bullet when "
        "a session surfaces confusion, a missing capability, or a workflow idea worth "
        "remembering; don't prune old entries without explicit review.",
        "2026-08-19: Audited MCP tool exposure -- confirmed the connector is genuinely "
        "full-access (27 tools including run_command, read_file/write_file anywhere, "
        "delegate_module, call_mcp_tool proxying to other registered servers like reflex) with "
        "zero per-client filtering; Claude Desktop, ChatGPT, and curl with the same token get an "
        "identical catalog. The only lever is the connector URL suffix (?mode=read) and the "
        "boot_config.mcp_writes_enabled flag, not client identity.",
        "2026-08-19: Gaps found -- subsystems that exist in the codebase but have no MCP tool at "
        "all: universal search (search.py/routes_search.py), Quality OS (quality_os.py), the "
        "MCP-server marketplace itself (routes_mcp_servers.py -- install/start/stop other MCP "
        "servers), and a dedicated read-back tool for project AI-memory (.synapse-ai-context.md "
        "is write-only via capture_note today). Squad management is add-only too -- no "
        "update/remove/reassign tools. Worth closing incrementally.",
        "2026-08-19: The 5-rung coder runtime ladder (claude -> codex -> copilot -> gemini -> "
        "local, in coder_runtimes.py) is fully implemented and shared between squads and the "
        "scaffold blueprint builder -- more complete than an earlier design doc assumed. ChatGPT "
        "is not a rung: unlike the others it has no CLI/headless entry point, so it can't be "
        "subprocess.run()'d the way claude/codex/copilot/gemini/local are.",
        "2026-08-19: Decision -- built chatgpt_browser_runtime.py, a real Playwright-driven "
        "runtime that types into and reads back from an actual chatgpt.com tab (persistent "
        "authenticated browser context), added as CoderRuntime.CHATGPT_WEB. Left OUT of "
        "DEFAULT_LADDER for now -- not as an account-risk hedge, but because it hadn't been "
        "live-tested end to end yet (needs a one-time human login into the Playwright profile "
        "first). A squad can already select it explicitly by name; promote it into the default "
        "ladder once proven live.",
        "2026-08-19: Confirmed running MULTIPLE simultaneous ChatGPT conversations against the "
        "same connector already works today with zero new code -- /mcp/{token} is fully "
        "stateless per-request, no session object, no single-session assumption anywhere. "
        "Several manually-opened tabs, each its own chat, can already act as parallel workers; "
        "the only thing missing for that to be orchestrated rather than manual is the same "
        "browser-runtime piece above, generalized to N tabs.",
    ]
    return upsert_playbook(
        conn,
        playbook_id=CHATGPT_WORKFLOW_NOTES_PLAYBOOK_ID,
        title="ChatGPT-Synapse workflow: design notes and open ideas",
        summary=(
            "Append-only running log of ideas, gaps, and decisions for making the "
            "ChatGPT-through-Synapse coding workflow itself more capable over time. Not a "
            "how-to -- operating steps stay in chatgpt-connector-setup and "
            "chatgpt-autonomous-app-build."
        ),
        steps=steps,
    )
