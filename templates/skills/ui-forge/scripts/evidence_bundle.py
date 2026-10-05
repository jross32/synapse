#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, shutil
from datetime import UTC, datetime
from pathlib import Path
SCHEMA="ui-forge-evidence-bundle-v1"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def source_fp(root):
 h=hashlib.sha256()
 skip={".git",".synapse","node_modules","dist","build",".next","coverage","__pycache__"}
 for p in sorted(root.rglob("*")):
  if not p.is_file(): continue
  rel=p.relative_to(root)
  if any(x in skip for x in rel.parts): continue
  h.update(rel.as_posix().encode()); h.update(sha(p).encode())
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest="cmd",required=True)
 c=sp.add_parser("create"); c.add_argument("project"); c.add_argument("--label",required=True); c.add_argument("--artifact",action="append",required=True); c.add_argument("--claim",action="append",default=[])
 v=sp.add_parser("verify"); v.add_argument("bundle")
 a=ap.parse_args()
 if a.cmd=="verify":
  bp=Path(a.bundle).resolve(); d=json.loads((bp/"manifest.json").read_text(encoding="utf-8")); bad=[]
  for x in d["artifacts"]:
   p=bp/x["stored_as"]
   if not p.is_file() or sha(p)!=x["sha256"]: bad.append(x["name"])
  manifest_hash=d.pop("manifest_sha256",None)
  calc=hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()
  print(json.dumps({"ok":not bad and calc==manifest_hash,"bad_artifacts":bad,"manifest_hash_ok":calc==manifest_hash},indent=2)); raise SystemExit(0 if not bad and calc==manifest_hash else 1)
 root=Path(a.project).resolve(); bid=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")+"-"+hashlib.sha256(a.label.encode()).hexdigest()[:8]
 bp=root/".synapse"/"ui-forge"/"evidence"/bid; apath=bp/"artifacts"; apath.mkdir(parents=True)
 arts=[]
 for i,val in enumerate(a.artifact):
  src=Path(val).resolve()
  if not src.is_file(): raise SystemExit("missing artifact: "+str(src))
  dest=apath/(f"{i:02d}-"+src.name); shutil.copy2(src,dest)
  arts.append({"name":src.name,"source":str(src),"stored_as":dest.relative_to(bp).as_posix(),"sha256":sha(dest),"size":dest.stat().st_size})
 d={"schema":SCHEMA,"id":bid,"label":a.label,"created_at":datetime.now(UTC).isoformat(),"project_source_fingerprint":source_fp(root),"artifacts":arts,"claims":a.claim}
 d["manifest_sha256"]=hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()
 (bp/"manifest.json").write_text(json.dumps(d,indent=2),encoding="utf-8")
 print(json.dumps({"ok":True,"bundle":str(bp),"artifact_count":len(arts),"source_fingerprint":d["project_source_fingerprint"]},indent=2))
if __name__=="__main__": main()
