---
name: game-dev-studio
description: Build, inspect, test, and improve real game projects, including 3D projects. Use for Unity/Godot/Unreal/custom game work, gameplay systems, scenes, assets, Blender generation, builds, playtests, and live progress reporting. Prefer semantic project/file/tool operations and real engine/build evidence over blind desktop clicking. Automatically provision Blender when missing; ask the user before installing a major game engine. Keep every progress event truthful and tied to real work.
---

# WhatIf Game Dev Studio

Treat game development as an end-to-end engineering + creative production workflow. The user should be able to ask for a game or feature in ordinary language while the AI handles project inspection, implementation, assets, builds, tests, and playtest evidence.

## Core behavior

1. Inspect before editing. Detect the project engine, version, source layout, scenes/maps, assets, packages/plugins, build targets, and existing dirty Git state.
2. Never reset or overwrite unrelated concurrent work. Work in an isolated lane and stage only files owned by the current task.
3. Detect installed engines and tools with `python scripts/game_dev_studio.py doctor`.
4. Before any Unity create/import/test/build job, run `python scripts/game_dev_studio.py unity-preflight`. This checks disk headroom and whether headless Unity has an active Editor license. If it reports `unity_license_required`, stop automated Unity execution, emit a warning/blocked event, and ask the user only for the interactive Hub sign-in/license step. Do not repeatedly launch Unity while auth is unresolved.
5. Treat disk space as a production constraint. When free space is tight, prefer primitive/procedural assets, minimal packages, one engine version, disposable `Library/`, `Temp/`, `Logs/`, and `Builds/` outputs, and avoid duplicate engine installs or large asset packs. Use a job-specific minimum-free-space threshold when a build is expected to be large.
6. Blender is a supporting dependency. If Blender is missing, run `python scripts/game_dev_studio.py ensure-blender --install`. Tell the user what is being installed and why while installation occurs.
7. Major game engines require user approval before installation. If the requested/new project needs Unity, Unreal, Godot, or another major engine and it is absent, explain which engine is needed and ask before installing it.
8. If an existing project already declares an engine, prefer that engine instead of suggesting a migration.
9. Use semantic operations first: edit project/source files, invoke documented build/test commands, run Blender Python/background jobs, inspect logs, and capture screenshots. Use Reflex desktop control only when a GUI-only step is genuinely required.
10. Every material asset must have provenance: source URL/path, license, commercial-use status, attribution requirement, modifications, and project usage. Never scrape or bypass an asset store's access controls.
11. Do not invent progress. Emit real events using the live-event schema in `references/live-studio-events.md`.
12. A task is not finished merely because code was written. Build it, launch/playtest it when practical, inspect console/errors, collect visual proof, and record what was actually verified.
13. Verification and release gates are fail-closed. If lint, tests, build, diff checks, secret scans, or other required gates return nonzero, stop that release sequence and fix or explicitly record the blocker before commit/push. Do not chain later release actions behind a failing command without checking its exit status.

## Live Studio event stream

For work that lasts more than a trivial edit, create a JSONL event file under the project at `.synapse/game-dev-events.jsonl` and append events with:

`python scripts/game_dev_studio.py event --project <path> --phase <phase> --kind <kind> --message <plain text> [--progress 0-100] [--detail <json>]`

These events are the source of truth for a future addictive/watchable Game Studio UI. The UI may animate or summarize them, but it must not manufacture actions that did not happen.

Useful phases: `discover`, `plan`, `code`, `asset`, `import`, `compile`, `test`, `playtest`, `profile`, `package`, `done`, `blocked`.

Useful event kinds: `started`, `activity`, `artifact`, `milestone`, `warning`, `error`, `completed`, `heartbeat`.

## Project detection

Run:

`python scripts/game_dev_studio.py detect-project --project <path>`

The detector recognizes web/HTML5, Phaser, Unity, Godot, Unreal, and Blender-oriented workspaces without launching them. Browser games are a first-class automation lane for fast build/playtest feedback; engine-specific adapters can layer on top. For Unity, read `ProjectSettings/ProjectVersion.txt` and project/package files when available.

