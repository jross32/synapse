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
| UV unwrap | verified | create mesh, unwrap, reopen and assert UV layer |
| Image textures/packing | verified | generated image texture, node hookup, missing-file/pack policy gate |
| Modifiers | verified | deterministic modifier fixture + applied/non-applied validation |
| Geometry Nodes | partial | procedural node group fixture + evaluated geometry assertion |
| Rigging/skinning | partial | armature + weights + pose deformation fixture |
| Animation/actions/NLA | partial | keyed action fixture + frame-state assertions/export check |
| Compositing | partial | node pipeline + deterministic render evidence |
| glTF/GLB export | verified | export + clean re-import + material/geometry assertions |
| FBX export | verified | export + clean re-import or target-engine validation |
| OBJ export | verified | export + clean re-import geometry assertion |
| USD export | unverified | export + clean re-import/validator where supported |
| Game-ready optimization | unverified | transforms/origin/naming/triangle/material/scale gate |
| Downstream engine import | unverified | engine-specific import/build/playtest evidence |

The matrix is intentionally conservative. A green lane must mean something an AI can rely on, not merely something Blender theoretically supports.


## Generic Blender Studio probe evidence
The initial synthetic probe creates a mesh, Principled PBR material, Bevel modifier, camera and area light, saves a `.blend`, exports GLB, then supports independent background reopen assertions and clean GLB re-import. This is deliberately generic and not dependent on RoomSpace3D. On Blender 5.2 the accepted fixture produced an 89,652-byte `.blend` and 2,004-byte GLB; clean GLB re-import yielded one mesh, the `ProbePBR` material, and 24 vertices. This promotes mesh creation, PBR materials, modifiers, and GLB export from partial/unverified to verified baseline lanes. It does not prove UVs, textures, geometry nodes, rigs, animation, compositing, FBX/OBJ/USD, optimization, or downstream-engine import.

Additional 2026-10-06 fixture evidence: background Blender created and persisted a UVMap with 24 UV loops on the generic probe mesh; independent reopen retained all 24. The same fixture persisted a Blender 5.2 Action from frames 1-24 and independent reopen evaluated Z rotation from 0 to ~1.5708 radians. Basic action/keyframe animation is therefore proven, but the broader animation lane remains partial until NLA and exported animation are gated.

Geometry Nodes baseline evidence: generic probe now persists a ProbeGeometry GeometryNodeTree with group input/output and a NODES modifier; independent background reopen evaluates the mesh successfully. Marked partial because this proves node-tree construction/persistence/evaluation, not yet nontrivial procedural generation.

Image-texture evidence: generic fixture generated an original 4x4 PNG, assigned it through a ShaderNodeTexImage to Principled Base Color, packed it into the .blend, saved, and independently reopened it with packed data and node-to-image linkage intact.

Rigging baseline evidence: generic fixture persists ProbeRig, a Root bone, ARMATURE modifier targeting that rig, and full Root vertex-group weights on all 8 base vertices; independent background reopen confirms the relationship and weights. Marked partial until actual posed deformation plus animated/exported skinning is verified.

Blender 5.2 compositor compatibility finding: Scene.node_tree is no longer present in this environment; Scene.compositing_node_group is the active API surface. A CompositorNodeTree named ProbeCompositor was successfully assigned and saved. The independent follow-up CLI call timed out, so this lane remains partial rather than verified. Do not use pre-5.x scene.node_tree assumptions without version checking.

FBX/OBJ evidence: the generic probe exported a 34,732-byte FBX and 12,244-byte OBJ. Each was then imported into a clean background Blender state; both produced one mesh with 96 evaluated/exported vertices (FBX also restored the broader scene objects).

