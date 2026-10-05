#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys
from datetime import UTC, datetime
from pathlib import Path
DRAFT=Path(__file__).resolve().parent/"draft_workspace.py"
SCHEMA="ui-forge-direction-board-v1"
def digest(p):
 h=hashlib.sha256(); h.update(Path(p).read_bytes()); return h.hexdigest()
def boards(project): return project/".synapse"/"ui-forge"/"direction-boards"
def fingerprint(project):
 h=hashlib.sha256()
 for p in sorted(project.rglob("*")):
  if not p.is_file(): continue
  rel=p.relative_to(project).as_posix()
  if rel.startswith((".synapse/",".git/")) or "/node_modules/" in "/"+rel+"/": continue
  h.update(rel.encode()); h.update(b"|"); h.update(hashlib.sha256(p.read_bytes()).digest())
 return h.hexdigest()
def save(path,data):
 path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(data,indent=2),encoding="utf-8")
def load(project,bid):
 p=boards(project)/(bid+".json")
 if not p.is_file(): raise SystemExit("board not found")
 return p,json.loads(p.read_text(encoding="utf-8"))
def create_draft(project,title):
 r=subprocess.run([sys.executable,str(DRAFT),"create",str(project),"--title",title],capture_output=True,text=True)
 if r.returncode: raise SystemExit(r.stderr or r.stdout)
 return json.loads(r.stdout)
def main():
 ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest="cmd",required=True)
 c=sp.add_parser("create"); c.add_argument("project"); c.add_argument("--title",required=True); c.add_argument("--direction",action="append",required=True)
 e=sp.add_parser("evidence"); e.add_argument("project"); e.add_argument("board"); e.add_argument("direction"); e.add_argument("--screenshot",required=True); e.add_argument("--browser-proof",required=True); e.add_argument("--score",required=True)
 s=sp.add_parser("select"); s.add_argument("project"); s.add_argument("board"); s.add_argument("direction")
 a=ap.parse_args(); project=Path(a.project).resolve()
 if a.cmd=="create":
  if not 2<=len(a.direction)<=5: raise SystemExit("requires 2-5 directions")
  ds=[]
  for name in a.direction:
   d=create_draft(project,name); ds.append({"name":name,"draft_id":d["id"],"workspace":d["workspace"],"evidence":None})
  bid=datetime.now(UTC).strftime("%Y%m%d%H%M%S")+"-"+hashlib.sha256("|".join(a.direction).encode()).hexdigest()[:8]
  data={"schema":SCHEMA,"id":bid,"title":a.title,"project":str(project),"base_fingerprint":fingerprint(project),"directions":ds,"selected":None}
  save(boards(project)/(bid+".json"),data); print(json.dumps(data,indent=2)); return
 p,data=load(project,a.board); d=next((x for x in data["directions"] if x["name"]==a.direction),None)
 if not d: raise SystemExit("unknown direction")
 if a.cmd=="evidence":
  ev={}
  for key,val in (("screenshot",a.screenshot),("browser_proof",a.browser_proof),("score",a.score)):
   q=Path(val).resolve()
   if not q.is_file(): raise SystemExit("missing evidence: "+str(q))
   ev[key]={"path":str(q),"sha256":digest(q)}
  d["evidence"]=ev; save(p,data); print(json.dumps({"ok":True,"direction":d["name"],"evidence":ev},indent=2)); return
 if fingerprint(project)!=data["base_fingerprint"]: raise SystemExit("live project drifted since board creation; refusing stale selection")
 if not d.get("evidence"): raise SystemExit("direction lacks required evidence")
 for ev in d["evidence"].values():
  q=Path(ev["path"])
  if not q.is_file() or digest(q)!=ev["sha256"]: raise SystemExit("direction evidence missing or tampered")
 data["selected"]={"name":d["name"],"draft_id":d["draft_id"],"selected_at":datetime.now(UTC).isoformat(),"merge_performed":False}
 save(p,data); print(json.dumps({"ok":True,"selected":data["selected"],"note":"selection records intent only; accept draft separately"},indent=2))
if __name__=="__main__": main()
