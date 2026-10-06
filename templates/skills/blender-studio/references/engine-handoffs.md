# Downstream engine handoff gates

A Blender asset is not "game ready" merely because export succeeded. Downstream validation must be target-specific and evidence-backed.

## Unity gate
Preferred artifact: GLB/glTF when the target project has a known glTF importer; otherwise FBX is the compatibility fallback. Run Unity headlessly when a valid Editor license is available, import into an isolated proof project, then assert imported root, meshes, vertex/triangle counts, materials, transforms/scale, animations where applicable, and no import errors. A Unity installation alone is not proof. On 2026-10-06 Unity 6000.4.0f1 was discovered locally, but the isolated batch proof stopped with exit 198 because no valid Unity Editor license was available. This is an environment blocker, not an asset failure.

## Roblox gate
Roblox Studio is installed locally and Synapse already has a Roblox Studio AI Bridge under `C:\Users\justi\robloxgame`. For Blender handoff, prefer an explicit import receipt rather than assuming Studio accepted a file. Validate MeshPart/asset creation, dimensions, pivot/orientation, collision policy, texture/material result, and a visual Studio screenshot/playtest. Roblox upload/import can involve platform authentication and asset publication, so keep the final user-account/publish step explicit when required.

## Receipt fields
`target_engine`, `engine_version`, `source_blend`, `export_path`, `export_format`, `importer`, `import_status`, `mesh_count`, `triangles`, `materials`, `textures`, `animations`, `scale`, `orientation`, `collision`, `visual_evidence`, `playtest_status`, `errors`, `limitations`.

## Failure semantics
- Export pass + engine unavailable => Blender export verified; downstream lane blocked/unverified.
- Engine launch/license/auth failure => environment blocker, never label asset invalid.
- Import warning => preserve warning in receipt and keep affected assertion partial/failed.
- Visual success without structural assertions => partial only.
- Structural success without visual/playtest evidence => partial only.
- Publish/upload success is separate from local import success.
