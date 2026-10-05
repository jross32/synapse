#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re, shutil
from datetime import UTC,datetime
from pathlib import Path
SEMVER=re.compile(r"^\d+\.\d+\.\d+$"); SCHEMA="ui-forge-design-system-registry-v1"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def registry(root): return root/".synapse"/"ui-forge"/"design-systems"
def main():
 ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest="cmd",required=True)
 pub=sp.add_parser("publish"); pub.add_argument("project"); pub.add_argument("--name",required=True); pub.add_argument("--version",required=True); pub.add_argument("--theme",required=True); pub.add_argument("--components",required=True); pub.add_argument("--guidelines",required=True)
 pin=sp.add_parser("pin"); pin.add_argument("project"); pin.add_argument("--name",required=True); pin.add_argument("--version",required=True)
 diff=sp.add_parser("diff"); diff.add_argument("project"); diff.add_argument("--name",required=True); diff.add_argument("old"); diff.add_argument("new")
 a=ap.parse_args(); root=Path(a.project).resolve(); base=registry(root)
 if not SEMVER.match(a.version if a.cmd!="diff" else a.old): raise SystemExit("semantic version required")
 if a.cmd=="publish":
  dest=base/a.name/a.version
  if dest.exists(): raise SystemExit("version already exists; immutable registry refuses overwrite")
  files={}
  for key,val in (("theme",a.theme),("components",a.components),("guidelines",a.guidelines)):
   src=Path(val).resolve()
   if not src.is_file(): raise SystemExit("missing "+key)
   dest.mkdir(parents=True,exist_ok=True); out=dest/src.name; shutil.copy2(src,out); files[key]={"path":out.name,"sha256":sha(out)}
  d={"schema":SCHEMA,"name":a.name,"version":a.version,"published_at":datetime.now(UTC).isoformat(),"files":files}; d["manifest_sha256"]=hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()
  (dest/"manifest.json").write_text(json.dumps(d,indent=2),encoding="utf-8"); print(json.dumps({"ok":True,"name":a.name,"version":a.version},indent=2)); return
 if a.cmd=="pin":
  dest=base/a.name/a.version; mp=dest/"manifest.json"
  if not mp.is_file(): raise SystemExit("design system version not found")
  d=json.loads(mp.read_text()); sig=d.pop("manifest_sha256",None)
  if hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()!=sig: raise SystemExit("manifest tampered")
  for x in d["files"].values():
   if sha(dest/x["path"])!=x["sha256"]: raise SystemExit("design system artifact tampered")
  pins=base/"pins.json"; state=json.loads(pins.read_text()) if pins.is_file() else {"schema":"ui-forge-design-system-pins-v1","pins":{}}
  state["pins"][a.name]={"version":a.version,"manifest_sha256":sig}; pins.parent.mkdir(parents=True,exist_ok=True); pins.write_text(json.dumps(state,indent=2),encoding="utf-8")
  print(json.dumps({"ok":True,"pinned":state["pins"][a.name]},indent=2)); return
 if not SEMVER.match(a.new): raise SystemExit("semantic version required")
 def man(v):
  p=base/a.name/v/"manifest.json"
  if not p.is_file(): raise SystemExit("version not found: "+v)
  return json.loads(p.read_text())
 x,y=man(a.old),man(a.new); changed=[k for k in x["files"] if x["files"][k]["sha256"]!=y["files"].get(k,{}).get("sha256")]
 print(json.dumps({"ok":True,"name":a.name,"from":a.old,"to":a.new,"changed":changed},indent=2))
if __name__=="__main__": main()
