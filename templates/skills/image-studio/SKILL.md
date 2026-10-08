# Synapse Image Studio

Use this skill whenever a project needs an image to be generated, edited, composited, restyled, cleaned up, or turned into a production-ready visual asset.

## Goal

Make image creation a native production step for any AI connected to Synapse. The AI should infer provider settings, save the output inside the relevant project, preserve provenance, and integrate the asset through the project's UI/asset workflow.

For reference-driven UI work, coordinate with UI Forge's Visual Target Contract and Asset-Led Product Workflow.

## Core routing

1. Call `synapse_image_generation_status` when provider readiness is unknown.
2. Discover existing project images before generating duplicates.
3. New image from text -> `synapse_generate_image`.
4. Reference-guided edit -> import/make the reference project-local, then `synapse_edit_image`.
5. Audit provenance/integrity for production use.
6. Register the final output in the project's asset manifest / UI Forge Asset Slot.

## UI production lane

Prefer Image Studio for:
- detailed hero illustrations
- human/persona portraits
- emotionally expressive scenes
- environments/background scenes
- photoreal products
- rich 2D card art
- reference-guided image transformations
- character/style-consistent image families

Do **not** use CSS primitives as a final substitute when one of these classes is explicitly required by the visual target.

If provider generation is unavailable:
- keep the planned asset slot unresolved
- consider Blender Studio only when the target can honestly be satisfied as a deterministic 3D/stylized/device/environment render
- otherwise mark the visual target blocked
- never report a generated asset that does not exist

## Quality defaults

- `max`: people/products/environments, hero art, marketing imagery, precision edits, identity/object consistency, or explicit highest-quality requests
- `xhigh`: strong production assets
- `high`: polished everyday assets
- `medium`: drafts/layout exploration
- `low`: speed/cost deliberately prioritized
- `auto`: no useful quality signal

Use a concrete production brief: subject, environment, framing/camera, lighting, materials/skin/fabric, pose/action, depth, color/brand constraints, negative constraints, intended crop, and what must remain consistent.

## Reference lock

For a reference image, explicitly classify:
- what must be preserved
- what may change
- target crop/aspect
- identity/style continuity requirements
- forbidden changes

After generation, inspect the actual output in context. A provider success response alone is not a visual-quality pass.

## Output and provenance

Save inside the selected Synapse project, normally under:
- `public/images/ai/...`
- `assets/generated/...`
- `art/generated/...`

Use descriptive, versioned filenames. Do not overwrite an approved asset unless replacement is intentional.

Retain:
- provider/model/quality metadata when available
- prompt/edit provenance
- source/reference ids
- file hash/integrity record
- intended asset-slot id
- approval/supersession state

## Iteration

Generate one strong candidate first. Prefer targeted edits when preserving composition/identity matters. Regenerate when the entire direction is wrong.

For UI work:
`asset -> browser integration -> screenshot -> target comparison -> asset edit/regenerate -> recapture`

Do not generate many expensive near-duplicates without an explicit comparison need.

## Completion

Do not claim image completion until:
- a real asset was returned
- it is project-scoped
- provenance is recorded
- it decodes/renders in the real product when integration is part of the task
- its crop/composition is verified at intended breakpoints
- it satisfies the Visual Target Contract asset class when one exists
