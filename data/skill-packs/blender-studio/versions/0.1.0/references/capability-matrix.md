# Blender Studio capability matrix

Status vocabulary: **verified** = exercised by a real reproducible fixture/gate; **partial** = some operations proven but not a broad lane; **unverified** = available in Blender/API but not yet accepted as a Synapse Blender Studio capability.

| Lane | Initial status | Acceptance evidence |
|---|---|---|
| Blender discovery/headless execution | verified | Game Dev Studio doctor + installed Blender invocation |
| Live MCP inspection + arbitrary bpy execution | verified | registered Blender MCP semantic tools + execute_blender_code |
| Mesh primitive/model creation | verified | existing RoomSpace3D scripted geometry; generic fixture required |
| Materials/PBR nodes | verified | existing project materials; generic portable fixture required |
| Cameras/lights/render | verified | RoomSpace3D renders + MCP render tools |
| Save/reopen background validation | verified | independent RoomSpace3D background validators |
| UV unwrap | unverified | create mesh, unwrap, reopen and assert UV layer |
| Image textures/packing | unverified | generated image texture, node hookup, missing-file/pack policy gate |
| Modifiers | verified | deterministic modifier fixture + applied/non-applied validation |
| Geometry Nodes | unverified | procedural node group fixture + evaluated geometry assertion |
| Rigging/skinning | unverified | armature + weights + pose deformation fixture |
| Animation/actions/NLA | unverified | keyed action fixture + frame-state assertions/export check |
| Compositing | unverified | node pipeline + deterministic render evidence |
| glTF/GLB export | verified | export + clean re-import + material/geometry assertions |
| FBX export | unverified | export + clean re-import or target-engine validation |
| OBJ export | unverified | export + clean re-import geometry assertion |
| USD export | unverified | export + clean re-import/validator where supported |
| Game-ready optimization | unverified | transforms/origin/naming/triangle/material/scale gate |
| Downstream engine import | unverified | engine-specific import/build/playtest evidence |

The matrix is intentionally conservative. A green lane must mean something an AI can rely on, not merely something Blender theoretically supports.


## Generic Blender Studio probe evidence
The initial synthetic probe creates a mesh, Principled PBR material, Bevel modifier, camera and area light, saves a `.blend`, exports GLB, then supports independent background reopen assertions and clean GLB re-import. This is deliberately generic and not dependent on RoomSpace3D. On Blender 5.2 the accepted fixture produced an 89,652-byte `.blend` and 2,004-byte GLB; clean GLB re-import yielded one mesh, the `ProbePBR` material, and 24 vertices. This promotes mesh creation, PBR materials, modifiers, and GLB export from partial/unverified to verified baseline lanes. It does not prove UVs, textures, geometry nodes, rigs, animation, compositing, FBX/OBJ/USD, optimization, or downstream-engine import.
