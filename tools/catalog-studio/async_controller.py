from __future__ import annotations
import argparse, json, os, subprocess, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path

TOOL_DIR=Path(__file__).resolve().parent
REPO_ROOT=TOOL_DIR.parent.parent
DATA_ROOT=REPO_ROOT/'data'/'catalog-studio'
LATEST=DATA_ROOT/'latest.json'
def worker_python():
    candidates=[REPO_ROOT/'.venv'/'Scripts'/'python.exe', REPO_ROOT/'.venv'/'bin'/'python']
    return next((x for x in candidates if x.exists()), Path(sys.executable))
PYTHON=worker_python()
WORKER=TOOL_DIR/'async_worker.py'
BATCH_WORKER=TOOL_DIR/'async_batch_worker.py'

def now(): return datetime.now(timezone.utc).isoformat()
def writej(p,v): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(v,indent=2),encoding='utf-8')
def readj(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def submit(input_path, output_path, preset, model, profile=None):
    rid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
    rd=DATA_ROOT/rid; status=rd/'status.json'; rd.mkdir(parents=True,exist_ok=True)
    state={'run_id':rid,'status':'queued','input':input_path,'output':output_path,'preset':preset,'model':model,'profile':profile,'created_at':now(),'status_file':str(status)}
    writej(status,state); writej(LATEST,{'run_id':rid,'status_file':str(status)})
    args=[str(PYTHON),str(WORKER),'--status',str(status),'--input',input_path,'--output',output_path,'--preset',preset,'--model',model]
    if profile: args += ['--profile',profile]
    flags=0
    if os.name=='nt': flags=subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.DETACHED_PROCESS|subprocess.CREATE_NO_WINDOW
    proc=subprocess.Popen(args,cwd=str(REPO_ROOT),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags,close_fds=True)
    state.update(status='starting',worker_pid=proc.pid,worker_started_at=now()); writej(status,state)
    return state

def submit_batch(input_dir, output_dir, preset, model, profile=None):
    rid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
    rd=DATA_ROOT/rid; status=rd/'status.json'; rd.mkdir(parents=True,exist_ok=True)
    state={'run_id':rid,'status':'queued','kind':'batch','input_dir':input_dir,'output_dir':output_dir,'preset':preset,'model':model,'profile':profile,'created_at':now(),'status_file':str(status)}
    writej(status,state); writej(LATEST,{'run_id':rid,'status_file':str(status)})
    args=[str(PYTHON),str(BATCH_WORKER),'--status',str(status),'--input-dir',input_dir,'--output-dir',output_dir,'--preset',preset,'--model',model]
    if profile: args += ['--profile',profile]
    flags=0
    if os.name=='nt': flags=subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.DETACHED_PROCESS|subprocess.CREATE_NO_WINDOW
    proc=subprocess.Popen(args,cwd=str(REPO_ROOT),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags,close_fds=True)
    state.update(status='starting',worker_pid=proc.pid,worker_started_at=now()); writej(status,state)
    return state

def status():
    if not LATEST.exists(): return {'status':'none','message':'No Catalog Studio runs yet.'}
    x=readj(LATEST); p=Path(x['status_file']); return readj(p) if p.exists() else {**x,'status':'missing'}

def main():
    a=argparse.ArgumentParser(); sub=a.add_subparsers(dest='cmd',required=True)
    s=sub.add_parser('submit'); s.add_argument('input'); s.add_argument('output'); s.add_argument('--preset',default='warm-gallery'); s.add_argument('--model',default='u2netp'); s.add_argument('--profile')
    b=sub.add_parser('submit-batch'); b.add_argument('input_dir'); b.add_argument('output_dir'); b.add_argument('--preset',default='warm-gallery'); b.add_argument('--model',default='u2netp'); b.add_argument('--profile')
    sub.add_parser('status')
    x=a.parse_args()
    if x.cmd=='submit': result=submit(x.input,x.output,x.preset,x.model,x.profile)
    elif x.cmd=='submit-batch': result=submit_batch(x.input_dir,x.output_dir,x.preset,x.model,x.profile)
    else: result=status()
    print(json.dumps(result,indent=2))
if __name__=='__main__': main()
