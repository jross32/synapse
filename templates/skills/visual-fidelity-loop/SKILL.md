# Visual Fidelity Loop — all Synapse-connected AI workers

Use for any request to replicate an approved screenshot/UI design in a real app,
or to generate premium visual assets when models/providers have different capabilities.

## Target lock

- Identify the actual app and obtain the approved reference image *bytes* in that
  project's folder, with sha256 and target viewport/engine. A screenshot shown in
  ChatGPT may NOT be accessible by Synapse. A verbal spec is a fallback, not proof
  that the original image was transferred.
- Document exact colors, text, fonts, spacing, hierarchy, imagery, shapes, crops,
  breakpoints, hover/focus/disabled/loading/error states, and expected behaviors.
- Read the existing UI Forge Visual Target Contract and Asset-Led Product Workflow.
  Preserve approved high-fidelity asset classes; never substitute a CSS placeholder
  and call it visually equivalent.

## Provider routing: use real capabilities

- Claude, when authenticated and available: reason about the design, read images,
  create/revise HTML/CSS/React/SVG assets and renderer prompts, identify mismatches.
  Claude does NOT natively create raster photos/illustrations. Do not treat SVG code
  as a raster image provider response.
- Synapse Image Studio: produce/edit raster artwork only with an actually configured,
  healthy image generation provider (currently native OpenAI raster support). Never
  assume ChatGPT login supplies an OpenAI API key.
- Blender Studio: produce 3D/stylized scene assets, icons, characters, phone hardware
  renders, and perspective compositions with deterministic geometry/camera.
- Existing/licensed/project assets: reuse when they match; keep provenance.
- Block an unavailable required asset; do not quietly lower the visual standard.

## Real implementation and audit

1. Create an asset manifest and source-controlled UI tokens/components.
2. Build the app using original approved art and usable buttons/flows.
3. Capture the real app at matched viewport/engine, with stabilized data and fonts.
4. From Synapse repo, run:
       .\.venv\Scripts\python.exe tools\ui_lab_reference_compare.py REF.png ACTUAL.png --output artifacts\visual-qa\run-001
5. Examine report.json plus difference.png and overlay.png. FAIL means iterate.
   BLOCKED means missing/mismatched evidence; neither means release ready.
6. Run UI Lab interaction, mobile/desktop, keyboard, errors, overflow, a11y, and
   Quality OS gates separately. Pixel matching is *not* usability proof.
7. Record hashes, screenshots, asset provider, active blockers, tests, Git state,
   and deployed application verification. Never claim 1:1 visual match without
   a grounded passing threshold agreed for the target.

## Durable reference

See docs/CLAUDE_ASSISTED_VISUAL_FIDELITY.md in the Synapse repo for the
file handoff and threshold contract. If Claude OAuth is expired, route
code/vector work to another available model and report Claude blocked.
Do not ask for or expose private auth tokens to put an image on a public site.
