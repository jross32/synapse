"""Read-only Synapse ecosystem backup inventory. Never read file contents or secrets."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import stat

GENERATED = frozenset({
    "node_modules",".venv","venv","__pycache__",".pytest_cache",".mypy_cache",
    ".next",".nuxt","dist","dist-electron","build","out",".turbo","target",
    ".ruff_cache",".cache","release","release-candidate-ci",".playwright",
})
SYSTEM = frozenset({
    "AppData","Downloads","Desktop","Documents","Pictures","Videos","Music",
    "Favorites","Contacts","Links","Searches","Saved Games","OneDrive",
    "iCloudDrive","Creative Cloud Files","3D Objects",
})
def is_junction(path):
    try:
        s=path.lstat()
        return path.is_symlink() or bool(getattr(s,"st_file_attributes",0)&stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return True

def measure(root:Path, *, skip_generated=False):
    count=0; total=0; recovery=0; generated=0; skipped=0; errors=0
    stack=[(root,False)]
    while stack:
        directory,gen=stack.pop()
        try:
            with os.scandir(directory) as it:
                for item in it:
                    try:
                        p=Path(item.path)
                        if is_junction(p):
                            skipped+=1;continue
                        is_dir=item.is_dir(follow_symlinks=False)
                        if is_dir:
                            if skip_generated and (gen or item.name in GENERATED):
                                skipped+=1
                            else:
                                stack.append((p,gen or item.name in GENERATED))
                        elif item.is_file(follow_symlinks=False):
                            size=item.stat(follow_symlinks=False).st_size
                            total+=size;count+=1
                            if gen:generated+=size
                            else:recovery+=size
                    except (OSError,PermissionError):
                        errors+=1
        except (OSError,PermissionError):
            errors+=1
    return {"total_bytes":total,"recovery_bytes_upper_bound":recovery,
            "generated_bytes":generated,"files":count,"skipped_reparse":skipped,"errors":errors}

def git_info(path):
    if not (path/".git").exists(): return {"git":False}
    try:
        def git(*args):
            return subprocess.run(["git","-C",str(path),*args],capture_output=True,
                text=True,timeout=5,encoding="utf-8",errors="replace").stdout.strip()
        output=git("status","--porcelain","--untracked-files=no")
        branch=git("branch","--show-current")
        origin=git("remote")
        return {"git":True,"branch":branch,"tracked_changes":len(output.splitlines()) if output else 0,
                "has_remotes":bool(origin),"git_directory_is_file":(path/".git").is_file()}
    except (OSError, subprocess.TimeoutExpired):
        return {"git":True,"probe_error":True}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--home",type=Path,default=Path.home())
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--skip-generated",action="store_true",help="Fast estimate; do not descend into reproducible dependency/build folders.")
    a=p.parse_args()
    home=a.home
    records=[]
    for x in sorted(home.iterdir(),key=lambda p:p.name.casefold()):
        if not x.is_dir() or x.name in SYSTEM or x.name.startswith(".") or is_junction(x):
            continue
        g=({"git":(x/".git").exists(),"git_probe_skipped":True} if a.skip_generated else git_info(x))
        if not g.get("git") and x.name.casefold() not in {"synapse","whatifpulse","shelf pact"}:
            continue
        m=measure(x,skip_generated=a.skip_generated)
        records.append({"path":str(x),"name":x.name,**g,**m})
    states=[]
    for x in [
        home/"AppData"/"Roaming"/"Synapse",
        home/"AppData"/"Local"/"Synapse",
        home/"AppData"/"Local"/"Programs"/"Synapse",
    ]:
        if x.is_dir():states.append({"path":str(x),**measure(x)})
    output={"schema":1,"created_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
            "mode":"read_only_fast_excluding_generated" if a.skip_generated else "read_only_full","home":str(home),
            "repositories":records,"state_roots":states,
            "limits":["No remote cloud volume size included","Unregistered non-Git project folders not automatically included",
                      "Recovery bytes include source/history and are an upper bound, not compressed archive size",
                      "No database consistency snapshot or live-service quiescence performed",
                      "Git worktrees may share objects; raw totals double count shared repository data",
                      "When skip-generated is set, total_bytes excludes generated directories entirely"]}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(output,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"repositories":len(records),"repo_total_gib":round(sum(x["total_bytes"] for x in records)/2**30,2),
        "repo_recovery_upper_gib":round(sum(x["recovery_bytes_upper_bound"] for x in records)/2**30,2),
        "repo_generated_gib":round(sum(x["generated_bytes"] for x in records)/2**30,2),
        "state_roots":states,"largest":[{"name":r["name"],"gib":round(r["total_bytes"]/2**30,2),
          "recovery_gib":round(r["recovery_bytes_upper_bound"]/2**30,2)} for r in sorted(records,key=lambda v:-v["total_bytes"])[:18]],
        "output":str(a.output)},indent=2))
if __name__=="__main__":main()
