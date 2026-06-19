# ADR-0008 — Marketplace reorg + sidebar customization

Date: 2026-06-19
Status: Proposed (gated on user "go" per phase)
Supersedes: —
Related: ADR-0001 (tool marketplace), ADR-0006 (project objectives),
         `plans/how-is-it-that-staged-meteor.md` Phase D

## Context

Two intertwined surface problems surfaced in the user wishlist that
share a single underlying solution:

1. **The Tools marketplace is a flat alphabetical grid.** With 11+
   bundled tools today (and the long tail growing once Phase C ships
   AI quick-actions as their own catalogue), the grid is hard to
   skim. Users asked for *"the marketplace in the tools sections or
   like what users can download, need to be more organized and
   sensible to the user"*.

2. **The sidebar is fixed at 6 default tabs.** v0.1.36 Phase A6
   landed a reorder + hide/show customization (Home + Settings
   locked). The wishlist took it further: *"when a user downloads a
   app or tool or something that has the ability to be its own tab,
   then there will be a way for the user, well, there is going to be
   a way, your going to make it"* — i.e. marketplace entries should
   be promotable to sidebar tabs.

Both reduce to the same shape: a **workspace layout schema** that
the Tools, Quick-actions, and Sidebar surfaces all read from. Phase
A6's `localStorage('synapse.sidebar.layout')` is a stepping stone;
this ADR lifts it into a first-class concept.

## Decision

Four sub-phases. **D1 + D2 must ship together** (the marketplace
reorg ties into the quick-actions catalogue). **D3 + D4 each get
their own go**.

### D1 — Tools marketplace reorg

Today: `<MarketplaceBrowser>` renders one giant `<ul>` sorted by id.

#### Categorisation

Marketplace entries already carry a `tier` field
(`declarative` / `handler`). Extend the registry schema with a new
optional `category` enum:

```jsonc
{
  "id": "open-folder",
  "tier": "declarative",
  "category": "system",   // NEW
  ...
}
```

Curated categories:
- `ai-coder` (claude, codex, copilot)
- `network` (cloudtap)
- `system` (open-folder, tail-log, npm-install, docker-compose-up)
- `dev-tools` (git-log-recent, git-status)
- `data` (anything that reads/writes user data; future)

A tool with no `category` falls through to a default "Uncategorised"
bucket so older registries don't break.

#### UI

`<MarketplaceBrowser>` becomes a two-column layout:
- **Left rail** (sticky on `md+`): the category list, with counts.
  Plus a "Recently installed" pinned-to-top entry seeded from the
  same data the v0.1.24 install flow already records on disk.
- **Right grid**: the existing tile grid, filtered to the active
  category, search box always visible at the top.

Filter chips (verified / community, runnable / read-only) move into
a single "Filters" pill button that opens a popover — keeps the
default view clean.

#### Schema change

The marketplace fallback at `docs/marketplace-sample.json` gains a
`category` field on each entry. Backward-compatible: missing
category = uncategorised. Update
`test_marketplace_bundled_handlers_load_with_valid_shape` to assert
the category enum is one of the known values (or absent).

### D2 — Quick-actions catalogue

Quick-actions (Phase F shipped 4 bundled templates) are conceptually
"AI workflows" — a curated catalogue. Today they're discovered only
through the Sessions page rail.

This sub-phase brings them into the Marketplace UX:

- New "Quick-actions" tab next to "Browse" inside the Tools page
  (today the Tools page has `installed` / `browse` only).
- Same categorisation as D1: categories ('coding', 'documentation',
  'admin' etc.).
- Each catalogue card shows the template name + description + the
  default CLI argv it ships with. "Open" button = same UX as the
  Sessions rail (POST `/api/v1/quick-actions/{id}/launch`).
- A "Pin to sidebar" toggle on each card (feeds D3).

The registry for quick-actions stays in `templates/quick-actions/`;
no new server route. The Tools page just lists what
`GET /api/v1/quick-actions` already returns, with extra UI chrome.

### D3 — Sidebar item promotion from marketplace

The Phase A6 layout schema gets extended:

```jsonc
{
  "order": ["home", "apps", "sessions", "qa:improve-synapse", "settings"],
  "hidden": ["processes"],
  "promoted": [
    {
      "id": "qa:improve-synapse",
      "label": "Improve Synapse",
      "icon": "sparkles",
      "kind": "quick-action",
      "ref": "improve-synapse"
    }
  ]
}
```

- `promoted` items get their own NAV_ITEM entries at runtime.
- Click on a promoted quick-action = same as the catalogue Open
  button (spawns the session).
