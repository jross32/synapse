# ADR-0022: One Synapse — unified coding cockpit, shared cross-AI Plan, and the usage-aware Auto-router

- **Status:** accepted (foundation; implemented across Phases Z + U)
- **Date:** 2026-06-28
- **Deciders:** Justin (owner), Claude
- **Supersedes/relates:** ADR-0020 (AI Factory / Case Engine — folded IN, not run
  as a separate app), ADR-0021 (AI bundles), ADR-0017 (marketplace + MCP wiring),
  ADR-0018 (workers = role + personality).

## Context
Two AI coders (Claude, Codex) have been building Synapse. Codex landed an AI
Factory + Case Engine + a **separate `ai_os` web app** and left a large
uncommitted spread (coder_workspace, benchmarks, installed_pages, fast_money).
The owner's north star is unchanged: **ONE Synapse** where *all* AI coders
(Claude / Codex / Copilot / local / OpenAI-API) work together, code is done
through a chat cockpit (not raw terminals), everything merges on a shared plan,
and it keeps working — cheaply — even across usage limits.

## Decision
1. **One integrated app.** No separate runtime. The `ai_os` execution/evidence
   views fold **into** Synapse (the cockpit + Review inbox). Extras (e.g. the
   WebScraper page) become **marketplace add-ons** (present-but-installable).
2. **The coding cockpit** (Sessions, reworked): projects → chats/threads on the
   left (auto-named, renameable), chat in the middle, a **coder picker**
   (Auto / Claude / Codex / Copilot / Local LLM / OpenAI-API / ALL). Local LLM +
   OpenAI-API = true chat; the CLIs = a chat-styled layer over their PTY with the
   terminal one tap away. **ALL** = the squad/boss. Right panel =
   **Plan · Preview · Changes · Checkpoints · Files · Team · Terminal · Usage** —
   each reusing an existing Synapse system. **Full automation is the default;**
   live preview + option-previews are opt-in.
3. **The shared cross-AI Plan** (`.synapse/plan.md` per project): the single
   source of truth every coder reads, follows, updates, comments on
   (`COMMENT:` lines), and hands off on. Any coder can continue another's work.
4. **The Auto-router** picks **service × model × effort** — plus **remaining
   usage × reset proximity × cost** — for each task, aiming for the *minimum
   effort that still nails it*, routing hard/quality-critical work to the strong
   model and cheap/mechanical work to local/free tiers. `benchmarks` learns the
   cheapest-that-works route per task type.
5. **Auto-continue across limits.** On a usage limit, hand off to an available
   coder now, or schedule a resume at the detected reset time — no human prompt.
   The Plan makes resumption seamless.
6. **Legit cheap/free access first, with an explicit experimental browser bridge.**
   Local LLM (unlimited) + owner's own free-tier API keys (Gemini, Groq,
   Cerebras, OpenRouter, GitHub Models, NVIDIA NIM, …) + the **OpenAI API**
   (`web_search` + Deep Research) remain the sanctioned default "ChatGPT brain."
   In addition, Synapse may ship an **opt-in ChatGPT browser-session connector**
   for the owner's own account/workflow when the goal is to reuse the user's live
   ChatGPT projects, folders, and conversations inside Synapse. That connector
   must stay browser-managed (no raw Apple/OpenAI credential material copied into
   prompts, env files, or project memory), be clearly marked experimental, and be
   safe to disable or clear at any time.
7. **Fused automation MCP** (first-class installable): the owner's web-scraper +
   real mouse/keyboard/vision live control, used for testing/UX and asset
   acquisition, and to dogfood Synapse itself.

## Cross-AI workflow (non-negotiable, enforced)
Every coder runs `scripts/preflight.ps1` first (claims next-free ADR/migration,
flags oversized uncommitted diffs), lands **small complete tested commits**, and
keeps ADR/CHANGELOG/PROGRESS/roadmap in sync (ADR-0019 doc-sync discipline). This
ADR is the architecture any coder builds toward — no divergent parallel product.

## Consequences
- One app to build, package, sell, and keep consistent; every panel reuses an
  existing subsystem, so the cockpit is *more* capable than Claude/Codex, not a
  reimplementation.
- Codex's committed AI Factory / Case Engine is kept and **integrated** (its run
  board becomes the cockpit's Team/Changes surfaces); its separate app is retired.
- Usage-aware routing + auto-continue = "code 24/7" within the default
  low-cost path, with any browser-session bridge kept explicit and opt-in.

## Follow-ups (tracked in the plan: Phases Z0–Z9 + U)
Triage + integrate Codex's WIP; fold `ai_os` in; build the cockpit + Plan; the
fused MCP; usage tracking + auto-continue; connectors (free tiers, Shopify, SEO);
full desktop + mobile dogfood; a reusable "Full Audit & Ship" workflow.
