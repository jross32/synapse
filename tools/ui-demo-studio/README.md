# UI Demo Studio

Synapse-native visual QA and product-experience benchmark tool for evidence-backed UI/UX improvement loops.

## What it does

A single run can:

1. resolve a Synapse project id or HTTP(S) URL;
2. record a safe UI walkthrough with Playwright;
3. capture screenshots and a Playwright trace;
4. re-open visited scenes at desktop and mobile viewports;
5. benchmark UI, UX, performance, accessibility, and reliability;
6. emit a machine-readable scorecard, a human report, and an AI remediation brief;
7. compare against the newest **compatible** scored run: same scorecard methodology, target, journey mode/steps, viewport, and duration.

The intended proof loop is:

**build -> record + benchmark -> inspect evidence -> fix highest-impact issues -> re-benchmark -> inspect new evidence -> compare**

Do not claim a UI/UX improvement from code changes alone. A claim needs new measured evidence and, where visual judgment matters, a new visual review of the resulting screenshots/video.

## Scores

All scores are 0-100.

- **UI** - visual integrity, readability/contrast, component consistency, responsive adaptation, and information hierarchy.
- **UX** - usable interaction completeness, task/journey success, response feedback, navigation/reversibility, and dead-end resistance.
- **Performance** - LCP, INP or a documented response proxy, CLS, TTFB, and long-task pressure.
- **Accessibility** - names/labels, contrast, target size, dialog dismissal, and semantic structure.
- **Reliability** - runtime errors, console errors, failed requests, and HTTP 4xx/5xx behavior.

The overall score is weighted, but severe experience failures impose hard caps so cosmetic polish cannot hide a broken journey.

## Hard gates

Hard gates are **blockers**, not ordinary low-scoring suggestions. Resolve them before treating the aggregate score as evidence of readiness.

- No usable controls on an app opening view: **UX = 0** and **overall <= 39 (F)**.
- Trapped visible dialog/modal without Close, Cancel, Done, Back, Return, or another detectable exit: **UX <= 59** and **overall <= 59 (F)**.
- Fewer than half of a guided multi-step journey succeeds: **UX <= 49** and **overall <= 59 (F)**.
- Serious mobile horizontal overflow: **UI <= 64** and **overall <= 69**.
- Clear Synapse project-identity mismatch: assessment is invalid, Reliability is capped, and **overall <= 19 (F)**.

A control is not counted as usable when it is disabled, `aria-disabled="true"`, inert, or inside an inert subtree.

The generated human report and AI remediation brief explain both the gate effect and why that gate matters to the product journey.

## Evidence labels

UI Demo Studio separates deterministic evidence from subjective review instead of mixing them into one confident-looking score.

- **Measured / derived** - browser-observed evidence transformed by the deterministic benchmark rubric.
- **Measured / proxy** - browser evidence exists, but a documented proxy/fallback is used instead of the preferred direct signal.
- **Derived / fallback** - the preferred observation was unavailable; interpret the score with lower confidence.
- **UNMEASURED visual review** - requires a human or vision-capable AI to inspect the captured screenshots/video. It must not be described as telemetry or a deterministic benchmark result.

Examples of deliberately unmeasured visual-review questions include hierarchy quality, spacing/alignment taste, typography/density, brand polish, perceived affordance, first-time-user clarity, motion quality, and empty/loading/error-state presentation.

## Assessment validity

When a Synapse project id is used, the benchmark attempts to verify that the page being scored identifies as the expected project. If the resolved URL clearly identifies as another registered Synapse project, the assessment is marked invalid and hard-capped.

This prevents stale or reused local ports from producing a confident score for the wrong application.

## Benchmark anchors

The deterministic benchmark uses current web-product thresholds as anchors, including:

- LCP good at approximately <= 2.5 s.
- INP good at approximately <= 200 ms.
- CLS good at approximately <= 0.1.
- Normal text contrast target >= 4.5:1; large text >= 3:1.
- WCAG 2.2 target-size baseline >= 24x24 CSS px, with 44x44 as an enhanced usability target.

These are laboratory heuristics. They are not a replacement for field telemetry, assistive-technology testing, user research, or a formal accessibility conformance audit.

## Inputs

- `target`: Synapse project id or HTTP(S) URL.
- `duration`: target demo length, 8-60 seconds.
- `journey`: optional labels separated by `>`, commas, or new lines.
- `viewport`: recording viewport, default `1280x720`.
- `headless`: unattended mode by default.

## Actions

- **Record + benchmark** - produce a new video, scorecard, human report, and AI remediation brief.
- **Check latest** - read the current/latest run status.
- **Re-benchmark latest** - rescore the last recorded journey without recording another video.
- **Open latest report** - open the final human-readable report when benchmarking completes.

## Output contract

Each completed run lives under `data/ui-demo-studio/<run-id>/` and can contain:

- `demo.webm` or `demo.mp4`
- `trace.zip`
- `scene-*.png`
- `ux-audit.json`
- `benchmark-raw.json`
- `scorecard.json`
- `ai-remediation.md`
- `report.md`
- `report.html`
- `status.json`

### Human reports

`report.html` is the decision-oriented visual report. After benchmark completion it includes:

- overall score and per-area scores;
- overall and per-area deltas versus the previous comparable run when available;
- active hard gates and their product impact;
- ordered measured remediation priorities;
- evidence-type labels for benchmark rows;
- duration evidence with explicit timing semantics;
- scene-coverage evidence;
- a separate **UNMEASURED** visual-review checklist;
- captured scene screenshots and the next proof-run checklist.

