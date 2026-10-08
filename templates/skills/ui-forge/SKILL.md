---
name: ui-forge
description: Model-independent UI product-engineering workflow for creating or materially improving a web/app interface. Use when the user asks for a beautiful/professional/premium UI, a Lovable-like builder workflow, a redesign, dashboard/landing page/app shell, visual polish, responsive overhaul, design-system cleanup, screenshot/reference-driven build, or a UI quality pass. Do not stop at code generation: inspect the real product, define the requested outcome, research authorized references as patterns, create project-native tokens/components, plan before editing, run the app, test it as a user on desktop/mobile, score the result, and repair until evidence gates pass.
---

# UI Forge

UI Forge is Synapse's reusable UI-building control plane. Its goal is not to imitate one vendor's visual style. Its goal is to reproduce and extend the workflow advantages that make specialized AI app builders consistently produce polished interfaces: strong context, design-system constraints, planning, rapid preview, browser self-verification, bounded iteration, model specialization, and measurable app-level evaluation.

The unit of success is the **running application**, not the prompt response and not the diff.

## Non-negotiable rules

1. Inspect the real project before proposing a redesign.
2. Preserve working product behavior, data truth, auth, and brand constraints unless the user explicitly asks to change them.
3. Plan the visual/interaction system before broad code edits.
4. Prefer the project's existing component system; create one coherent system if none exists.
5. Use references for principles and interaction patterns, never proprietary source/branding/copy or pixel-for-pixel cloning.
6. Make bounded changes, run the app, and look at the result in a browser before calling a UI task done.
7. Test desktop and mobile. Test loading, empty, error, success, hover/focus/disabled, overflow, and recovery states proportionate to the feature.
8. Do not trust self-description such as "looks polished". Produce evidence and score it.
9. If a high-powered model is available, use it where its strengths matter most; do not assume one model should own the whole trajectory.
10. A browser failure, broken interaction, fabricated data, inaccessible critical path, or regression is a blocker regardless of visual score.

## The UI Forge control loop

### Phase 0 — Coordinate and inspect

Before editing:
- read project AI context, rules, ADRs/backlog, design tokens, component library, routes, tests, screenshots, and current runtime state
- check for concurrent writers and avoid their lanes
- identify the existing stack and start/run/test commands
- inspect the current screen in a real browser when possible
- capture representative desktop and mobile baseline screenshots

Write a short `UI Forge brief` containing:
- user goal
- target user and primary job
- screen/flow scope
- must-preserve behavior
- product truth/data constraints
- brand personality
- current UI problems
- acceptance criteria
- target proof surfaces

### Phase 1 — Context and pattern harvest

Research only when it improves a design decision.

Preferred sources:
1. the target product itself and adjacent screens
2. its existing design system/component library
3. public/authorized reference products with similar interaction problems
4. public design-system docs and licensed open-source component sources

Use Synapse Web Scraper / browser tools to capture useful structure: headings, page sections, screenshots, forms, interactions, responsive behavior, and reusable patterns. Record **what principle was learned**, not a recipe to clone the pixels.


If the user gives screenshots, treat them as intent evidence. Extract hierarchy, density, rhythm, component families, motion, navigation, and state treatment, then rebuild in the target product's own identity.

### Phase 1.5 — Lock a Visual Target Contract

When the user provides or approves a visual target, do not proceed from an informal mental impression.

Read `references/visual-target-contract.md` and create a project-scoped Visual Target Contract before broad implementation.

The contract must:
- register the approved reference(s) or project design-reference ids
- enumerate target routes/surfaces and desktop/mobile viewports
- enumerate required sections and information architecture
- classify every material asset slot (CSS primitive, vector, production illustration, photoreal image, 3D render, device mockup, motion)
- state which elements are match/adapt/omit-with-reason/blocked
- forbid prototype signals on required polished surfaces
- define the minimum reference-fidelity score and proof set

