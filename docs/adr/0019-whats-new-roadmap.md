# ADR-0019: In-app "What's New" + Roadmap (the path) + doc-sync discipline

- Status: Accepted (MW8 shipping)
- Date: 2026-06-24
- Deciders: Justin (owner), Claude

## Context

The owner wants users — and the AI working on the project — to see **inside the
app** both what shipped (a changelog / version log) and what's coming (the
roadmap / ADRs, "in the works / coming soon"), presented professionally as a
**path**. And: when an idea changes the plan, the relevant docs should be
reviewed + updated so the in-app view stays current.

## Decision

### Source of truth (docs, not a new DB)
- **`CHANGELOG.md`** (repo root, Keep-a-Changelog) — what shipped, per version.
- **`docs/roadmap.json`** — a curated, user-facing distillation of the plan:
  each item `{id, title, status: shipped|in_progress|coming, summary, phase,
  adr}`. The internal plan stays private; this is the public path.

### Daemon — `about.py` + `routes_about.py`
- `GET /about/changelog` parses `CHANGELOG.md` into versions → sections → items
  (folding bullet continuation lines). `GET /about/roadmap` reads
  `roadmap.json`. Both degrade to empty rather than erroring.
- Path resolution via `runtime_paths.bundled_changelog/bundled_roadmap`
  (dev: repo root / docs; packaged: bundled under `resources/docs`). Packaging:
  electron-builder `extraResources` now ships the whole `docs/` (json + CHANGELOG
  + roadmap).

### Renderer — a "What's New" nav tab
`pages/Whatsnew.tsx`: two views — **Roadmap** (a vertical timeline grouped
In the works → Coming → Shipped, with ADR tags) and **What's changed** (version
cards with rendered `**bold**`/`` `code` `` bullets).

### Doc-sync discipline (codified in `CLAUDE.md`)
When an idea changes the plan or a feature lands, **review the according docs and
change only what needs changing**: the ADR (`docs/adr/`), `CHANGELOG.md` (append
under the in-progress version), and `docs/roadmap.json` (flip an item's status /
add a coming item). The in-app surface reads these, so keeping them current keeps
the app's path current.

## Consequences
- Users + the AI see a live, honest "where we are / where we're going" in-app.
- No new storage; the docs are the data, so updating them updates the app.
- One discipline keeps ADRs, changelog, and roadmap in sync.

## Alternatives considered
- *Parse the private plan file directly* — rejected; the plan is internal +
  messy. A curated `roadmap.json` is the clean public view.
- *Bundle a markdown renderer lib* — avoided; a tiny inline formatter covers the
  `**bold**`/`` `code` `` the changelog actually uses.
