#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, shutil, tempfile
from datetime import UTC, datetime
from pathlib import Path
SCHEMA="ui-forge-version-ledger-v1"
EXCLUDE_DIRS={".git",".synapse","node_modules","dist","build",".next","coverage","__pycache__",".cache",".turbo"}
EXCLUDE_FILES={".env",".env.local",".env.production",".DS_Store","Thumbs.db"}
def relfiles(root):
 for p in sorted(root.rglob("*")):
  if not p.is_file(): continue
  rel=p.relative_to(root)
  if any(x in EXCLUDE_DIRS for x in rel.parts) or rel.name in EXCLUDE_FILES or rel.name.startswith(".env."): continue
  yield p,rel.as_posix()
def sha_bytes(b): return hashlib.sha256(b).hexdigest()
def snapshot(root):
 out={}
 for p,rel in relfiles(root):
  b=p.read_bytes(); out[rel]={"sha256":sha_bytes(b),"size":len(b)}
 return out
def fingerprint(files):
 h=hashlib.sha256()
 for rel,v in sorted(files.items()): h.update(rel.encode()); h.update(v["sha256"].encode())
 return h.hexdigest()
def ledger(root): return root/".synapse"/"ui-forge"/"version-ledger"
def load(root,bid):
 p=ledger(root)/"bookmarks"/(bid+".json")
 if not p.is_file(): raise SystemExit("bookmark not found")
 d=json.loads(p.read_text(encoding="utf-8")); return p,d
def copy_atomic(src,dst):
 dst.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(prefix=dst.name+".",dir=str(dst.parent)); os.close(fd)
 try: shutil.copy2(src,tmp); os.replace(tmp,dst)
 finally:
  if os.path.exists(tmp): os.unlink(tmp)
def main():
 ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest="cmd",required=True)
 c=sp.add_parser("create"); c.add_argument("project"); c.add_argument("--label",required=True)
 p=sp.add_parser("plan"); p.add_argument("project"); p.add_argument("bookmark"); p.add_argument("--path",action="append")
 r=sp.add_parser("restore"); r.add_argument("project"); r.add_argument("bookmark"); r.add_argument("--plan",required=True)
 a=ap.parse_args(); root=Path(a.project).resolve()
 if a.cmd=="create":
  files=snapshot(root); fp=fingerprint(files); bid=datetime.now(UTC).strftime("%Y%m%d%H%M%S")+"-"+fp[:10]
  store=ledger(root)/"objects"; store.mkdir(parents=True,exist_ok=True)
  for src,rel in relfiles(root):
   hv=files[rel]["sha256"]; obj=store/hv
   if not obj.exists(): copy_atomic(src,obj)
  data={"schema":SCHEMA,"id":bid,"label":a.label,"created_at":datetime.now(UTC).isoformat(),"fingerprint":fp,"files":files}
  bp=ledger(root)/"bookmarks"/(bid+".json"); bp.parent.mkdir(parents=True,exist_ok=True); bp.write_text(json.dumps(data,indent=2),encoding="utf-8")
  print(json.dumps({"ok":True,"bookmark":bid,"fingerprint":fp,"file_count":len(files)},indent=2)); return
 _,b=load(root,a.bookmark); current=snapshot(root)
 if a.cmd=="plan":
  wanted=set(a.path or b["files"].keys()); changes=[]
  for rel in sorted(wanted):
   target=b["files"].get(rel); cur=current.get(rel)
   if not target: raise SystemExit("path not present in bookmark: "+rel)
   if not cur or cur["sha256"]!=target["sha256"]: changes.append({"path":rel,"current_sha256":cur["sha256"] if cur else None,"restore_sha256":target["sha256"]})
  plan={"schema":"ui-forge-version-restore-plan-v1","bookmark":b["id"],"created_at":datetime.now(UTC).isoformat(),"project_fingerprint_at_plan":fingerprint(current),"changes":changes}
  raw=json.dumps(plan,sort_keys=True).encode(); plan["plan_sha256"]=sha_bytes(raw)
  out=ledger(root)/"plans"/(b["id"]+"-"+plan["plan_sha256"][:10]+".json"); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(plan,indent=2),encoding="utf-8")
  print(json.dumps({"ok":True,"plan":str(out),"changes":changes,"dry_run":True},indent=2)); return
 planp=Path(a.plan).resolve(); plan=json.loads(planp.read_text(encoding="utf-8")); sig=plan.pop("plan_sha256",None)
 if sha_bytes(json.dumps(plan,sort_keys=True).encode())!=sig: raise SystemExit("restore plan tampered")
 if plan["bookmark"]!=b["id"]: raise SystemExit("restore plan bookmark mismatch")
 if fingerprint(current)!=plan["project_fingerprint_at_plan"]: raise SystemExit("project drifted after restore plan; refusing")
 store=ledger(root)/"objects"; staged=[]
 for ch in plan["changes"]:
  obj=store/ch["restore_sha256"]
  if not obj.is_file() or sha_bytes(obj.read_bytes())!=ch["restore_sha256"]: raise SystemExit("bookmark object missing or tampered")
  staged.append((obj,root/ch["path"]))
 backup=ledger(root)/"restore-backups"/datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
 try:
  for _,dst in staged:
   if dst.exists(): copy_atomic(dst,backup/dst.relative_to(root))
  for obj,dst in staged: copy_atomic(obj,dst)
 except Exception:
  for _,dst in staged:
   old=backup/dst.relative_to(root)
   if old.exists(): copy_atomic(old,dst)
  raise
 print(json.dumps({"ok":True,"restored":[x["path"] for x in plan["changes"]],"backup":str(backup)},indent=2))
if __name__=="__main__": main()
