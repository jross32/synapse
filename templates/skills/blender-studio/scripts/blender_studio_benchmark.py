from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

DEFAULT_BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"


def find_blender() -> str | None:
    for candidate in (os.getenv("BLENDER_PATH"), shutil.which("blender"), DEFAULT_BLENDER):
        if candidate and Path(candidate).is_file():
            return str(Path(candidate))
    return None


BUILD_SCRIPT = r'''
import bpy, json, math
from pathlib import Path
root=Path(__import__("sys").argv[__import__("sys").argv.index("--")+1])
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene
scene.unit_settings.system='METRIC'
scene.unit_settings.scale_length=1.0

# Mesh / transforms / UV
bpy.ops.mesh.primitive_cube_add(size=2, location=(0,0,0))
obj=bpy.context.object
obj.name='BenchmarkMesh'
obj.scale=(1.0,.7,.5)
bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
bpy.context.view_layer.objects.active=obj
for p in obj.data.polygons: p.select=True
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.uv.smart_project()
bpy.ops.object.mode_set(mode='OBJECT')

# Original packed image texture + PBR material
img=bpy.data.images.new('BenchmarkTexture', width=4, height=4, alpha=True)
pixels=[]
for y in range(4):
    for x in range(4):
        pixels += ([0.9,0.2,0.05,1.0] if (x+y)%2 else [0.05,0.7,0.25,1.0])
img.pixels[:]=pixels
img.filepath_raw=str(root/'benchmark_texture.png')
img.file_format='PNG'
img.save()
img.pack()
mat=bpy.data.materials.new('BenchmarkPBR')
mat.use_nodes=True
nt=mat.node_tree
bs=nt.nodes.get('Principled BSDF')
tex=nt.nodes.new('ShaderNodeTexImage')
tex.name='BenchmarkImageTexture'
tex.image=img
bs.inputs['Roughness'].default_value=.33
nt.links.new(tex.outputs['Color'],bs.inputs['Base Color'])
obj.data.materials.append(mat)

# Conventional modifier
bev=obj.modifiers.new('BenchmarkBevel','BEVEL')
bev.width=.08
bev.segments=2

# Nontrivial Geometry Nodes transform
tree=bpy.data.node_groups.new('BenchmarkGeometry','GeometryNodeTree')
tree.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
tree.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
inp=tree.nodes.new('NodeGroupInput')
out=tree.nodes.new('NodeGroupOutput')
trans=tree.nodes.new('GeometryNodeTransform')
trans.inputs['Translation'].default_value=(0,0,.5)
tree.links.new(inp.outputs['Geometry'],trans.inputs['Geometry'])
tree.links.new(trans.outputs['Geometry'],out.inputs['Geometry'])
gn=obj.modifiers.new('BenchmarkGeometryNodes','NODES')
gn.node_group=tree

# Rig + weighted mesh + animation + NLA
bpy.ops.mesh.primitive_cube_add(size=1, location=(0,0,1.5))
rig_mesh=bpy.context.object
rig_mesh.name='BenchmarkRigMesh'
ad=bpy.data.armatures.new('BenchmarkRigData')
arm=bpy.data.objects.new('BenchmarkRig',ad)
scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active=arm
arm.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
bone=ad.edit_bones.new('Root')
bone.head=(0,0,0); bone.tail=(0,0,1)
bpy.ops.object.mode_set(mode='OBJECT')
am=rig_mesh.modifiers.new('BenchmarkArmature','ARMATURE')
am.object=arm
vg=rig_mesh.vertex_groups.new(name='Root')
vg.add(range(len(rig_mesh.data.vertices)),1.0,'REPLACE')
pb=arm.pose.bones['Root']
pb.rotation_mode='XYZ'
for frame,angle in ((1,0.0),(12,0.6)):
    scene.frame_set(frame)
    pb.rotation_euler=(0,angle,0)
    pb.keyframe_insert(data_path='rotation_euler',frame=frame)
act=arm.animation_data.action
track=arm.animation_data.nla_tracks.new()
track.name='BenchmarkTrack'
strip=track.strips.new('BenchmarkStrip',1,act)
strip.name='BenchmarkStrip'
scene.frame_start=1; scene.frame_end=12

# Camera/light/render
bpy.ops.object.camera_add(location=(4,-5,3))
cam=bpy.context.object
cam.name='BenchmarkCamera'
scene.camera=cam
from mathutils import Vector
cam.rotation_euler=(Vector((0,0,.5))-cam.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.light_add(type='AREA', location=(2,-2,4))
light=bpy.context.object
light.name='BenchmarkKey'
light.data.energy=700
light.data.size=4
scene.render.engine='BLENDER_WORKBENCH'
scene.render.resolution_x=64
scene.render.resolution_y=64
scene.render.resolution_percentage=100
scene.render.filepath=str(root/'benchmark_render.png')
scene.render.image_settings.file_format='PNG'

blend=root/'benchmark.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(blend))

# Exports happen before visual proof so structural artifacts survive slow renderer startup.
bpy.ops.export_scene.gltf(filepath=str(root/'benchmark.glb'),export_format='GLB',export_animations=True)
bpy.ops.export_scene.fbx(filepath=str(root/'benchmark.fbx'),use_selection=False,add_leaf_bones=False)
bpy.ops.wm.obj_export(filepath=str(root/'benchmark.obj'),export_materials=True)
bpy.ops.wm.usd_export(filepath=str(root/'benchmark.usdc'),selected_objects_only=False)
bpy.ops.render.render(write_still=True)

mesh=obj.data
mesh.calc_loop_triangles()
print('BUILD_RECEIPT:'+json.dumps({
  'blender':bpy.app.version_string,
  'objects':len(scene.objects),
  'mesh_vertices':len(mesh.vertices),
  'triangles':len(mesh.loop_triangles),
  'uv_layers':len(mesh.uv_layers),
  'materials':[m.name for m in mesh.materials],
  'packed_texture':bool(img.packed_file),
  'gn_nodes':[n.bl_idname for n in tree.nodes],
  'nla_tracks':[t.name for t in arm.animation_data.nla_tracks],
  'files':{p.name:p.stat().st_size for p in root.iterdir() if p.is_file()}
}))
'''