**Fail closed on asset downgrades.** If the target visibly requires a detailed person, environment, device render, illustration, or other production asset, a simple CSS oval, generic icon, or empty gradient panel is not an acceptable substitute merely because an image provider is unavailable.

Route assets deliberately:
1. reuse an approved project asset when suitable
2. use project-native CSS/components only for genuinely primitive visual needs
3. use Synapse Image Studio for people, environments, reference-guided imagery, photoreal work, and rich 2D illustration
4. use Synapse Blender Studio for deterministic 3D/device/environment/stylized-render families or reusable source scenes
5. import a licensed/provenanced asset when appropriate
6. otherwise record a blocker and keep the visual target unresolved

Before implementation, run an asset-readiness check. When a required producer is unavailable, do not lower the bar silently; mark the contract blocked.

After each substantial implementation pass:
- capture the real running surfaces
- compare them visually against the locked target
- populate the evidence contract
- run `scripts/prototype_surface_scan.py`
- run `scripts/visual_target_gate.py`
- repair the largest remaining visual/completeness gap first
- recapture and rescore

Functional/browser correctness and visual-target fidelity are separate gates. Both must pass.

### Phase 2 — Build the project-native design grammar

Before large implementation, define or recover:
- semantic color tokens (canvas, surface, elevated, border, text, muted, accent, success, warning, danger, focus)
- typography scale and line-height rhythm
- spacing scale
- radius/elevation rules
- icon rules
- content width / grid rules
- responsive breakpoints
- component families and variants
- interaction/state rules
- motion duration/easing rules
- data/provenance display rules when relevant

Prefer semantic tokens over raw values scattered through components.

Create a compact component contract, for example:
`Button(primary|secondary|quiet|danger)`
`Card(default|interactive|metric)`
`Status(success|warning|error|neutral)`
`PageHeader(title, description, actions)`

Do not create component abstractions solely for theoretical reuse. Reuse must improve consistency or iteration speed.

### Phase 3 — Choose an experience direction

Generate 1–3 meaningfully different directions mentally or in lightweight artifacts, then choose one based on the product goal. Avoid trivial variants that differ only in color.

Evaluate each direction on:
- hierarchy
- information density
- navigation clarity
- first-glance comprehension
- brand fit
- accessibility
- mobile viability
- implementation risk
- distinctive product-specific behavior

Pick one and state why.

### Phase 4 — Plan before coding

For anything beyond a small style fix, define:
- files/components likely to change
- interaction/state changes
- responsive behavior
- data dependencies
- regression risks
- verification plan

Split broad redesigns into bounded vertical slices so each slice can be rendered and judged. Avoid giant unreviewable UI diffs.

### Phase 5 — Model specialization and routing

UI Forge is model-independent, not model-indifferent.

When multiple runtimes are available, route by evidence and strength:
- **visual/design specialist**: visual hierarchy, composition, typography, motion, creative direction
- **implementation specialist**: component architecture, state, data wiring, responsive code
- **correctness reviewer**: runtime behavior, regressions, edge cases
- **UX/accessibility reviewer**: navigation, keyboard, semantics, discoverability, mobile ergonomics

Do not fan out merely to spend tokens. Use additional models when the task is large, the first pass is stuck, or independent review materially raises confidence.

Preserve context when switching models. Summarize discoveries, constraints, attempts, failures, and current screenshots so a new worker does not restart the investigation.

### Phase 6 — Implement with fast visual feedback

During implementation:
- extend existing components/tokens first
- keep copy concise and product-specific
- prefer real content shape over lorem ipsum
- preserve data truth; never invent missing metrics to make a card look full
- handle loading/empty/error states as first-class design states
- use responsive layout primitives instead of desktop-only fixed dimensions
- keep focus/hover/pressed/disabled states coherent
- use motion only when it explains transition, hierarchy, or causality

After each meaningful slice, run/build the app and inspect the rendered result.

### Phase 7 — Real-user browser proof

A substantial UI change is not done until the running app has been exercised.

