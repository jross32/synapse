"""Read-only registered Synapse project and cloud dependency inventory.

Never opens environment variable files, private keys, tokens, databases, or
application data. Sizes are logical filesystem sizes, not cloud storage quotas.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from synapse_backup_inventory import measure, is_junction

GENERATED_HINTS = {"node_modules",".venv","venv","dist","dist-electron","build","release"}
DATA_HINTS = {".db",".sqlite",".sqlite3",".jsonl"}
CLOUD = {
    "railway": "Railway deployment, service variables, hosted databases and volumes",
    "cloudflared": "Cloudflare tunnel and DNS configuration",
    "github": "GitHub repositories, Actions artifacts, Secrets, Releases",
    "onedrive": "OneDrive or Microsoft account storage",
    "google_drive": "Google Drive and OAuth grants",
    "s3": "S3-compatible object storage",
    "supabase": "Supabase hosted database/storage",
    "firebase": "Firebase hosted data",
    "dropbox": "Dropbox account data",
}
def build_report(registry: Path, home: Path) -> dict:
    data=json.loads(registry.read_text(encoding="utf-8-sig"))
    projects=data["projects"]
    paths={}
    for project in projects:
        candidate=Path(project["path"].replace("/", "\\"))
        key=str(candidate).casefold()
        paths.setdefault(key, {"path":candidate,"ids":[]})["ids"].append(project["id"])
    measured=[]
    for value in sorted(paths.values(),key=lambda x:str(x["path"]).casefold()):
        path=value["path"]
        if not path.exists():
            measured.append({"path":str(path),"project_count":len(value["ids"]),"available":False})
            continue
        if not path.is_dir() or is_junction(path):
            measured.append({"path":str(path),"project_count":len(value["ids"]),"available":False,"reason":"not-a-regular-directory"})
            continue
        metric=measure(path,skip_generated=True)
        measured.append({"path":str(path),"project_count":len(value["ids"]),"available":True,**metric})
    # Avoid double counting nested registered projects in the summed upper bound.
    present=[r for r in measured if r.get("available")]
    top_roots=[]
    for r in sorted(present,key=lambda x:(len(Path(x["path"]).parts),x["path"].casefold())):
        rp=Path(r["path"])
        if any(rp==Path(p["path"]) or Path(p["path"]) in rp.parents for p in top_roots):
            r["nested_in_other_registered_root"]=True
        else:
            top_roots.append(r)
    system=[]
    state_paths=[
        home/"AppData"/"Roaming"/"Synapse",
        home/"AppData"/"Local"/"Synapse",
        home/"AppData"/"Local"/"Programs"/"Synapse",
        home/".synapse",
        home/".cloudflared",
        home/".playwright-mcp",
        home/".codex",
        home/".claude",
    ]
    for path in state_paths:
        if path.is_dir() and not is_junction(path):
            system.append({"path":str(path),**measure(path,skip_generated=True),"review_classification":"sensitive_backup_candidate"})
    cloud=[{"provider":k,"dependency":v,"local_config_indicators_only":True,
            "remote_size_bytes":None,"remote_backup_verified":False} for k,v in CLOUD.items()]
    return {
        "schema":1, "mode":"read_only_no_secret_contents","registered_projects":len(projects),
        "unique_registered_paths":len(paths),"available_paths":len(present),
        "missing_paths":len(measured)-len(present),
        "top_level_registered_paths":len(top_roots),
        "registered_recovery_bytes_upper_bound":sum(x["recovery_bytes_upper_bound"] for x in top_roots),
        "state_recovery_bytes_upper_bound":sum(x["recovery_bytes_upper_bound"] for x in system),
        "project_roots":measured,"state_roots":system,"cloud_dependency_checklist":cloud,
        "caveats":[
            "Cloud storage, Railway DBs, volumes, secrets, DNS and OAuth grants have not been remotely exported or sized",
            "Additional unregistered local folders or cloud accounts may exist",
            "Nested roots excluded from aggregate project total; state locations could overlap projects",
            "Generated dependency/build folders excluded; these upper bounds are not compressed sizes",
            "Live SQLite WAL consistency and actual credential decryptability not established",
            "Restore tested with synthetic records only until a separately approved encrypted snapshot is performed",
        ],
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--registry",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--home",type=Path,default=Path.home())
    a=p.parse_args()
    report=build_report(a.registry,a.home)
    a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({
        "registered_projects":report["registered_projects"],
        "available_paths":report["available_paths"],
        "missing_paths":report["missing_paths"],
        "top_level_roots":report["top_level_registered_paths"],
        "projects_recovery_upper_gib":round(report["registered_recovery_bytes_upper_bound"]/2**30,3),
        "state_recovery_upper_gib":round(report["state_recovery_bytes_upper_bound"]/2**30,3),
        "largest_roots":[{"name":Path(x["path"]).name,"gib":round(x.get("recovery_bytes_upper_bound",0)/2**30,2)} for x in sorted(report["project_roots"],key=lambda y:-y.get("recovery_bytes_upper_bound",0))[:15]],
        "output":str(a.output)},indent=2))
if __name__=="__main__": main()
