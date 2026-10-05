import json, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; TOOL=ROOT/"templates/skills/ui-forge/scripts/version_ledger.py"
def call(*a): return subprocess.run(["python",str(TOOL),*map(str,a)],capture_output=True,text=True)
checks={}
with tempfile.TemporaryDirectory(prefix="uif-ledger-") as td:
 root=Path(td); (root/"src").mkdir(); f=root/"src/App.jsx"; f.write_text("A",encoding="utf-8"); (root/".env").write_text("SECRET=x")
 p=call("create",root,"--label","Known good"); data=json.loads(p.stdout); bid=data["bookmark"]
 checks["bookmark_created"]=p.returncode==0 and data["file_count"]==1
 checks["env_excluded"]=not any(".env" in str(x) for x in (root/".synapse/ui-forge/version-ledger/objects").iterdir())
 f.write_text("B",encoding="utf-8")
 p=call("plan",root,bid,"--path","src/App.jsx"); plan=json.loads(p.stdout); pp=Path(plan["plan"])
 checks["dry_run_detects_change"]=p.returncode==0 and plan["dry_run"] and len(plan["changes"])==1 and f.read_text()=="B"
 p=call("restore",root,bid,"--plan",pp); checks["restore_succeeds"]=p.returncode==0 and f.read_text()=="A"
 f.write_text("C"); p=call("plan",root,bid); pp=Path(json.loads(p.stdout)["plan"]); f.write_text("D"); p=call("restore",root,bid,"--plan",pp)
 checks["post_plan_drift_refused"]=p.returncode!=0 and f.read_text()=="D"
 f.write_text("E"); p=call("plan",root,bid); pp=Path(json.loads(p.stdout)["plan"]); d=json.loads(pp.read_text()); d["changes"][0]["path"]="evil.txt"; pp.write_text(json.dumps(d)); p=call("restore",root,bid,"--plan",pp)
 checks["tampered_plan_refused"]=p.returncode!=0 and f.read_text()=="E"
 # tamper object
 p=call("plan",root,bid); pp=Path(json.loads(p.stdout)["plan"]); book=json.loads(next((root/".synapse/ui-forge/version-ledger/bookmarks").glob("*.json")).read_text()); hv=book["files"]["src/App.jsx"]["sha256"]; (root/".synapse/ui-forge/version-ledger/objects"/hv).write_text("tamper"); p=call("restore",root,bid,"--plan",pp)
 checks["tampered_object_refused"]=p.returncode!=0 and f.read_text()=="E"
result={"schema":"ui-forge-version-ledger-benchmark-v1","checks":checks,"passed":sum(checks.values()),"total":len(checks),"overall_pass":all(checks.values()),"claims":{"content_addressed_bookmarks":True,"drift_safe_restore":all(checks.values()),"not_a_full_ui_forge_or_lovable_claim":True}}
print(json.dumps(result,indent=2)); raise SystemExit(0 if result["overall_pass"] else 1)