VALIDATE_SCRIPT = r'''
import bpy, json
from pathlib import Path
root=Path(__import__("sys").argv[__import__("sys").argv.index("--")+1])
obj=bpy.data.objects['BenchmarkMesh']
mesh=obj.data
mesh.calc_loop_triangles()
tree=bpy.data.node_groups['BenchmarkGeometry']
deps=bpy.context.evaluated_depsgraph_get()
ev=obj.evaluated_get(deps)
zs=[v.co.z for v in ev.data.vertices]
img=bpy.data.images.get('BenchmarkTexture')
mat=bpy.data.materials.get('BenchmarkPBR')
tex=mat.node_tree.nodes.get('BenchmarkImageTexture') if mat else None
rig_mesh=bpy.data.objects['BenchmarkRigMesh']
arm=bpy.data.objects['BenchmarkRig']
def sample(frame):
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    e=rig_mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return tuple(e.data.vertices[0].co)
p1=sample(1); p12=sample(12)
base={
 'identity_scale':all(abs(v-1)<1e-6 for v in obj.scale),
 'identity_rotation':all(abs(v)<1e-6 for v in obj.rotation_euler),
 'positive_determinant':obj.matrix_world.determinant()>0,
 'unit_system':bpy.context.scene.unit_settings.system,
 'unit_scale':bpy.context.scene.unit_settings.scale_length,
 'uv_loops':len(mesh.uv_layers.active.data) if mesh.uv_layers.active else 0,
 'material':mesh.materials[0].name if mesh.materials else None,
 'texture_packed':bool(img and img.packed_file),
 'texture_link':tex.image.name if tex and tex.image else None,
 'modifier_types':[m.type for m in obj.modifiers],
 'gn_nodes':[n.bl_idname for n in tree.nodes],
 'gn_min_z':min(zs),'gn_max_z':max(zs),
 'rig_delta':sum(abs(a-b) for a,b in zip(p1,p12)),
 'rig_weighted_vertices':sum(rig_mesh.vertex_groups['Root'].weight(i)>.99 for i in range(len(rig_mesh.data.vertices))),
 'action':arm.animation_data.action.name if arm.animation_data and arm.animation_data.action else None,
 'nla_tracks':[t.name for t in arm.animation_data.nla_tracks],
 'nla_strips':[s.name for t in arm.animation_data.nla_tracks for s in t.strips],
 'triangles':len(mesh.loop_triangles),
}
imports={}
for fmt,name in [('glb','benchmark.glb'),('fbx','benchmark.fbx'),('obj','benchmark.obj'),('usd','benchmark.usdc')]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    p=root/name
    if fmt=='glb': bpy.ops.import_scene.gltf(filepath=str(p))
    elif fmt=='fbx': bpy.ops.import_scene.fbx(filepath=str(p))
    elif fmt=='obj': bpy.ops.wm.obj_import(filepath=str(p))
    else: bpy.ops.wm.usd_import(filepath=str(p))
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    imports[fmt]={
      'mesh_count':len(meshes),
      'vertices':sum(len(o.data.vertices) for o in meshes),
      'materials':[m.name for m in bpy.data.materials],
      'armatures':[o.name for o in bpy.context.scene.objects if o.type=='ARMATURE'],
      'actions':[a.name for a in bpy.data.actions],
    }
print('VALIDATE_RECEIPT:'+json.dumps({'base':base,'imports':imports}))
'''