- Click on a promoted tool = navigates to the Tools page with that
  tool's tile pre-expanded.
- Reorder + hide/show work the same as Phase A6 locked items
  (Home + Settings still pinned).

`<SidebarSettings>` from Phase A6 gains a "Promoted" section that
lists every promotion the user has added; remove + reorder there.

#### REST: no new route needed

The schema is renderer-only (still `localStorage`-backed). The
marketplace tile's "Pin to sidebar" toggle just edits the same key.

### D4 — Workspace-layout schema (cleanup)

Lift the sidebar's `synapse.sidebar.layout` localStorage key into a
generic `synapse.workspace.layout`. Other surfaces that today have
their own ad-hoc preferences read from the same place:

- Home featured slideshow order (today: hard-coded "pinned, then
  recent").
- Apps grid sort (today: "pinned + alphabetical").
- Sessions tab strip ordering.

Adds a `migration` step in renderer/lib/workspace.ts that detects
the old key + copies into the new shape on first read. No daemon
work.

## Consequences

### Positive
- **Discoverability**: the marketplace becomes browseable with intent.
  "Show me network tools" / "show me AI workflows" instead of one
  giant scroll.
- **Same component owns both Tools and Quick-actions** — one filter
  surface, one categorisation. Adding a marketplace category in the
  future is one constant.
- **Sidebar promotion** is the bridge between "I downloaded a tool"
  and "I use this every day" — currently users have to remember to
  navigate to Tools every time. Promotion eliminates the trip.
- **Workspace-layout schema** generalises Phase A6's work without
  rewriting it. Phase A6 stays useful; D3/D4 just expand its scope.

### Negative / honest trade-offs
- **Categories require manual curation.** A tool author has to pick
  the right bucket. Some tools won't fit cleanly — we accept "system"
  as the catchall.
- **The marketplace grid was simple.** Two columns + filters add UI
  complexity. Worth it once the catalogue grows past ~15 tools;
  premature now (which is why D1/D2 ship together — one redesign).
- **Promoted sidebar items can confuse**. The user installs a tool,
  toggles "Pin to sidebar", forgets, then later wonders why the
  sidebar has stale entries. Mitigate: SidebarSettings shows a
  "Promoted" section with one-click un-promote.
- **localStorage scoping**. Promoted items live per-machine. If the
  user pairs two machines they have to set up promotions twice.
  Acceptable for v0.1.x; cloud-sync is a separate ADR if it ever
  happens.

## Detailed design (locked at acceptance)

### Category enum

```ts
type MarketplaceCategory =
  | 'ai-coder'
  | 'network'
  | 'system'
  | 'dev-tools'
  | 'data';
```

Stored as a string. Unknown values fall through to a "More" bucket
so a future-added category doesn't crash the renderer.

### Migration of Phase A6's localStorage key

In `renderer/lib/workspace.ts` (new):

```ts
// One-shot migration from the v0.1.36 sidebar key.
const v1 = window.localStorage.getItem('synapse.sidebar.layout');
if (v1 && !window.localStorage.getItem('synapse.workspace.layout')) {
  // Wrap the old shape inside the new schema.
  window.localStorage.setItem(
    'synapse.workspace.layout',
    JSON.stringify({ sidebar: JSON.parse(v1), promoted: [] })
  );
}
```

The old key is left in place so a rollback to v0.1.36 still works.

### Marketplace tile "Pin to sidebar"

A small star/anchor toggle in the marketplace tile header. Click =
add a `promoted` entry to the workspace layout, refresh the
sidebar (existing 'storage' event listener picks it up).

## Status

Proposed. Implementation does NOT start until the user gives the go
on D1 + D2 (which ship together — they share the categorised
catalogue UI). D3 + D4 each get their own go.

## Verification plan

### D1 + D2
- `test_marketplace_bundled_handlers_load_with_valid_shape` extended:
  every entry's `category` (if present) must be one of the known
  enum values.
- Live: open Tools → Browse, sidebar lists categories with counts;
  filter switches the grid; search filters cumulatively.
- Open Tools → Quick-actions, same UX as Browse, "Open" button
  spawns the workbench session.

### D3
- Click "Pin to sidebar" on a quick-action card.
- Sidebar refreshes with the new item present.
- Click the new sidebar item → session launches.
- Open SidebarSettings → Promoted section lists the item with an
  "Unpromote" button.

### D4
- Old `synapse.sidebar.layout` key is migrated into the new
  `synapse.workspace.layout`.
- Existing reorder / hide from Phase A6 still works (regression
  guard).
