# ADR-0018: Workers = Roles + Personalities (collaboration) + data-driven squad presets

- Status: Accepted (MW3 shipping; MW4 presets to follow)
- Date: 2026-06-25
- Deciders: Justin (owner), Claude

## Context

A squad worker today is just a **role** (`AgentRoleTemplate` — planner,
implementer, reviewer, …). The owner's key ask: a worker should be **role +
personality**, so the *same* role can appear twice with *different* personalities
and the two AIs actually bring different voices — collaborate and debate instead
of echoing each other (e.g. "Designer + Visionary" vs "Designer + Skeptic").

## Decision

### Personalities are a small, seeded, editable layer
New `personalities` table (migration `015`) + `personalities.py`:
`{id, name, blurb, traits[], prompt_preamble_md, voice, builtin, sort_order}`
with full CRUD and five seeded built-ins that create useful tension when mixed —
**Pragmatist, Perfectionist, Skeptic, Visionary, Mediator**. Seeded on startup in
`app.py` alongside `seed_default_role_templates`. Built-ins re-seed if missing, so
they're protected from deletion (the route returns `409`); they can still be
edited.

### A roster entry carries an optional personality
`agent_work_items` gains a nullable `personality_id` (same migration); it's
threaded through `AgentWorkItem` / `AgentWorkItemCreate` / `create_work_item` /
`_row_to_work_item`.

### The synthesized worker prompt layers role + personality
`ai_context_memory.write_role_prompt` gains `personality_name` +
`personality_preamble_md` and emits a **`## Personality`** section after the role
guidance. `routes_agent_squads.launch_work_item` loads the work-item's personality
(defensively — a deleted personality must never block a launch) and passes it in.
So two same-role workers get genuinely different system prompts.

### Roles already cover the new crews — no duplicates
The seed roster already includes `tester` (Tester/QA), `devops`, `docs-writer`,
`researcher`, `reviewer`, `designer`. The new **App-shipping** and **Deep-Research**
crews (MW4) therefore *reuse* existing roles and differ only by personality — we
deliberately did **not** add duplicate roles.

### REST + types
`routes_personalities.py` → `GET/POST /personalities`,
`PATCH/DELETE /personalities/{id}` (audited; built-in delete → `409`). `Personality`
/ `PersonalityCreate` / `PersonalityUpdate` registered in `model_registry()`.

## Consequences
- Same role + different personality = real collaboration/debate — the owner's
  "Synapse identity" feature.
- Personalities are data: seeded, listable, installable later (marketplace), and
  editable — no code change to add one.
- MW4 squad presets compose existing roles × personalities (UI/UX audit crew,
  App-shipping crew, Deep-Research crew, …).

## Alternatives considered
- *Fold personality into the role template* — rejected; it's orthogonal (one role,
  many personalities) and the owner wants it as its own selectable type.
- *Hard-code personalities in the prompt builder* — rejected; they must be
  user-visible, editable, and marketplace-installable.
