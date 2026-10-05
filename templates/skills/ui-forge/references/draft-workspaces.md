# UI Forge Draft Workspaces

UI Forge drafts are isolated, conflict-aware copies of a project for exploring frontend directions without mutating the live workspace.

Use `scripts/draft_workspace.py` when a task is exploratory, broad, collaboration-heavy, or likely to benefit from comparing multiple visual directions before acceptance.

## Core safety model

A draft contains:

- an immutable base snapshot from draft creation time
- an isolated editable workspace
- a manifest with base hashes and lifecycle state
- a changed-file diff/status surface
- conflict-aware acceptance
- an acceptance backup for every overwritten/deleted live file

Generated/heavy directories such as `.git`, `.synapse`, `node_modules`, `dist`, `build`, `.next`, and coverage/cache directories are excluded. Because the workspace lives beneath the project `.synapse/ui-forge/drafts/` tree, normal Node resolution can still walk up to the live project's installed dependencies without copying `node_modules`.

## AI workflow

Create a draft:

```text
python scripts/draft_workspace.py create <project-root> --title "Dashboard direction B"
```

Run UI Forge against the returned `workspace` path. The live project must remain unchanged while the draft is open.

Inspect status and diff:

```text
python scripts/draft_workspace.py status <project-root> <draft-id>
python scripts/draft_workspace.py diff <project-root> <draft-id>
```

Before accepting:

1. run/build the draft workspace
2. browser-test desktop/mobile and relevant states
3. run objective browser/design audits where applicable
4. satisfy the UI Forge evidence gate
5. inspect draft diff/risk classification
6. accept only if the live paths touched by the draft still match the base snapshot

Accept:

```text
python scripts/draft_workspace.py accept <project-root> <draft-id>
```

Acceptance fails closed when the same live paths changed since draft creation. Non-overlapping drafts can still be accepted independently because conflict detection is path-scoped.

## Risk gate

UI Forge drafts are intended primarily for frontend exploration. Changes to `.env*`, backend/API/server/function paths, migrations, database/schema paths, Prisma, Supabase, and similar high-risk areas are flagged. Normal accept refuses them unless `--allow-risky` is explicitly supplied.

Do not use `--allow-risky` merely to get past the gate. Treat it as a deliberate escalation requiring a separate backend/data/auth verification plan.

## Parallel directions

Multiple drafts may share the same base state. Use them for materially different layout, copy, visual-language, or interaction directions. Compare running previews and evidence rather than picking from prose descriptions.

## Discard

Discarding an open draft deletes only the draft workspace and leaves the live project untouched:

```text
python scripts/draft_workspace.py discard <project-root> <draft-id>
```

Accepted drafts are retained as audit history by the script instead of being silently deleted.
