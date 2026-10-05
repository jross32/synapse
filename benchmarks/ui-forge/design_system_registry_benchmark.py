import json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; TOOL=ROOT/"templates/skills/ui-forge/scripts/design_system_registry.py"
def c(*a): return subprocess.run(["python",str(TOOL),*map(str,a)],capture_output=True,text=True)
checks={}
with tempfile.TemporaryDirectory(prefix="uif-ds-") as td:
 root=Path(td); src=root/"inputs"; src.mkdir()
 def files(suffix):
  t=src/f"theme{suffix}.json"; cpt=src/f"components{suffix}.json"; g=src/f"guide{suffix}.md"; t.write_text('{"accent":"#000"}' if suffix=="1" else '{"accent":"#111"}'); cpt.write_text('{"Button":["primary"]}'); g.write_text("Use semantic tokens."); return t,cpt,g
 t,cpt,g=files("1"); p=c("publish",root,"--name","core","--version","1.0.0","--theme",t,"--components",cpt,"--guidelines",g); checks["publish_v1"]=p.returncode==0
 p=c("publish",root,"--name","core","--version","1.0.0","--theme",t,"--components",cpt,"--guidelines",g); checks["immutable_version"]=p.returncode!=0
 p=c("pin",root,"--name","core","--version","1.0.0"); checks["pin_verified_version"]=p.returncode==0
 t2,c2,g2=files("2"); p=c("publish",root,"--name","core","--version","1.1.0","--theme",t2,"--components",c2,"--guidelines",g2); checks["publish_v2"]=p.returncode==0
 p=c("diff",root,"--name","core","1.0.0","1.1.0"); checks["version_diff"]=p.returncode==0 and json.loads(p.stdout)["changed"]==["theme"]
 # existing pin stays old until explicit repin
 pins=json.loads((root/".synapse/ui-forge/design-systems/pins.json").read_text()); checks["no_implicit_repin"]=pins["pins"]["core"]["version"]=="1.0.0"
 p=c("pin",root,"--name","core","--version","1.1.0"); checks["explicit_repin"]=p.returncode==0
 # tamper then pin must fail
 (root/".synapse/ui-forge/design-systems/core/1.1.0"/t2.name).write_text("tamper"); p=c("pin",root,"--name","core","--version","1.1.0"); checks["tamper_refused"]=p.returncode!=0
result={"schema":"ui-forge-design-system-registry-benchmark-v1","checks":checks,"passed":sum(checks.values()),"total":len(checks),"overall_pass":all(checks.values()),"claims":{"immutable_versioned_design_system_registry":all(checks.values()),"explicit_project_pinning":True,"not_a_full_ui_forge_or_lovable_claim":True}}
print(json.dumps(result,indent=2)); raise SystemExit(0 if result["overall_pass"] else 1)
