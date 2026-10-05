import json, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; TOOL=ROOT/"templates/skills/ui-forge/scripts/direction_board.py"
def call(*args):
 p=subprocess.run(["python",str(TOOL),*map(str,args)],capture_output=True,text=True); return p
checks={}
with tempfile.TemporaryDirectory(prefix="uif-board-") as td:
 root=Path(td); (root/"App.jsx").write_text("export default()=> <main>Hello</main>",encoding="utf-8")
 p=call("create",root,"--title","Test","--direction","A","--direction","B")
 checks["create_two_directions"]=p.returncode==0
 data=json.loads(p.stdout); checks["isolated_drafts"]=len(data["directions"])==2 and all(Path(x["workspace"]).is_dir() for x in data["directions"])
 bid=data["id"]
 p=call("select",root,bid,"A"); checks["selection_without_evidence_refused"]=p.returncode!=0
 proof=root/".synapse/ui-forge/proof"; proof.mkdir(parents=True)
 for n,c in [("shot.png","png"),("browser.json",'{"pass":true}'),("score.json",'{"overall":90}')]: (proof/n).write_text(c,encoding="utf-8")
 p=call("evidence",root,bid,"A","--screenshot",proof/"shot.png","--browser-proof",proof/"browser.json","--score",proof/"score.json")
 checks["evidence_attaches"]=p.returncode==0
 p=call("select",root,bid,"A"); checks["evidence_gated_selection"]=p.returncode==0 and json.loads(p.stdout)["selected"]["merge_performed"] is False
 board=root/".synapse/ui-forge/direction-boards"/(bid+".json"); saved=json.loads(board.read_text()); checks["selection_does_not_merge"]=saved["selected"]["merge_performed"] is False and (root/"App.jsx").read_text()=="export default()=> <main>Hello</main>"
 # tamper evidence then reselect
 (proof/"score.json").write_text('{"overall":1}',encoding="utf-8"); p=call("select",root,bid,"A"); checks["tampered_evidence_refused"]=p.returncode!=0
 # restore evidence hash by reattach, then drift live source
 call("evidence",root,bid,"A","--screenshot",proof/"shot.png","--browser-proof",proof/"browser.json","--score",proof/"score.json")
 (root/"App.jsx").write_text("export default()=> <main>Drift</main>",encoding="utf-8"); p=call("select",root,bid,"A"); checks["source_drift_refused"]=p.returncode!=0
 p=call("create",root,"--title","Bad","--direction","Only"); checks["one_direction_refused"]=p.returncode!=0
result={"schema":"ui-forge-direction-board-benchmark-v1","checks":checks,"passed":sum(checks.values()),"total":len(checks),"overall_pass":all(checks.values()),"claims":{"evidence_gated_direction_selection":all(checks.values()),"selection_is_non_merging":True,"not_a_full_ui_forge_or_lovable_claim":True}}
print(json.dumps(result,indent=2)); raise SystemExit(0 if result["overall_pass"] else 1)
