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
4. Before any Unity create/import/test/build job, run `python scripts/game_dev_studio.py unity-preflight`. This checks disk headroom, whether Unity is blocked on an interactive software-terms window, and whether headless Unity can reach a usable Editor state. If it reports `unity_license_required` or `unity_terms_required`, stop automated Unity execution, emit a warning/blocked event, and ask the user only for the required interactive step. Never accept legal/software terms on the user's behalf. Do not repeatedly launch Unity while the blocker is unresolved.
5. Treat disk space as a production constraint. When free space is tight, prefer primitive/procedural assets, minimal packages, one engine version, disposable `Library/`, `Temp/`, `Logs/`, and `Builds/` outputs, and avoid duplicate engine installs or large asset packs. Use a job-specific minimum-free-space threshold when a build is expected to be large.
6. Blender is a supporting dependency. If Blender is missing, run `python scripts/game_dev_studio.py ensure-blender --install`. Tell the user what is being installed and why while installation occurs.
7. Major game engines require user approval before installation. If the requested/new project needs Unity, Unreal, Godot, or another major engine and it is absent, explain which engine is needed and ask before installing it.
8. If an existing project already declares an engine, prefer that engine instead of suggesting a migration.
9. Use semantic operations first: edit project/source files, invoke documented build/test commands, run Blender Python/background jobs, inspect logs, and capture screenshots. Use Reflex desktop control only when a GUI-only step is genuinely required.
10. Every material asset must have provenance: source URL/path, license, commercial-use status, attribution requirement, modifications, and project usage. Never scrape or bypass an asset store's access controls.
11. Study references before reinventing mature systems. Use `reference-scan` for public/open-source source trees, explicitly licensed references, or user-owned local builds. Treat unknown-rights sources as analysis-only. Never source pirated ROMs, bypass access controls, or automatically copy reference code/assets/data into the game.
12. Do not invent progress. Emit real events using the live-event schema in `references/live-studio-events.md`.
13. A task is not finished merely because code was written. Build it, launch/playtest it when practical, inspect console/errors, collect visual proof, and record what was actually verified.
14. Verification and release gates are fail-closed. If lint, tests, build, diff checks, secret scans, or other required gates return nonzero, stop that release sequence and fix or explicitly record the blocker before commit/push. Do not chain later release actions behind a failing command without checking its exit status.

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

Use `python scripts/game_dev_studio.py unity-create --project <path>` for new Unity projects instead of invoking `-createProject` directly. The wrapper refuses existing targets, runs preflight first, verifies required Unity project markers, and rolls back only newly created partial output when creation fails. Never delete or overwrite a pre-existing target as cleanup.

Before Unity automation, verify four separate facts: the requested Editor version exists, sufficient disk headroom exists for the job, no interactive Unity software-terms prompt is blocking startup, and the Editor can acquire a valid license in batch mode. Installation alone is not proof that Unity is usable. A signed-out Unity Hub may leave the Editor installed but unable to run headlessly. Treat software-terms acceptance and authentication/license activation as explicit interactive boundaries and preserve all other work while waiting for the user.

For storage-constrained machines, keep Unity reference projects intentionally small: built-in primitives, generated materials, compact scenes, no duplicate engine versions, no large sample/asset packs, and no committed `Library`, `Temp`, `Logs`, or build output. Measure free space again before large imports or release builds.

## Unity policy boundary

The AI may help the user build their own Unity project by writing/inspecting their project materials and using user-authorized workflows. Do not point unofficial bots/scrapers at Unity services or the Asset Store. Current Unity terms require AI agents/MCP/automated callers interacting with Unity Offerings to use Unity-authorized pathways. If direct agentic editor/service integration is desired, verify the current authorized mechanism before enabling it.

Prefer project-file editing, ordinary documented build tooling, and user-owned content where that fits the current authorization. Keep Unity service/Asset Store acquisition separate from general web/CC0/open-licensed asset acquisition.

## Reference Lab / game-study workflow

Use references to improve how Game Dev Studio builds games without turning reference analysis into silent copying. Run:

`python scripts/game_dev_studio.py reference-scan --source <path> [--source-url <url>] --rights-basis <open-source|licensed|user-owned|unknown> [--license <declared-license>] [--output <study.json>]`

The scanner is intentionally analysis-first:

