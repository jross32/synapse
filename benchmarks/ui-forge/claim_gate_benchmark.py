import json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; TOOL=ROOT/"templates/skills/ui-forge/scripts/claim_gate.py"
base={"model":"gpt","model_version":"x","tools":["browser"],"machine":"m","fixture":"f","task":"t","prompt":"p","time_budget":30,"complete":True,"critical_failures":0,"pass_rate":1.0,"score":80}
def run(pairs):
 with tempfile.NamedTemporaryFile("w",suffix=".json",delete=False) as f: json.dump({"pairs":pairs},f); n=f.name
 p=subprocess.run(["python",str(TOOL),n],capture_output=True,text=True); Path(n).unlink(); return p,json.loads(p.stdout)
def pair(delta=5):
 b=dict(base); c=dict(base); c["score"]=b["score"]+delta; return {"baseline":b,"challenger":c}
checks={}
p,d=run([pair() for _ in range(5)]); checks["five_strict_wins_allowed"]=p.returncode==0 and d["eligible"]
p,d=run([pair() for _ in range(4)]); checks["insufficient_repeats_refused"]=p.returncode!=0
x=[pair() for _ in range(5)]; x[2]["challenger"]["model_version"]="other"; p,d=run(x); checks["mismatched_environment_refused"]=p.returncode!=0
x=[pair() for _ in range(5)]; x[1]["challenger"]["score"]=80; p,d=run(x); checks["tie_refused"]=p.returncode!=0
x=[pair() for _ in range(5)]; x[1]["challenger"]["critical_failures"]=1; p,d=run(x); checks["critical_failure_refused"]=p.returncode!=0
x=[pair() for _ in range(5)]; x[1]["challenger"]["pass_rate"]=.8; p,d=run(x); checks["lower_pass_rate_refused"]=p.returncode!=0
x=[pair() for _ in range(5)]; x[1]["challenger"]["complete"]=False; p,d=run(x); checks["incomplete_evidence_refused"]=p.returncode!=0
result={"schema":"ui-forge-claim-gate-benchmark-v1","checks":checks,"passed":sum(checks.values()),"total":len(checks),"overall_pass":all(checks.values()),"claims":{"superiority_language_is_evidence_gated":all(checks.values()),"does_not_itself_prove_superiority":True}}
print(json.dumps(result,indent=2)); raise SystemExit(0 if result["overall_pass"] else 1)
