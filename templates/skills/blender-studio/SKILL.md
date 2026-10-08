---
name: blender-studio
description: Create, inspect, modify, validate, render, and export Blender assets/scenes through Synapse. Use for Blender, 3D assets, meshes, materials, textures, procedural geometry, rigs, animation, lighting, cameras, renders, conversion, game/app-ready exports, device mockups, and reusable UI/marketing render assets.
---

# Synapse Blender Studio

Treat Blender as a first-class AI creation environment, not a GUI that must be blindly clicked.

## Operating contract

1. Inspect before mutation: file/save state, datablocks, objects, linked libraries, missing files, engine, camera/light state.
2. Prefer semantic Blender MCP tools. Use reproducible `bpy` code as the universal escape hatch.
3. Prefer background/scripted jobs over desktop clicking; use Reflex for GUI-only work or human-view proof.
4. Never execute untrusted scripts embedded in downloaded .blend files.
5. Save editable source as .blend for meaningful generated work.
6. Retain provenance and intended downstream use for generated/imported assets.
7. Validate after edits; reopen important .blend outputs when practical.
8. Produce a render/thumbnail and inspect it for visual work.
9. Verify exports exist and, where practical, re-import/validate downstream.
10. Keep capability claims evidence-scoped.
11. Preserve concurrent work.
12. Optimize for the target medium.

## Creation loop

`target + constraints -> inspect -> choose semantic MCP/bpy -> create -> save .blend -> structural validation -> render -> visual review -> export -> downstream verification -> provenance receipt`

## UI / marketing render lane

Blender is not only for games. Use it when web/app visual targets need deterministic, reusable rendered assets such as:

- phone/laptop/tablet device frames
- perspective-correct device mockups
- abstract 3D hero objects
- stylized silhouette/character scenes
- product pedestals/rooms/environments
- glass/metal/plastic branded forms
- icon families with shared material/lighting
- reusable camera/lighting setups across multiple landing sections
- transparent PNG hero/card assets
- turntables or short loops for motion sections

For these tasks:

1. Read UI Forge's Visual Target Contract / asset manifest.
2. Set the camera to the final composition/aspect before detailed modeling.
3. Build safe-area guides for text/UI overlay zones.
4. Prefer reusable collections/materials and named cameras.
5. Pack or explicitly reference required textures.
6. Render at least 2x intended CSS display resolution when practical.
7. Use transparent film/background for composited assets; use a scene/world background when the entire environment is the asset.
8. Keep the .blend source beside provenance notes so future AIs can reframe/re-light rather than rebuild.
9. If showing a real product UI inside a device, capture the actual running UI separately and map/composite it; do not invent screenshots.
10. Verify the exported render in the real browser composition.

### Choosing Blender vs Image Studio

Choose Blender when geometry, camera, perspective, repeatability, transparent output, material consistency, or reusable source control matter.

Choose Image Studio when photoreal humans, organic environments, expressive illustrative scenes, or reference-guided 2D transformation matters more.

They can be combined: Image Studio can create background/texture material while Blender supplies device geometry/camera; or Blender can render a device frame for compositing with a generated environment.

If neither can meet a locked target, record a blocker rather than downgrading to a crude CSS stand-in.

## Capability lanes

Track evidence separately for mesh/modeling; modifiers; curves/text; UVs; PBR materials; image textures; Geometry Nodes; armatures/skinning; keyframe/action/NLA; cameras; lights/worlds; Eevee/Cycles rendering; compositing; import/conversion; glTF/GLB; FBX/OBJ/USD; game optimization; UI/marketing renders; downstream app integration.

Read `references/capability-matrix.md`, `references/engine-handoffs.md`, and `references/tool-routing.md` before broad capability claims. Use `scripts/blender_studio.py matrix` and `probe` for machine-readable/local proof.

## Downstream games/apps

For game work, coordinate with WhatIf Game Dev Studio. Prefer GLB/glTF for portable PBR when supported.

For web/app marketing renders, normally export PNG (alpha when needed) or a web-optimized derivative created from a verified render. Record source .blend, render path, camera, resolution, color-management assumptions, provenance, and browser integration evidence.