`report.md` is regenerated at benchmark completion from the same score/evidence inputs so the Markdown and HTML reports do not disagree about the final benchmark. During the recorder-only stage, a preliminary recorder report may exist before the benchmark replaces it.

### AI remediation brief

`ai-remediation.md` is optimized for an AI-driven fix loop. It intentionally orders work as:

1. hard-gate blockers;
2. lowest-scoring measured benchmark items;
3. explicit visual-review work that remains unmeasured until inspected;
4. a required repeat run using the same target/journey for proof.

The brief must not turn visual taste into fake telemetry. Visual judgments should cite the actual video/screenshot evidence.

### Mobile navigation evidence

Scorecard 3.3 compares the opening desktop and mobile benchmark surfaces. When desktop exposes visible navigation links, mobile must expose either visible navigation links or a visible menu/navigation control. If both disappear, `ui.mobile_navigation` scores 0 and contributes to responsive adaptation.

This deliberately allows common responsive patterns such as collapsing several desktop links into one accessible hamburger/menu button. It does not require desktop and mobile navigation to look the same.

### Keyboard evidence

Scorecard 3.3 adds a bounded, non-destructive Chromium keyboard probe on the opening benchmark route. It samples sequential Tab navigation and reports:

- focusable controls discovered and sampled controls reached;
- whether sampled keyboard focus has a detectable UA/authored outline or shadow indicator;
- whether sampled focused controls are at least partially unobscured in the viewport;
- when a visible modal exists, whether Tab focus remains contained and whether Escape dismisses it.

These are browser-observed heuristics, not a formal WCAG conformance certificate. The focus indicator check intentionally stays conservative: it recognizes deterministic outline/shadow evidence and does not invent a pass for visual changes it cannot measure reliably. A keyboard-probe failure is reported as **not measured** rather than scored as a product failure.

`a11y.keyboard_focus` contributes to Accessibility. `ux.dialog_keyboard` contributes to modal reversibility only when a visible dialog exists; otherwise it is **not applicable**. The existing `ux.trapped_dialog` hard gate remains independent and still requires an actual missing visible exit path.

### Duration semantics

Several timing values can coexist and they mean different things:

- `duration_seconds` / `target_duration_seconds` - configured target duration, not an observation.
- `recording_elapsed_seconds` - measured recorder window from timed recording start to stop.
- `video_duration_seconds` - measured encoded media duration from video metadata after recording.
- `video_duration_delta_seconds` - encoded video duration minus configured target duration.
- `video_finalize_seconds` - post-record finalization overhead; it is **not** part of the encoded video duration.
- `recording_mode` - `screencast` when the explicit Playwright start/stop lifecycle is available, otherwise the legacy `recordVideo` fallback.

The human report labels these separately so finalization time is never misreported as demo length.

### Comparable-run semantics

Scorecard **3.3** fingerprints the scorecard methodology, target, journey mode and labels, viewport, and configured duration. A before/after delta is emitted only when those fields match. This prevents a short automatic tour, a different task, or an older scoring method from being presented as a valid product improvement.

The recorder prefers Playwright Screencast because it can stop capture explicitly at the recording deadline. Older Playwright builds fall back to context-level `recordVideo`. Acceptance tests use a tighter encoded-duration tolerance for Screencast than for the fallback.

### Scene coverage semantics

A scene is captured evidence, not automatically a successful task step.

The reports show:

- journey mode;
- captured scene count;
- number of distinct URL states represented;
- requested guided-label count when applicable;
- recorded missing/failed journey events.

For task completion, use the measured **Task / journey success** benchmark. Do not infer 100% journey success from screenshot count alone.

### `scorecard.json`

Stable top-level fields include:

- `version`
- `experience_mode`
- `validity`
- `overall_score`
- `grade`
- `scores.ui`
- `scores.ux`
- `scores.performance`
- `scores.accessibility`
- `scores.reliability`
- `gates[]`
- `metrics.ui[]`
- `metrics.ux[]`
- `metrics.performance[]`
- `metrics.accessibility[]`
- `metrics.reliability[]`
- `raw`

Every metric includes an id, label, score, observed evidence, target, and source.

## Visual review checklist

Before calling a substantial UI change visually complete, inspect the latest video/screenshots and answer each item with evidence:

- [ ] Is the primary job and primary action obvious at first glance?
- [ ] Is spacing/alignment rhythm intentional across dense and sparse regions?
- [ ] Do typography, line length, emphasis, and density support scanning?
- [ ] Does color have a semantic job and feel product-specific rather than generic?
- [ ] Do interactive controls look interactive before hover or experimentation?
- [ ] Can a first-time user understand the next useful action?
- [ ] Do transitions explain state changes without unnecessary delay or distraction?
- [ ] Are empty, loading, error, and success states understandable and recoverable?

These checks are **UNMEASURED** until a reviewer actually inspects the visual evidence.

## Safety

Automatic tours refuse destructive/payment/logout-like actions. The benchmark interaction probe prefers same-origin navigation and may fall back to visible non-destructive, non-submit buttons. Destructive labels are excluded.

Do not weaken these safety restrictions to improve scene count or score.

## Reviewer expectations

A trustworthy improvement claim should answer four questions:

1. **What was broken?** Cite a hard gate, measured benchmark row, or visual-review finding.
2. **What changed?** Name the bounded product/UI fix.
3. **What evidence improved?** Cite the new score delta, timing evidence, scene/task evidence, or visual comparison.
4. **What remains unmeasured or risky?** Keep subjective judgment and missing telemetry explicit.
