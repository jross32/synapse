from __future__ import annotations
import argparse, json, os, shutil, subprocess, tempfile
from pathlib import Path

LANES = {
 "discovery_headless":"verified", "live_mcp_bpy":"verified", "mesh_modeling":"verified",
 "materials_pbr":"verified", "camera_light_render":"verified", "save_reopen_validation":"verified",
 "uv":"unverified", "image_textures":"unverified", "modifiers":"verified", "geometry_nodes":"unverified",
 "rigging_skinning":"unverified", "animation":"unverified", "compositing":"unverified", "gltf_glb":"verified",
 "fbx":"unverified", "obj":"unverified", "usd":"unverified", "game_optimization":"unverified", "downstream_engine":"unverified"
}

def find_blender():
    env=os.getenv("BLENDER_PATH")
    candidates=[env, shutil.which("blender"), r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"]
    for c in candidates:
        if c and Path(c).is_file(): return str(Path(c))
    return None

def matrix(): return {"schema":1,"lanes":LANES,"verified":sum(v=="verified" for v in LANES.values()),"partial":sum(v=="partial" for v in LANES.values()),"unverified":sum(v=="unverified" for v in LANES.values())}

def probe(output: str | None):
    blender=find_blender()
    if not blender: return {"ok":False,"reason":"blender_not_found"}
    root=Path(output).resolve() if output else Path(tempfile.mkdtemp(prefix="synapse-blender-studio-"))
    root.mkdir(parents=True,exist_ok=True); blend=root/"probe.blend"; glb=root/"probe.glb"; receipt=root/"receipt.json"
    script=root/"probe.py"
    script.write_text(r'''import bpy,json,sys
from pathlib import Path
root=Path(sys.argv[sys.argv.index("--")+1]); blend=root/"probe.blend"; glb=root/"probe.glb"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(location=(0,0,0)); o=bpy.context.object; o.name="SynapseProbeCube"; o.scale=(1,.7,.5); bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
mat=bpy.data.materials.new("ProbePBR"); mat.use_nodes=True; bs=mat.node_tree.nodes.get("Principled BSDF"); bs.inputs["Base Color"].default_value=(0.08,0.28,0.8,1); bs.inputs["Roughness"].default_value=.32; o.data.materials.append(mat)
bev=o.modifiers.new("ProbeBevel","BEVEL"); bev.width=.12; bev.segments=3
bpy.ops.object.camera_add(location=(4,-5,3)); cam=bpy.context.object; bpy.context.scene.camera=cam
def point(obj,pt=(0,0,0)):
 import mathutils; obj.rotation_euler=(mathutils.Vector(pt)-obj.location).to_track_quat('-Z','Y').to_euler()
point(cam)
bpy.ops.object.light_add(type='AREA',location=(2,-2,4)); bpy.context.object.data.energy=700; bpy.context.object.data.shape='DISK'; bpy.context.object.data.size=4
bpy.context.scene.render.engine='BLENDER_EEVEE'; bpy.context.scene.render.resolution_x=320; bpy.context.scene.render.resolution_y=240; bpy.context.scene.render.resolution_percentage=100
bpy.ops.wm.save_as_mainfile(filepath=str(blend)); bpy.ops.export_scene.gltf(filepath=str(glb),export_format='GLB')
print('PROBE:'+json.dumps({'objects':len(bpy.data.objects),'mesh':o.name,'material':mat.name,'modifier':bev.type,'blend':str(blend),'glb':str(glb)}))
''',encoding="utf-8")
    cp=subprocess.run([blender,"--background","--python",str(script),"--",str(root)],capture_output=True,text=True,timeout=120)
    marker=next((x[6:] for x in cp.stdout.splitlines() if x.startswith("PROBE:")),None)
    data=json.loads(marker) if marker else {}
    ok=cp.returncode==0 and blend.is_file() and blend.stat().st_size>0 and glb.is_file() and glb.stat().st_size>0
    out={"ok":ok,"blender":blender,"root":str(root),"blend_bytes":blend.stat().st_size if blend.exists() else 0,"glb_bytes":glb.stat().st_size if glb.exists() else 0,"probe":data,"stderr_tail":cp.stderr[-1000:]}
    receipt.write_text(json.dumps(out,indent=2),encoding="utf-8")
    return out

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True); sub.add_parser("matrix"); p=sub.add_parser("probe"); p.add_argument("--output")
    a=ap.parse_args(); r=matrix() if a.cmd=="matrix" else probe(a.output); print(json.dumps(r,indent=2)); raise SystemExit(0 if r.get("ok",True) else 1)
if __name__=="__main__": main()