- **Unity source**: detect direct or nested projects, engine version, package manifest, scenes/prefabs/scripts/tests, and architecture signals such as ScriptableObjects, Addressables, Input System, Cinemachine, UI Toolkit, DOTS/Burst, Netcode, URP/HDRP, Multiplayer Services, Vivox, Localization, Timeline, and NavMesh.
- **Built Unity games**: identify observable build structure, scripting backend clues, managed assembly names, and executable/data layout without automatically decompiling or extracting content.
- **Blender references**: inventory `.blend` source, exported models, and texture files. Do not execute embedded/untrusted scripts automatically.
- **ROM binaries**: default to fingerprint/size/type evidence only. Analyze a ROM only when it is locally provided or otherwise legally obtained by the user; do not locate or download unauthorized ROM copies.
- **Rights/provenance**: hash root license/notice files where present, retain source URL/path and rights basis, and emit a reuse policy. `unknown` rights always fail safe to analysis-only.

Reference findings should become **transferable design/engineering hypotheses**: camera behavior, content/data modeling, input architecture, enemy/creature systems, progression structure, rendering strategy, networking, asset-production stages, test patterns, and performance constraints. Validate those hypotheses in the target game's own code and benchmarks. Do not copy distinctive protected characters, names, maps, art, audio, dialogue, proprietary datasets, or binary-extracted assets. Even for open-source code, verify the actual license and attribution/redistribution obligations before reuse.

For a genre study (for example, a creature-collection RPG), combine at least one genre-relevant reference with at least one modern engine/reference project. This keeps genre lessons separate from obsolete engine practices. Prefer original game identity and mechanics inspired by generalized patterns rather than a branded clone.

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

## Benchmark-driven release contract

Treat every Game Dev Studio version as an engineering experiment, not a version-number exercise.

Before implementation, record the problem, the reason it matters, the current baseline, the intended improvement, and acceptance criteria. Research current engine/tool documentation when behavior, APIs, package versions, licensing, or best practice could have changed.

Before release, require evidence appropriate to the change:

- direct helper/regression tests for Studio automation behavior;
- engine-native compile/import success;
- Edit Mode and Play Mode tests for Unity changes when applicable;
- coverage as execution evidence, never as a substitute for behavioral assertions;
- build result, duration, output bytes, warnings, and errors from the engine build report;
- storage delta for large generated caches/builds or dependency changes;
- launch proof and visual proof for player-facing changes;
- performance measurements against a named accepted baseline when runtime behavior could regress;
- exact limitations, skipped checks, infrastructure failures, and non-comparable measurements.

Hard correctness failures are release blockers. Benchmark movement is compared against an explicit tolerance and investigated when material; do not invent thresholds after seeing a result. Never convert an infrastructure timeout into a product failure or success.

For reference projects, preserve a small deterministic benchmark fixture. A Unity reference fixture should be able to prove: isolated preflight, transactional creation, package resolution, compile, Edit Mode tests, Play Mode tests, build, launch, screenshot/visual inspection, and performance capture. Record machine-readable evidence under `.synapse/benchmarks/` so later versions can compare against prior accepted baselines.

## Unity benchmark validity

For Unity runtime evidence, follow `references/unity-benchmark-contract.md`. Validate machine-readable runtime output with `python scripts/game_dev_studio.py benchmark-validate --input <benchmark.json> --expect rendered` (or `headless`). A headless `Null Device` result is not rendering evidence. Use warm-up-aware steady-state samples, mark unsupported counters unavailable, and never claim cold-cache versus warm-cache build speedups as directly comparable.

For rendered release evidence, verify engine-native screenshot bytes and hash when available, record benchmark presentation settings, and preserve rejected benchmark runs as compact provenance. Diagnose isolated max-frame failures before changing a threshold.

When host contention can invalidate rendered performance evidence, use `benchmark-wait` instead of manually retrying the player. Require a sustained quiet window (for example --max-cpu-percent 65 --stable-samples 4), block known conflicting engine/player processes, and pass a fingerprint manifest when one exists so source or executable drift aborts the launch. Keep the performance acceptance thresholds unchanged; the idle gate exists to prevent false negatives and cherry-picking, not to make a slow build pass. After the run, validate the resulting artifact separately with `benchmark-validate`.
