#!/usr/bin/env python3
import argparse,json,statistics
from pathlib import Path
SCHEMA="ui-forge-superiority-claim-gate-v1"
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("results"); ap.add_argument("--min-repeats",type=int,default=5); a=ap.parse_args()
 d=json.loads(Path(a.results).read_text()); pairs=d.get("pairs",[]); reasons=[]
 if len(pairs)<a.min_repeats: reasons.append(f"need at least {a.min_repeats} paired repeats")
 keys=("model","model_version","tools","machine","fixture","task","prompt","time_budget")
 for i,p in enumerate(pairs):
  b=p.get("baseline",{}); c=p.get("challenger",{})
  for k in keys:
   if b.get(k)!=c.get(k): reasons.append(f"pair {i} mismatch: {k}")
  if not b.get("complete") or not c.get("complete"): reasons.append(f"pair {i} incomplete evidence")
  if c.get("critical_failures",0)>0: reasons.append(f"pair {i} challenger critical failure")
  if c.get("pass_rate",0)<b.get("pass_rate",0): reasons.append(f"pair {i} challenger lower pass rate")
  if c.get("score",0)<=b.get("score",0): reasons.append(f"pair {i} challenger did not strictly win")
 deltas=[p["challenger"].get("score",0)-p["baseline"].get("score",0) for p in pairs] if pairs else []
 out={"schema":SCHEMA,"eligible":not reasons,"paired_repeats":len(pairs),"reasons":reasons,"score_deltas":deltas,"median_delta":statistics.median(deltas) if deltas else None,"claim":("measured challenger superiority supported for this benchmark configuration" if not reasons else "superiority claim refused")}
 print(json.dumps(out,indent=2)); raise SystemExit(0 if out["eligible"] else 2)
if __name__=="__main__": main()