def run_blender(blender: str, args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run([blender, *args], capture_output=True, text=True, timeout=timeout, check=False)


def marker(stdout: str, prefix: str) -> dict:
    line=next((x[len(prefix):] for x in stdout.splitlines() if x.startswith(prefix)), None)
    if not line:
        raise RuntimeError(f"missing {prefix} marker")
    return json.loads(line)


def benchmark(output: str | None) -> dict:
    blender=find_blender()
    if not blender:
        return {'ok':False,'reason':'blender_not_found'}
    root=Path(output).resolve() if output else Path(tempfile.mkdtemp(prefix='blender-studio-benchmark-'))
    root.mkdir(parents=True,exist_ok=True)
    build_py=root/'build.py'; validate_py=root/'validate.py'
    build_py.write_text(BUILD_SCRIPT,encoding='utf-8')
    validate_py.write_text(VALIDATE_SCRIPT,encoding='utf-8')
    build=run_blender(blender,['--background','--python',str(build_py),'--',str(root)])
    if build.returncode:
        result={'ok':False,'stage':'build','exit_code':build.returncode,'stderr_tail':build.stderr[-3000:],'stdout_tail':build.stdout[-3000:]}
        (root/'benchmark-receipt.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        return result
    build_receipt=marker(build.stdout,'BUILD_RECEIPT:')
    blend=root/'benchmark.blend'
    validate=run_blender(blender,['--background',str(blend),'--python',str(validate_py),'--',str(root)])
    if validate.returncode:
        result={'ok':False,'stage':'validate','exit_code':validate.returncode,'stderr_tail':validate.stderr[-3000:],'stdout_tail':validate.stdout[-3000:],'build':build_receipt}
        (root/'benchmark-receipt.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        return result
    vr=marker(validate.stdout,'VALIDATE_RECEIPT:')
    b=vr['base']; im=vr['imports']
    checks={
      'source_blend':blend.is_file() and blend.stat().st_size>0,
      'render':(root/'benchmark_render.png').is_file() and (root/'benchmark_render.png').stat().st_size>1000,
      'identity_transforms':b['identity_scale'] and b['identity_rotation'] and b['positive_determinant'],
      'metric_units':b['unit_system']=='METRIC' and abs(b['unit_scale']-1)<1e-6,
      'uv':b['uv_loops']>0,
      'pbr_texture':b['material']=='BenchmarkPBR' and b['texture_packed'] and b['texture_link']=='BenchmarkTexture',
      'modifiers':'BEVEL' in b['modifier_types'] and 'NODES' in b['modifier_types'],
      'geometry_nodes':'GeometryNodeTransform' in b['gn_nodes'] and b['gn_min_z']>=0 and b['gn_max_z']>=1,
      'rig_deformation':b['rig_delta']>.1 and b['rig_weighted_vertices']==8,
      'animation_nla':bool(b['action']) and 'BenchmarkTrack' in b['nla_tracks'] and 'BenchmarkStrip' in b['nla_strips'],
      'gltf_roundtrip':im['glb']['mesh_count']>0 and im['glb']['vertices']>0,
      'fbx_roundtrip':im['fbx']['mesh_count']>0 and im['fbx']['vertices']>0,
      'obj_roundtrip':im['obj']['mesh_count']>0 and im['obj']['vertices']>0,
      'usd_roundtrip':im['usd']['mesh_count']>0 and im['usd']['vertices']>0,
      'animated_gltf':len(im['glb']['actions'])>0 and len(im['glb']['armatures'])>0,
    }
    result={'ok':all(checks.values()),'blender':blender,'root':str(root),'checks':checks,'build':build_receipt,'validation':vr}
    (root/'benchmark-receipt.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--output')
    args=ap.parse_args()
    result=benchmark(args.output)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result.get('ok') else 1)


if __name__=='__main__':
    main()