Minimum proof:
- desktop representative viewport
- mobile representative viewport
- primary user path end-to-end
- no horizontal overflow
- navigation/back/close behavior works
- forms and buttons are operable
- keyboard focus is visible on critical controls
- loading/empty/error/success states checked where applicable
- console/runtime errors checked
- screenshots captured for before/after or final states

Use Playwright/Quality OS/Reflex/browser-proof tools already present in Synapse where available.
Run `scripts/browser_audit.js` on representative desktop/mobile viewports when possible. Treat its overflow, target-size, accessible-name, label, image-alt, and heading findings as objective evidence; inspect context before promoting a diagnostic into a blocker.

### Phase 8 — Multi-lens review

Score the final running surface from 0–100 on these dimensions:
- request_fidelity
- visual_design
- ux
- responsive
- accessibility
- runtime_correctness
- browser_proof
- originality

Use `references/quality-rubric.md` and, when useful, `scripts/ui_forge.py` for a deterministic gate.

UI Forge pass gate:
- overall weighted score >= 85
- runtime_correctness >= 85
- browser_proof >= 80
- no critical failures

Any critical failure blocks completion regardless of score.

### Phase 9 — Repair loop

If the gate fails:
1. identify the lowest-scoring dimensions and blockers
2. separate visual taste problems from functional/interaction problems
3. fix the smallest root cause with the highest leverage
4. rerun the app and the affected browser proof
5. rescore

Do not endlessly restyle. Stop when evidence passes and remaining issues are explicit low-risk tradeoffs.

### Phase 10 — Learn and persist

For recurring patterns, persist useful project knowledge:
- accepted tokens/components
- successful layout grammar
- rejected anti-patterns
- mobile constraints
- domain-specific truth/display rules
- common regressions and their checks

When a workflow failure repeats across projects, improve UI Forge / Synapse Quality OS rather than adding another one-off prompt exception.

## Anti-generic visual rules

Avoid the default AI-app look unless it is genuinely right for the brand:
- purple/blue gradient as an automatic hero
- every section inside a rounded card
- excessive pills/badges
- giant empty whitespace with tiny content
- glassmorphism by default
- random decorative blobs
- identical icon+title+paragraph feature grids
- metrics without provenance or purpose
- too many equally weighted CTAs
- mobile layouts that simply stack desktop cards forever

Aim for a clear visual thesis tied to the product's job.

## Visual-edit bridge

When the task is a fine-grained visual correction, use the precision path instead of regenerating a screen:
1. identify or select the target DOM element in the running browser
2. for React/Vite development, prefer `data-ui-forge-source` tags from `scripts/babel_source_tags.mjs`
3. inject `scripts/visual_edit_bridge.js` when an interactive/select-by-selector bridge is useful; it captures source tag/id, semantic identity, computed style, geometry, viewport, and page context
4. preview safe text/class/allowlisted-attribute changes reversibly in the running browser with `window.UIForge.preview(...)`; inspect the changed geometry/style and use `commitSpec()` only when the element has an exact `data-ui-forge-source`
5. when the source tag is exact and the previewed/requested change is mechanically safe static JSX, dry-run `scripts/direct_ast_edit.mjs`; apply only if it accepts the edit and syntax reparse passes
6. otherwise make the smallest owning token/class/component prop/source edit through the main coding worker
7. rerender immediately and re-probe the same element/source tag
8. verify surrounding layout and critical behavior did not regress

If source tags are unavailable, `commitSpec()` must remain not-ready; fall back to `scripts/source_locator.py` semantic matching and the main coding worker. Browser previews are temporary decision surfaces, not source truth. Prefer precise edits over regenerating entire screens.

### CSS-owned visual style edits

For direct spacing, sizing, typography, color, border, shadow, and layout adjustments, preview the change on the selected element with `window.UIForge.preview({type: "style_props", properties: {...}})`. This preview is intentionally temporary inline style so geometry/computed style can be judged instantly; `revertPreview()` must restore the prior DOM exactly.

