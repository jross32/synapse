---
name: blender-studio
description: Create, inspect, modify, validate, render, and export Blender assets/scenes through Synapse. Use for Blender, 3D assets, meshes, materials, textures, procedural geometry, rigs, animation, lighting, cameras, renders, conversion, and game/app-ready exports.
---

# Synapse Blender Studio

Treat Blender as a first-class AI creation environment, not a GUI that must be blindly clicked.

## Operating contract

1. Inspect before mutation: file path/save state, datablocks, objects, linked libraries, missing external files, engine, and relevant object details.
2. Prefer semantic Blender MCP tools for inspection/navigation/rendering. Use `execute_blender_code` with `bpy` as the universal creation/edit escape hatch when a dedicated semantic operation does not exist.
3. Prefer reproducible Blender Python/background jobs over desktop clicking. Use Reflex only for genuinely GUI-only work or human-view verification.
4. Never execute untrusted scripts embedded in downloaded `.blend` files. Inspect external assets and provenance first.
5. Save meaningful source work as `.blend`; do not treat an export as the only editable source unless conversion is explicitly the task.
6. For every generated/imported production asset, retain provenance and intended downstream use. Generated assets must be identified as generated/original rather than externally licensed.
7. Validate after meaningful edits. Reopen important `.blend` outputs in background Blender when practical and assert the properties that matter instead of trusting the save call.
8. For visual work, produce a render/thumbnail or viewport evidence and inspect it. Structural tests alone do not prove appearance.
9. Exports are deliverables, not proof. Verify the exported file exists, is non-empty, and where practical re-import it into a clean Blender scene or validate it in the downstream engine.
10. Do not claim a Blender capability is flawless/universal merely because `bpy` exposes it. Use the capability matrix and real benchmark evidence. Unverified categories remain unverified.
11. Preserve concurrent work. Never overwrite unrelated dirty `.blend` or project files; create a separate source/output when ownership is ambiguous.
12. Optimize assets for their target: game assets need sane origins/transforms, naming, material/texture portability, topology/triangle awareness, and explicit scale/unit conventions.

## Creation loop

For substantial work: understand target and constraints -> inspect current scene/project -> choose semantic MCP or scripted lane -> create/edit -> save source -> structural validation -> visual render/inspection -> export if needed -> export/re-import validation -> provenance/receipt -> downstream integration.

## Capability lanes

Track evidence separately for: mesh/modeling; modifiers; curves/text; UVs; PBR materials; image textures; Geometry Nodes; armatures/skinning; keyframe/action/NLA animation; cameras; lights/worlds; Eevee/Cycles rendering; compositing; import/conversion; glTF/GLB export; FBX/OBJ/USD export where supported; game-ready optimization; downstream engine/app import.

Read `references/capability-matrix.md` before making broad capability claims. Read `references/tool-routing.md` for the semantic MCP -> bpy -> background validation -> GUI fallback ladder and timeout/retry rules. Use `scripts/blender_studio.py matrix` for the machine-readable baseline and `probe` for a real local Blender smoke fixture.

## Downstream games/apps

For game work, coordinate with WhatIf Game Dev Studio. Prefer GLB/glTF for portable PBR scene/assets when the target supports it. Use another format only for a concrete compatibility reason. Record source `.blend`, export path, units/scale convention, animation expectations, texture policy, provenance, and verification evidence so a later AI can safely reuse the asset.