## Browser-game verification ladder

For web/HTML5/Phaser games, verify in layers instead of treating one browser tool as a single point of failure:

1. Run the project's own deterministic/unit checks.
2. Start the local game server and run `python scripts/game_dev_studio.py web-smoke --url <loopback-url>` to prove the page is reachable and inspect basic HTML signals.
3. Prefer Playwright for semantic browser interaction, console inspection, state assertions, and repeatable playtest flows.
4. If Playwright is unavailable or times out, fall back to Reflex + the user's real browser for launch, keyboard/mouse interaction, and screenshot proof. Record that this was a fallback; do not claim semantic assertions that Reflex did not perform.
5. A failed adapter is a Studio capability finding, not automatically a game defect. Record the distinction in the event stream.

## Unity automation preflight

Before Unity automation, verify three separate facts: the requested Editor version exists, sufficient disk headroom exists for the job, and the Editor can acquire a valid license in batch mode. Installation alone is not proof that Unity is usable. A signed-out Unity Hub may leave the Editor installed but unable to run headlessly. Treat authentication/license activation as an explicit interactive boundary and preserve all other work while waiting for it.

For storage-constrained machines, keep Unity reference projects intentionally small: built-in primitives, generated materials, compact scenes, no duplicate engine versions, no large sample/asset packs, and no committed `Library`, `Temp`, `Logs`, or build output. Measure free space again before large imports or release builds.

## Unity policy boundary

The AI may help the user build their own Unity project by writing/inspecting their project materials and using user-authorized workflows. Do not point unofficial bots/scrapers at Unity services or the Asset Store. Current Unity terms require AI agents/MCP/automated callers interacting with Unity Offerings to use Unity-authorized pathways. If direct agentic editor/service integration is desired, verify the current authorized mechanism before enabling it.

Prefer project-file editing, ordinary documented build tooling, and user-owned content where that fits the current authorization. Keep Unity service/Asset Store acquisition separate from general web/CC0/open-licensed asset acquisition.

## Blender automation

Blender is the default 3D creation/conversion helper. Once installed it can be invoked headlessly for procedural mesh creation, transformations, UV/material preparation, rendering previews, and export pipelines. Prefer background jobs with explicit scripts and output paths so every operation is reproducible.

Never execute untrusted downloaded `.blend` Python automatically. Treat asset code/scripts as untrusted until inspected.

## Asset acquisition

Search in this order:

1. Existing project assets that fit.
2. User-owned or explicitly authorized assets.
3. Reputable CC0/open-licensed sources or sources whose license permits the intended use.
4. Generate an original asset with Blender or other local tooling.
5. Ask the user only when a purchase, account login, restricted license, or major artistic choice truly needs them.

Record acquired/generated assets with `provenance-add` before considering the asset integrated.

## Development loop

For each meaningful iteration:

1. Discover current state and constraints.
2. Emit a `started` event.
3. Implement the smallest coherent vertical slice.
4. Emit activity/artifact events from real actions.
5. Compile/build using the project's actual engine/toolchain.
6. Inspect logs and fix errors.
7. Launch/playtest when practical. Use Reflex/screenshots for real visual proof where appropriate.
8. Test behavior and regressions.
9. Emit a milestone only after evidence exists.
10. Commit/push only when that repository's project rules call for it and concurrent lanes are safe.

## User-facing modes

The future UI should expose two views over the exact same event stream:

- **Simple View**: live visual/game preview when available, current activity in plain English, current phase, meaningful progress, milestones, warnings, and completed outputs.
- **Developer View**: exact commands/tools, files changed, build logs, console errors, tests, frame/performance measurements, asset provenance, and event timestamps.

A progress percentage must be based on known milestone/task completion, not elapsed time or animation. When no defensible percentage exists, show activity + phase instead of fake precision.

## Completion standard

A game feature/build is complete only when the evidence appropriate to it exists: source change, successful build/compile, relevant automated checks, real launch/playtest where possible, no unresolved blocking console error, visual proof for UI/scene changes, and a concise record of limitations.