A `style_props` preview is **not** JSX-commit-ready. Use `styleCommitSpec()` to emit the selected browser probe plus declarations, then commit through `scripts/css_style_editor.mjs`. The editor parses stylesheets with PostCSS, matches the selected element against the rightmost selector compound, prefers exact ID/class ownership, refuses tied owners unless file + selector are explicit, patches only an allowlisted visual property set, and reparses CSS before writing.

After source commit, HMR/reload must show the requested computed style with the same UI Forge source identity and without persistent inline-style debt. If ownership is ambiguous, the value is dynamic, CSS is generated, or the property requires URLs/structural syntax, use the main coding worker instead of forcing a direct edit.

### Multi-select and atomic batch edits

When the same mechanically safe change applies to several rendered elements, do not repeat one source edit at a time. Use `window.UIForge.selectMany([...])` (or additive Ctrl/Meta/Shift selection), then `previewMany(operation)` to inspect the group change in the running browser. `commitBatchSpec()` is ready only when every selected element has a unique exact `data-ui-forge-source`.

Commit that specification with `scripts/batch_ast_edit.mjs`. The batch editor validates all operations before mutation, applies same-file edits from later source positions to earlier positions so source columns remain stable, and restores every touched file if an apply step fails. Mixed safe/unsafe selections must leave the source tree byte-identical. After commit, rerender and re-probe every selected source ID, then run affected desktop/mobile proof.

Batch editing is for one coherent operation across a set of elements, not a shortcut for unrelated edits. If selections need different semantic changes, use separate bounded operations or the main coding worker.


## AI execution contract

UI Forge is designed to be invoked by AI workers through Synapse, not only read by humans. The canonical human entry is the `ui-forge` Synapse quick action. The canonical AI run controller is `scripts/conductor.py`, backed by `references/workflow-contract.json` and the persistent run state.

For substantial work:
- initialize a persistent state file with `scripts/conductor.py init`; use `conductor.py status` as the compact resume/next-action packet
- record artifacts/proof through the conductor and complete phases through `conductor.py complete`; it must refuse completion when the declared contract is not satisfied
- use the state file to resume after a model switch, chat interruption, or failed route instead of restarting discovery
- record recurring workflow/tool failures with `scripts/friction_ledger.py`; two repeats or one high/critical failure is promoted into a workflow-improvement candidate
- capture promoted friction in Synapse project memory/backlog when it represents a reusable platform improvement

The workflow state is operational memory, not a substitute for project truth. Source files, the running app, browser evidence, tests, and Synapse Quality OS remain authoritative.

### Benchmark invocation

Use `scripts/benchmark_matrix.py` to generate a Synapse benchmark-run payload for baseline versus UI Forge. It keeps the benchmark task identical while declaring separate workflow treatments through `candidate_group_key` and `candidate_instruction_md`. The baseline must not invoke UI Forge; the challenger must use the installed skill and workflow contract.

Do not group same-model workflow variants only by runtime/model: Synapse benchmark candidates must retain explicit workflow candidate keys. Keep `TASK.md` identical and record the treatment separately in `PROMPT.md`/attempt metadata.

## Required outputs for substantial work

Maintain or report:
- UI Forge brief
- chosen design direction
- token/component changes
- implementation slices completed
- desktop/mobile browser evidence
- quality scores and blockers
- unresolved risks
- reusable patterns worth persisting

## Definition of done

Do not claim a UI is finished merely because the code compiles.

Finished means the requested experience is implemented, visually coherent, responsive, accessible enough for the product's critical path, functionally correct, browser-verified, original to the product, and above the UI Forge evidence gate.

## Precision tooling and benchmark

