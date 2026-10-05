#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re
from datetime import UTC, datetime
from pathlib import Path
SCHEMA="ui-forge-review-pins-v1"
SOURCE=re.compile(r"^(?P<file>.+?):(?P<line>[1-9][0-9]*):(?P<col>[1-9][0-9]*)$")
def store(root): return root/".synapse"/"ui-forge"/"review-pins.json"
def load(root):
 p=store(root)
 return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"schema":SCHEMA,"pins":[]}
def save(root,d): p=store(root); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(d,indent=2),encoding="utf-8")
def source_context(root,source):
 m=SOURCE.match(source)
 if not m: raise SystemExit("invalid source pointer")
 f=(root/m["file"]).resolve()
 try: f.relative_to(root)
 except ValueError: raise SystemExit("source path escapes project")
 if not f.is_file(): raise SystemExit("source file missing")
 lines=f.read_text(encoding="utf-8").splitlines(); n=int(m["line"])
 if n>len(lines): raise SystemExit("source line missing")
 text=lines[n-1].strip(); return m["file"],text,hashlib.sha256(text.encode()).hexdigest()
def main():
 ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest="cmd",required=True)
 a=sp.add_parser("add"); a.add_argument("project"); a.add_argument("--source",required=True); a.add_argument("--ui-id",required=True); a.add_argument("--note",required=True)
 r=sp.add_parser("resolve"); r.add_argument("project")
 ns=ap.parse_args(); root=Path(ns.project).resolve(); data=load(root)
 if ns.cmd=="add":
  file,text,h=source_context(root,ns.source); pid=hashlib.sha256((ns.ui_id+ns.source+ns.note).encode()).hexdigest()[:12]
  pin={"id":pid,"ui_id":ns.ui_id,"source":ns.source,"file":file,"source_line_hash":h,"source_line_excerpt":text,"note":ns.note,"created_at":datetime.now(UTC).isoformat()}
  data["pins"].append(pin); save(root,data); print(json.dumps({"ok":True,"pin":pin},indent=2)); return
 results=[]
 for pin in data["pins"]:
  f=root/pin["file"]; matches=[]
  if f.is_file():
   for i,line in enumerate(f.read_text(encoding="utf-8").splitlines(),1):
    if hashlib.sha256(line.strip().encode()).hexdigest()==pin["source_line_hash"]: matches.append(i)
  status="resolved" if len(matches)==1 else ("ambiguous" if len(matches)>1 else "orphaned")
  results.append({"id":pin["id"],"ui_id":pin["ui_id"],"status":status,"source":f'{pin["file"]}:{matches[0]}:1' if len(matches)==1 else None,"matches":matches})
 print(json.dumps({"ok":True,"results":results},indent=2))
if __name__=="__main__": main()
