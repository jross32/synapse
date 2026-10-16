"""Read-only Synapse backup dependency and restore-readiness inventory.

The inventory records path names and approximate bytes, never file contents or
secret values. No backup is made here. Its test-restore exercises only synthetic
files in a temporary directory and does not touch live Synapse data.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

EXCLUDED = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".next",
            "dist", "build", ".turbo", ".cache", "coverage", "target", ".gradle"}
SENSITIVE_NAMES = {"credentials", "tokens", "secrets", "auth", "private", "key", "cloudflared"}
EXTRA = [
    ("Synapse roaming application data", "AppData/Roaming/Synapse", "required_sensitive"),
    ("Synapse local application data", "AppData/Local/Synapse", "required_sensitive"),
    ("Installed desktop program", "AppData/Local/Programs/Synapse", "reinstallable"),
    ("Synapse user profile configuration", ".synapse", "required_sensitive"),
    ("Synapse backup keys", ".synapse-backup-keys", "required_sensitive"),
    ("Cloudflare tunnel configuration", ".cloudflared", "required_sensitive"),
    ("Playwright authenticated browser", ".playwright-mcp", "required_sensitive"),
    ("PM2 service state", ".pm2", "service_state"),
]
CLOUD_PROVIDERS = [
    {"name":"Railway accounts backend and cloud database","kind":"hosted_db_service","bytes":"unknown","action":"export via provider and test import"},
    {"name":"GitHub repositories and Actions releases","kind":"version_control_and_artifacts","bytes":"unknown","action":"mirror repos and capture release assets separately"},
    {"name":"Cloudflare DNS/tunnel/access configuration","kind":"routing_and_identity","bytes":"unknown","action":"document tunnel names and recoverable settings without exposing tokens"},
    {"name":"ChatGPT Synapse MCP connector registration","kind":"account_connection","bytes":"unknown","action":"verify connection endpoint and token continuity through owner-authorized test"},
    {"name":"OAuth-linked cloud providers","kind":"external_accounts","bytes":"unknown","action":"inventory provider grants and validate reconnection; never export refresh tokens in plaintext"},
]

def scan_folder(root: Path, *, exclusions=frozenset(), file_budget=250000):
    """OS walk avoiding symlinks/junctions; no reads of contents."""
    if not root.exists():
        return {"exists":False,"bytes":0,"files":0,"excluded_bytes":"unmeasured","complete":True}
    total=files=0
    complete=True
    skipped=[]
    stack=[root]
    while stack:
        current=stack.pop()
        try:
            with os.scandir(current) as it:
                for item in it:
                    try:
                        if item.is_symlink():
                            continue
                        if item.is_dir(follow_symlinks=False):
                            if item.name.lower() in exclusions or bool(getattr(item.stat(follow_symlinks=False),"st_file_attributes",0)&0x400):
                                skipped.append(item.name)
                            else:
                                stack.append(Path(item.path))
                        elif item.is_file(follow_symlinks=False):
                            total += item.stat(follow_symlinks=False).st_size
                            files += 1
                            if files >= file_budget:
                                complete=False
                                stack=[]
                                break
                    except (OSError, PermissionError):
                        complete=False
        except (OSError, PermissionError):
            complete=False
    return {"exists":True,"bytes":total,"files":files,"excluded_names":sorted(set(skipped)),
            "complete":complete}

def collect(registry: Path, home: Path, output: Path):
    source=json.loads(registry.read_text(encoding="utf-8-sig"))
    projects=source["projects"]
    candidates={}
    for project in projects:
        raw=project.get("path")
        if not raw:continue
        path=Path(raw).resolve(strict=False)
        key=os.path.normcase(str(path)).lower()
        item=candidates.setdefault(key,{"path":str(path),"projects":[],"category":"registered_project"})
        item["projects"].append(project.get("id") or project.get("name") or "?")
    # Avoid double-counting nested project folders; record as nested aliases.
    roots=sorted(candidates.values(),key=lambda row:len(Path(row["path"]).parts))
    unique=[]
    nested=[]
    for item in roots:
        path=Path(item["path"])
        parent=next((x for x in unique if path == Path(x["path"]) or Path(x["path"]) in path.parents),None)
        if parent:
            nested.append({"path":str(path),"included_by":parent["path"],"projects":item["projects"]})
        else:
            unique.append(item)
    # Main repo exists even if not registered as its own project.
    main=(home/"synapse").resolve(strict=False)
    if not any(main == Path(x["path"]) or Path(x["path"]) in main.parents for x in unique):
        unique.append({"path":str(main),"projects":["synapse-main-repository"],"category":"source_and_local_data"})
    # Remove any roots now included by main, so count only once.
    dedup=[]
    for item in sorted(unique,key=lambda x:len(Path(x["path"]).parts)):
        path=Path(item["path"])
        parent=next((x for x in dedup if path == Path(x["path"]) or Path(x["path"]) in path.parents),None)
        if parent:nested.append({"path":str(path),"included_by":parent["path"],"projects":item["projects"]})
        else:dedup.append(item)
    roots=dedup
    # Keep config paths separate unless they're already inside a project root.
    for title,rel,category in EXTRA:
        path=(home/rel).resolve(strict=False)
        parent=next((x for x in roots if path==Path(x["path"]) or Path(x["path"]) in path.parents),None)
        if parent:nested.append({"path":str(path),"included_by":parent["path"],"projects":[title]})
        else:roots.append({"path":str(path),"projects":[title],"category":category})
    for entry in roots:
        scan=scan_folder(Path(entry["path"]),exclusions=EXCLUDED)
        entry.update(scan)
        entry["required_backup_bytes_lower_bound"]=scan["bytes"] if entry["category"]!="reinstallable" else 0
    total=sum(x["bytes"] for x in roots)
    required=sum(x["required_backup_bytes_lower_bound"] for x in roots)
    report={"timestamp_utc":datetime.now(timezone.utc).isoformat(),"source":"live Synapse registry + known local app/config paths",
        "registered_projects":len(projects),"unique_counted_roots":len(roots),
        "nested_paths_not_double_counted":nested,"roots":roots,
        "local_total_bytes_excluding_regenerable_dirs":total,
        "required_backup_bytes_lower_bound":required,
        "partial":not all(x["complete"] for x in roots),
        "excluded_directory_names":sorted(EXCLUDED),
        "cloud_services":CLOUD_PROVIDERS,
        "caveats":["Cloud database/export sizes are not included; no cloud data was accessed.",
                   "Excluded dependency/build/cache directories and Git object histories may add material bytes.",
                   "Paths outside registered projects and known Synapse config roots may be missing.",
                   "No file content, secrets, database rows, or credentials were read."]}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report

def synthetic_restore_test():
    with tempfile.TemporaryDirectory(prefix="synapse-restore-proof-") as tmp:
        root=Path(tmp);original=root/"original"; restored=root/"restored";original.mkdir()
        (original/"settings.json").write_text('{"version":1,"device":"synthetic"}',encoding="utf-8")
        (original/"database.sqlite").write_bytes(b"fake synthetic data only\x00\x01")
        shutil.copytree(original,restored)
        def manifest(folder):
            return {x.relative_to(folder).as_posix():hashlib.sha256(x.read_bytes()).hexdigest()
                    for x in folder.rglob("*") if x.is_file()}
        assert manifest(original)==manifest(restored)
        assert len(manifest(restored))==2
        return {"status":"synthetic_restore_passed","files":2,
                "live_data_restored":False,"cloud_restore_verified":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--registry",type=Path,required=True)
    p.add_argument("--home",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    r=collect(args.registry,args.home,args.output)
    print(json.dumps({"roots":r["unique_counted_roots"],"projects":r["registered_projects"],
        "measured_gib":round(r["local_total_bytes_excluding_regenerable_dirs"]/1073741824,2),
        "required_lower_bound_gib":round(r["required_backup_bytes_lower_bound"]/1073741824,2),
        "partial":r["partial"],"restore_test":synthetic_restore_test()},indent=2))

if __name__=="__main__":main()