For fine-grained React/Vite edits, prefer the development-only source-tag path documented in `references/source-tagging.md`. `scripts/babel_source_tags.mjs` adds project-relative `data-ui-forge-source` and deterministic `data-ui-forge-id` attributes to intrinsic JSX during development. Capture/select the rendered element with `scripts/dom_probe.js` or `scripts/visual_edit_bridge.js`, then use `scripts/source_locator.py` to resolve the owning source. For exact source-tag targets and safe static text/class/allowlisted-string-attribute changes, `scripts/direct_ast_edit.mjs` can patch only the validated AST byte range and reparse the result without reformatting surrounding source. It must fail closed on dynamic/mixed JSX. Fall back to the main coding worker or semantic DOM matching when direct editing is unsafe or source tags are unavailable. Never ship local absolute paths in production markup.

For design-system consistency, use `scripts/design_audit.py` as a heuristic signal, not an unquestionable judge. Preserve intentional exceptions. Re-run after structural cleanup.

After browser proof, score evidence with `scripts/ui_forge.py`. If the score or structural checks still need attention, feed the score report plus optional design audit to `scripts/repair_plan.py`. The planner must prioritize critical/runtime/browser failures and structural drift over cosmetic polish, and it must stop recommending mandatory work once the gate and stop rule are satisfied.

For claims that UI Forge improves model performance, use the bundled `ui-forge-v1` benchmark and `references/benchmark-contract.md`. Compare the same model/version, tools, machine, starting fixture, prompt, and time budget with and without UI Forge. Keep failed attempts in the denominator. Do not infer Lovable parity or superiority from a different execution environment; report measured UI Forge deltas directly.

## Evidence-based model routing

UI Forge may use multiple high-powered models, but model choice must become evidence-based rather than brand-based. Store comparable per-role results in the scorecard shape shown by `references/model-scorecard.example.json`, then use `scripts/route_model.py` with live Synapse runtime availability.

Supported routing roles are visual direction, implementation, repair, correctness review, UX review, and accessibility review. A runtime/model is eligible only after the configured minimum number of comparable benchmark runs for that role. If there is not enough evidence, the router returns `insufficient_evidence`; keep the current competent worker or run the benchmark rather than inventing a ranking. Runtime quota/cooldown state always overrides a historical benchmark win.

Prefer quality routing for normal product work. Speed routing is allowed for bounded low-risk work only when absolute quality/pass-rate evidence remains acceptable. Preserve the full project brief, current screenshots, failures, and attempted approaches whenever switching workers so model routing does not erase context.

## Interaction State Lab

Base-state styling and interaction-state styling are separate source owners. UI Forge base CSS resolution intentionally ignores pseudo selectors; a normal spacing/color/layout edit must never silently land in `:hover`, `:focus`, or another state rule.

For supported states (`hover`, `focus`, `focus-visible`, `active`, `disabled`, `checked`), pass `state` with a `style_props` preview. The temporary browser preview is explicitly a **simulated inline state design preview**: use it to judge the treatment, then revert it. `styleCommitSpec()` carries the requested state to `scripts/css_style_editor.mjs`, which automatically resolves only a rule with exactly that pseudo-state. Combined/structural pseudo selectors require explicit file + selector or the main coding path.

After commit, exercise the **real** browser state before declaring success: hover with the pointer, keyboard-focus the element, verify a genuinely disabled control, check a checkbox/radio, or hold active state as appropriate. Verify the committed computed style, move out of the state and recheck base styling, preserve source identity, and keep desktop/mobile/console proof clean. See `references/interaction-states.md`.

## Theme Capsules

When a project has a coherent semantic CSS token system worth reusing, capture it with `scripts/theme_capsule.mjs extract <project-root> <output.json> --name <name>`. The capsule records root-level CSS custom properties plus stylesheet/selector/line provenance and categorizes them into color, typography, spacing, radius, shadow, motion, and other groups. Conflicting root definitions block extraction rather than being silently reconciled.

Before applying a capsule elsewhere, validate it and run `theme_capsule.mjs apply <target-project> <theme.json> --dry-run`. The apply path updates only matching semantic custom properties that already exist in the target; it does not globally replace hex values or rewrite component CSS. Missing or ambiguous target tokens block application by default. `--allow-partial` is only for an intentionally reviewed subset, never a compatibility bypass. Multi-file writes are atomic and rollback-safe.

