# Claude-assisted visual fidelity: shared Synapse workflow

Scope: Every Synapse project with an approved mockup, visual target contract, or screenshot reference.

## Model and renderer responsibilities

1. **ChatGPT and owner:** lock the approved reference, layout, typography, imagery, mobile/desktop composition, and interaction states. Save actual approved screenshot bytes into the project; do not assume a chat image or assistant sandbox path is available on the Windows host. Mark reference_missing if unavailable.
2. **Claude (only when authenticated and available):** inspect the same target and codebase; produce frontend components, CSS, SVG/vector artwork, interaction states, detailed raster-generation prompts, and targeted screenshot repair briefs. Claude does not directly generate raster photos or illustrations. An SVG or code artifact is valid only once saved and rendered.
3. **Raster imagery:** use Synapse Image Studio's configured image provider (currently native OpenAI support), or a legitimately licensed imported asset. A ChatGPT subscription does not grant an OpenAI API key.
4. **3D art:** use Blender Studio for deterministic scene, stylized characters, devices, mockups, and perspective-critical artwork.
5. **UI Forge:** integrate actual asset slots, components and tokens, run the app, and preserve functionality. No silently downgraded art.
6. **UI Lab / Quality OS:** compare real running app screenshots, test states and interactions, and preserve passing evidence.

## Screenshot comparison (implemented)

After putting approved and real browser captures at exactly the same viewport size, run from the Synapse repository:

    .\.venv\Scripts\python.exe tools\ui_lab_reference_compare.py path\approved.png path\actual.png --output artifacts\visual-qa\run-001

Outputs: report.json, overlay.png and difference.png.

- PASS: both default thresholds are met: at most 10% of pixels exceed 24/255 maximum per-channel difference, and mean RGB absolute error at most 15/255.
- FAIL: measurable image difference exceeds a threshold.
- BLOCKED: viewport dimensions conflict, all pixels are ignored, or ignore mask dimensions mismatch. Images are never silently resized.
- Optionally pass --ignore-mask mask.png, where white pixels exclude a sensitive/dynamic region and black pixels remain comparable. Do not mask functional UI defects.
- Thresholds are initial heuristics only, not pixel-perfect visual identity, accessibility, browser functionality, or quality certification. Keep independent interaction/a11y gates.
- Match same browser engine, viewport, font loading, fixed time/data, app state and image assets before interpreting scores.

## Failover and integrity

If Claude OAuth is expired or runtime is quota-blocked, route vector/code work to an actually usable model; explicitly record unavailable Claude. If raster generation is not configured, use Blender only when the required asset is genuinely 3D and otherwise block the asset. Use authenticated project-local image imports with real PNG/JPEG/WebP bytes, not invented Synapse access to ChatGPT sandbox files.

Preserve asset source/provenance, provider/model, reference source, prompt, sha256, visual target, per-breakpoint screenshots, defect report, pass/fail evidence and exact reproduction command. Treat all mismatches, broken controls, bad mobile overflow, and open blocking Quality OS gates as release blockers.

Never destroy parallel workers' uncommitted edits or report a provider or screenshot gate as passing when not observed.
