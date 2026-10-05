import json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; TOOL=ROOT/"templates/skills/ui-forge/scripts/review_pins.py"
def c(*a): return subprocess.run(["python",str(TOOL),*map(str,a)],capture_output=True,text=True)
checks={}
with tempfile.TemporaryDirectory(prefix="uif-pins-") as td:
 root=Path(td); (root/"src").mkdir(); f=root/"src/App.jsx"; f.write_text("const x=1;\nexport default function App(){\n return <button>Save</button>;\n}\n")
 p=c("add",root,"--source","src/App.jsx:3:9","--ui-id","uif-save","--note","Needs stronger CTA"); checks["pin_added"]=p.returncode==0
 f.write_text("// shifted\n"+f.read_text()); p=c("resolve",root); d=json.loads(p.stdout)["results"][0]; checks["survives_line_shift"]=d["status"]=="resolved" and d["matches"]==[4]
 f.write_text(f.read_text().replace("return <button>Save</button>;","return <button>Publish</button>;")); p=c("resolve",root); checks["changed_target_orphans"]=json.loads(p.stdout)["results"][0]["status"]=="orphaned"
 f.write_text("return <button>Save</button>;\nreturn <button>Save</button>;\n"); p=c("resolve",root); checks["duplicate_target_ambiguous"]=json.loads(p.stdout)["results"][0]["status"]=="ambiguous"
result={"schema":"ui-forge-review-pins-benchmark-v1","checks":checks,"passed":sum(checks.values()),"total":len(checks),"overall_pass":all(checks.values()),"claims":{"source_anchored_review_pins":all(checks.values()),"not_a_full_ui_forge_or_lovable_claim":True}}
print(json.dumps(result,indent=2)); raise SystemExit(0 if result["overall_pass"] else 1)