Use Theme Capsules to preserve brand/design language across related apps, seed isolated UI Forge drafts, and give AI workers reusable machine-readable design context. Do not assume token equality means visual correctness: rerender the target, verify desktop/mobile, inspect contrast/accessibility, and rerun design-system drift checks. See `references/theme-capsules.md`.



## Generated and imported Asset Slots

When an interface needs a generated or imported raster image, keep generation and source placement as separate proof stages. Use Synapse Image Studio or another authorized image source when appropriate, then stage the resulting local PNG/JPEG/WebP with `scripts/asset_slot.mjs`. Preview the staged `/ui-forge-assets/` URL on the real selected `<img>` using `scripts/asset_preview_bridge.js`; require successful decode and inspect geometry before accepting it.

Revert the browser preview before mutation. Dry-run and then commit only when the selected element has exact `data-ui-forge-source` ownership and points to an intrinsic `<img>` with a static string `src`. The source edit updates the project-owned image URL and meaningful alt text, reparses JSX, preserves a provenance receipt, then requires HMR/rerender plus desktop/mobile/console proof. Dynamic `src`, non-image targets, SVG/active content, invalid image bytes, receipt/hash mismatch, and path escapes fail closed. See `references/asset-slots.md`.

## Executable State Matrix

For substantial data-driven or stateful UI, turn relevant loading, empty, error, success, disabled, and recovery states into an executable matrix with `scripts/state_matrix_runner.mjs`; see `references/state-matrix.md`. Run every required state in fresh browser contexts at representative desktop/mobile viewports. Use deterministic route mocks and response sequences where needed to prove loading, failure, retry, and recovery.

A state passes only when its user-visible assertions pass, objective browser blockers are absent, and no unexpected console/page errors occur. A deliberately mocked >=400 response may create the browser's normal failed-resource console entry; the runner records that separately as expected failure evidence. Missing required states fail validation. Do not delete a required state or weaken assertions to make a broken UI pass.

## Isolated draft workspaces

For exploratory redesigns, competing visual directions, or broad frontend changes, use `scripts/draft_workspace.py` before editing the live project. Each draft keeps an immutable base snapshot plus an isolated workspace under `.synapse/ui-forge/drafts/`. Run the UI Forge conductor against the returned workspace, preview and browser-test the draft, then inspect `status`/`diff` before acceptance.

Acceptance is path-scoped and conflict-aware: if a live path touched by the draft changed after draft creation, accept must fail closed instead of overwriting newer work. Non-overlapping drafts may still merge independently. `.env*`, backend/API/server/function paths, migrations, database/schema paths, Prisma, Supabase, and similar changes are risk-gated by default. Never use `--allow-risky` merely to bypass the frontend safety boundary. See `references/draft-workspaces.md`.

Use drafts to compare running alternatives, not to multiply nearly identical variants. Keep the live application unchanged until the chosen draft satisfies browser proof and the UI Forge quality gate.

## Runtime ownership tracing

A DOM declaration is not always the source of the rendered state. Static HTML/JSX may be overwritten after load by application state, effects, event handlers, timers, or direct DOM mutation. If a seemingly correct static edit does not appear in the running app, do not keep editing the declaration blindly.

Run `scripts/runtime_owner_locator.py` with the rendered element probe. It links element IDs/selectors to JavaScript/TypeScript aliases and ranks `.textContent`, `.innerText`, `.innerHTML`, `className`, `setAttribute`, style, and value mutations, with rendered-text evidence when available. Prefer candidates marked `likely_runtime_writer=true`.

The intended precision order is: exact compile-time source tag -> safe direct static edit when ownership is truly static -> rerender -> if the state is overwritten, runtime-owner trace -> smallest owning runtime-state edit -> browser proof. The static source locator remains useful for declarations; the runtime-owner locator answers a different question: what code is actually writing the visible state?
