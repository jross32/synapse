# ADR-0014: Local LLM assistant (Ollama) + chat + model marketplace

- Status: Accepted (Phase L shipping; Phase M = model marketplace, follows)
- Date: 2026-06-23
- Deciders: Justin (owner), Claude

## Context

The owner wants a built-in **local LLM assistant** — "say hi, ask questions
about the app, and eventually have it do things" — convenient and opt-in, plus
a **one-click model marketplace** to browse and download open models with live
progress. It must be **off by default** (not every user wants it).

Synapse already runs the cloud coder CLIs (Claude/Codex/Copilot) as PTY
sessions. The local LLM is a *different* surface: an in-app chat backed by the
user's own **Ollama** engine (`127.0.0.1:11434`), which Synapse can also detect,
install, and start/stop. (A key architectural note recorded in the roadmap:
token/cost "usage tracking" is only feasible for this **local** model — we run
the cloud CLIs as PTYs and cannot see their API usage.)

## Decision

### Engine bridge — `ollama_client.py`
One async module owns the Ollama integration: `is_installed()` (via
`runtime_resolution.resolve_command("ollama")`), `server_up()`, `list_models()`
(`/api/tags`), `start_server()` / `stop_server()` (best-effort lifecycle so the
user can open/close the engine), `chat()` (`/api/chat`, non-streaming for v1),
and `pull()` (streaming `/api/pull`, used by the marketplace). Every entry point
degrades gracefully so the UI shows an honest "not installed / not running"
state. **`httpx` promoted to a runtime dependency.**

### Persisted chat — migration `013_assistant.sql` + `assistant.py` + `routes_assistant.py`
- `assistant_settings` (single row, **`enabled` defaults 0** — opt-in), persisted
  `assistant_chats` + `assistant_messages` so the user can open / close / resume
  conversations and pick from their installed models.
- REST (token-guarded): `GET /assistant/status` (installed / server_up / enabled
  / models), `GET|PATCH /assistant/settings`, `POST /assistant/engine/start|stop`,
  chats CRUD, and `POST /assistant/chats/{id}/messages` which (optionally)
  prepends a **live-state system message** (projects + squads + tools) so
  "what's the boss doing?" gets a real answer, runs the turn through Ollama, and
  persists both messages.

### Renderer (Phase L2)
A new **"Assistant" nav tab** (auto-wired via `NAV_ITEMS`) with a model picker
(installed models), open/close engine, new/resume/delete chats, and chat. A
**Settings toggle gates the whole surface** (off by default; when off the tab +
quick-ask hide and no engine starts). A **global quick-ask** (palette/mic) seeded
with `/ai/context` for one-shot questions from any screen.

### Model marketplace (Phase M) — `routes_models.py` + `ModelBrowser`
Mirrors the tool marketplace (`routes_marketplace.py` + `MarketplaceBrowser.tsx`)
but with **streaming download progress**: a curated `docs/models-sample.json`
(small/popular open models), `POST /models/pull/{id}` streaming `ollama pull`
progress as `v1.model.pull_progress` WS events (like Cloudtap streams its
reader), a download manager (queue with a concurrency cap), and
`catalog_preferences` tracking. `DELETE /models/{id}` removes a model.

### Safety / future
- The assistant answers + guides today. **Taking actions** ("use X to do Y") is
  a later step: it will call the same REST surface the autonomous boss uses,
  always behind a **confirmation card** (ADR-0015), never auto-running dangerous
  actions.
- Voice in/out is ADR-0015 (Web Speech now, local Whisper — a marketplace model —
  later).

## Consequences
- A private, offline-capable assistant lives beside the cloud coders, opt-in and
  convenient, with zero new runtime service to babysit (Ollama is the user's).
- The model marketplace reuses proven marketplace + streaming patterns.
- Honest scoping: real token/cost usage is local-model-only.

## Alternatives considered
- *llama.cpp / a bundled engine* — heavier to ship + manage; Ollama is the
  pragmatic, popular, user-installable choice with a clean HTTP API.
- *Proxy the cloud CLIs for usage stats* — rejected; we don't sit in their API
  path and won't intercept their auth.
