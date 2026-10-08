# Visual Target Contract

A **Visual Target Contract (VTC)** turns a user-approved screenshot, mockup, collage, or design direction into a fail-closed implementation target. It exists because functional browser proof alone cannot establish visual fidelity or product completeness.

Use a VTC whenever the user supplies or approves a visual reference and expects the implementation to materially resemble it.

## Core rule

A locked visual target is not "inspiration." It is an acceptance artifact.

The implementation may remain original and product-specific, but every material element of the target must be classified before coding:

- **match** — the product should reproduce the same role/hierarchy/experience.
- **adapt** — preserve the design principle while changing content/brand/interaction.
- **omit with reason** — intentionally excluded because it is unsafe, unsupported, dishonest, or outside scope.
- **blocked** — required but cannot yet be produced because a provider/tool/asset is unavailable.

Anything not classified is unresolved.

## Required contract fields

Create a JSON contract using `references/visual-target-contract.example.json` as the shape.

At minimum record:

- project id/name
- reference files or design-reference ids
- target surfaces/routes
- viewport(s)
- required sections
- required asset slots
- forbidden prototype signals
- minimum visual/completeness score
- explicit blockers
- approval timestamp or provenance note

### Required asset slots

Classify each visible asset need before implementation:

- `css-primitive` — line, shape, simple icon, gradient, divider.
- `vector-graphic` — logo/icon/diagram that needs deliberate vector art.
- `production-illustration` — detailed hero/card illustration.
- `photoreal-image` — people/product/environment requiring image generation or licensed source.
- `3d-render` — deterministic object/device/environment or stylized scene suited to Blender.
- `device-mockup` — phone/laptop/tablet frame with real product screenshot.
- `motion-asset` — animation/video/render sequence.

A high-fidelity slot may **not** be silently replaced by `css-primitive`. If the required producer is unavailable, mark the slot blocked and fail the fidelity gate.

## Evidence contract

After implementation, produce evidence JSON containing, per surface:

- actual screenshot path
- browser URL
- viewport
- required sections found
- resolved asset slots and provenance/source type
- placeholder/prototype signals still visible
- visual reviewer score (when human/model visual review is used)
- unresolved differences
- accessibility/runtime proof references

The deterministic gate does not pretend to understand aesthetics from pixels. It verifies that the required evidence exists and that the implementation did not silently omit, downgrade, or leave placeholder surfaces.

Pair this gate with actual screenshot/reference review.

## Fail-closed conditions

A target surface fails when any of these applies:

1. required reference or browser screenshot is missing
2. required section is absent
3. required route/state is unproven
4. required production asset is missing
5. asset was downgraded to a lower-fidelity class without explicit acceptance
6. required surface contains forbidden prototype language such as "coming soon", "next UI slice", "local fallback", or "not connected"
7. a required screen is represented only by placeholder copy
8. minimum visual/completeness score is not met
9. a declared blocker remains unresolved

## Asset production routing

Use the cheapest tool that can honestly meet the target:

1. Existing approved project asset
2. Project-native component/CSS primitive, only if the target truly calls for a primitive
3. Synapse Image Studio for people, environments, illustrative scenes, photoreal assets, or reference-guided image work
4. Synapse Blender Studio for deterministic 3D objects, device mockups, stylized scenes, cameras/lighting, reusable render families, or when 3D source reuse is valuable
5. Imported/licensed asset with provenance
6. Blocked state if none can satisfy the target

Never lower the visual bar merely because a preferred generator is unavailable.

## Repair loop

`lock target -> decompose -> asset plan -> implement -> browser capture -> compare -> gate -> repair -> recapture`

Do not advance to "done" while the VTC report contains unresolved required gaps.
