import json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; TOOL=ROOT/"templates/skills/ui-forge/scripts/evidence_bundle.py"
def c(*a): return subprocess.run(["python",str(TOOL),*map(str,a)],capture_output=True,text=True)
checks={}
with tempfile.TemporaryDirectory(prefix="uif-evidence-") as td:
 root=Path(td); (root/"src").mkdir(); (root/"src/App.jsx").write_text("A")
 proof=root/"proof"; proof.mkdir(); (proof/"desktop.png").write_text("image"); (proof/"audit.json").write_text('{"pass":true}')
 p=c("create",root,"--label","Release proof","--artifact",proof/"desktop.png","--artifact",proof/"audit.json","--claim","desktop browser proof")
 d=json.loads(p.stdout); bp=Path(d["bundle"]); checks["bundle_created"]=p.returncode==0 and d["artifact_count"]==2
 p=c("verify",bp); checks["bundle_verifies"]=p.returncode==0 and json.loads(p.stdout)["ok"]
 # evidence storage must not contaminate source fingerprint
 p2=c("create",root,"--label","Second","--artifact",proof/"audit.json"); d2=json.loads(p2.stdout); checks["evidence_excluded_from_source_fingerprint"]=d2["source_fingerprint"]==d["source_fingerprint"]
 # tamper copied artifact
 manifest=json.loads((bp/"manifest.json").read_text()); art=bp/manifest["artifacts"][0]["stored_as"]; art.write_text("tamper"); p=c("verify",bp); checks["artifact_tamper_detected"]=p.returncode!=0
 # manifest tamper
 bp2=Path(d2["bundle"]); mp=bp2/"manifest.json"; m=json.loads(mp.read_text()); m["claims"]=["forged"]; mp.write_text(json.dumps(m)); p=c("verify",bp2); checks["manifest_tamper_detected"]=p.returncode!=0
result={"schema":"ui-forge-evidence-bundle-benchmark-v1","checks":checks,"passed":sum(checks.values()),"total":len(checks),"overall_pass":all(checks.values()),"claims":{"tamper_evident_evidence_bundle":all(checks.values()),"evidence_does_not_contaminate_source_fingerprint":checks["evidence_excluded_from_source_fingerprint"],"not_a_full_ui_forge_or_lovable_claim":True}}
print(json.dumps(result,indent=2)); raise SystemExit(0 if result["overall_pass"] else 1)
