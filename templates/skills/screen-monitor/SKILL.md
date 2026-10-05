---
name: screen-monitor
description: Read-only Synapse visual screen monitoring and human-view auditing through Reflex. Use when the user asks Synapse to monitor, watch, inspect, observe, visually verify, or human-audit the desktop, an app window, a browser window, a game, or a UI as a real user would see it. Establish a visual baseline first, observe meaningful changes, and record evidence or project findings without taking desktop input control.
---

# Screen Monitor

Screen Monitor is Synapse's read-only eyes-on-the-real-screen workflow.

It covers the gap between source or DOM correctness and what a human actually sees. A passing test or DOM snapshot is not proof that the visible desktop experience looks correct. Screen Monitor uses the real visible desktop through Reflex, compares meaningful visual states, and turns observations into evidence-backed project decisions.

## Core rule

Observe first, remain read-only, and verify visual claims with real screen evidence.

## Use it for

- watching a real app while another process or AI is changing it
- checking whether an app actually launched and rendered correctly
- human-view UI audits of desktop, browser, or game experiences
- verifying dialogs, menus, transitions, loading states, errors, and responsive behavior
- spotting clipping, overlap, off-screen content, broken layout, unreadable text, stale loading screens, duplicate windows, crash dialogs, and obvious visual regressions
- checking what the user sees after a build, restart, or deploy
- observing long-running tasks without repeatedly asking the user what is on screen
- turning a visible issue into a Synapse backlog or project-context note with concrete evidence

Keep the workflow focused on the target app or window and avoid capturing unrelated sensitive content.

## Preferred Synapse / Reflex path

1. Call `synapse_get_context` and, for project work, `synapse_get_project_ai_context`.
2. Call `synapse_list_mcp_tools(server="reflex")` when exact downstream tool names or schemas are not already known.
3. Use `synapse_call_mcp_tool` for read-only Reflex calls.

Minimum useful Reflex tools:

- `take_screenshot`
- `screenshot_window`
- `get_active_window` or `get_focused_app_state`
- `list_windows_detailed`
- `get_screen_size`
- `get_window_rect`
- `window_screenshot_grid`

Do not use mouse, keyboard, window mutation, process termination, file mutation, or other control tools as part of this workflow.

Read `references/workflow-contract.json` before building automation around Screen Monitor.

## Screen Monitor loop

### 1. Orient

For project-scoped work:

- read the Synapse project context
- identify the project, app, or process being observed
- note the user's current goal
- avoid touching unrelated work

For general desktop observation, identify the active window and visible monitor before assuming what should be watched.

### 2. Scope the observation target

Prefer the narrowest target that answers the question:

- **window**: best for one app; use `screenshot_window`
- **monitor**: best when cross-app behavior matters; use `take_screenshot`
- **window grid**: useful when comparing multiple visible apps or windows

Record the target by stable handle or PID when possible rather than only title text.

### 3. Capture a baseline

Before judging changes, capture:

- screenshot
- active or focused window metadata
- window rectangle and state when relevant
- timestamp in the work log or project note

Describe only what is visibly supported. Do not infer hidden application state from pixels alone.

### 4. Observe meaningful changes

A monitoring pass should answer:

- What changed since the last meaningful frame?
- Is the target still visible and responsive?
- Did a new dialog, error, or loading state appear?
- Did the intended external action visibly take effect?
- Is the visual state better, worse, unchanged, or ambiguous?

Do not create a noisy frame-by-frame diary. Keep frames when they establish a baseline, show a material transition, demonstrate a bug, prove a fix, or capture a terminal or error state.

Suggested active-observation cadence is 1-3 seconds for short UI transitions and 5-15 seconds for slower tasks. Prefer event-driven checks, such as process, window, or repo state changes, over indefinite rapid screenshots.

### 5. Classify the observation

Use one of:

- `healthy` — visible state matches the intended experience
- `changed` — meaningful visible change, not inherently a problem
- `needs_attention` — degraded or confusing UI, or unexpected state
- `blocked` — cannot continue because another dependency is missing
- `error` — crash, fatal dialog, failed launch, or clearly broken state
- `ambiguous` — visual evidence is insufficient; gather another source before concluding

### 6. Verify like a human

For product or UI work, inspect at least:

- first impression and hierarchy
- whether the primary action is obvious
- text clipping, truncation, or overlap
- horizontal and vertical overflow
- dialogs and overlays
- loading, empty, error, and success states when reachable through external automation
- visible disabled, focus, or selected state where relevant
- obvious touch-target or spacing problems
- desktop and mobile viewport when browser-based mobile support matters
- whether navigation or action feedback is perceptible

Visual inspection does not replace semantic accessibility checks. Pair with Playwright or browser audit when accessibility, labels, keyboard order, or DOM semantics matter.

Read `references/visual-audit-rubric.md` for severity and evidence rules.

### 7. Record useful evidence

When a finding matters to a Synapse project, capture a concise project note or backlog item containing:

- observed screen, window, or state
- visible symptom
- event immediately before it
- expected visible result
- actual visible result
- severity
- timestamp or evidence-frame reference when available
- whether the issue was later fixed and re-verified

Do not dump raw screenshots or unrelated desktop content into project memory.

### 8. Stop conditions

Stop or hand off when:

- the requested visible state is verified
- the target disappears and cannot be safely recovered read-only
- repeated observations show no meaningful change and another evidence source is needed
- the requested conclusion cannot be supported from visual evidence alone

## Evidence standard

Do not claim `works` because the code compiled. For a visual claim, collect visual proof from the actual target state.

Do not claim `user experience is good` from one screenshot. Exercise the relevant transition or state through the appropriate external test workflow when practical.

Do not claim `fixed` until a post-change frame shows the visible defect is gone and no obvious replacement defect appeared.

## Pairing with other Synapse workflows

- **UI Forge**: source and design repair; Screen Monitor provides real-screen evidence before and after.
- **UI Demo Studio**: recorded guided demonstrations; Screen Monitor is lighter-weight observation and verification.
- **App Doctor / Repair Arena**: technical diagnosis and repair planning; Screen Monitor adds the visible symptom and post-fix proof.
- **Autonomous Dev Loop**: use Screen Monitor as the visual verification gate for iterations that change UI or desktop behavior.
- **Game Dev Studio**: use for real rendered-game or window observation when visual gameplay proof is required.

## Deliverable

A good Screen Monitor run leaves behind:

1. a clear target and baseline
2. only meaningful visual observations
3. evidence-backed findings or verified success
4. a concise durable project handoff when the observation changes project work
