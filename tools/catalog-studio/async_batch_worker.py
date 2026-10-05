from __future__ import annotations
import argparse, json, traceback
from datetime import datetime, timezone
from pathlib import Path
from controller import batch_process, load_profile

def now(): return datetime.now(timezone.utc).isoformat()
def readj(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def writej(p,v): p.write_text(json.dumps(v,indent=2),encoding='utf-8')
def patch(p,**kw):
    x=readj(p); x.update(kw,updated_at=now()); writej(p,x); return x

def main():
    a=argparse.ArgumentParser(); a.add_argument('--status',required=True); a.add_argument('--input-dir',required=True); a.add_argument('--output-dir',required=True); a.add_argument('--preset',default='warm-gallery'); a.add_argument('--model',default='u2netp'); a.add_argument('--profile'); x=a.parse_args(); st=Path(x.status)
    try:
        patch(st,status='running',started_at=now(),message='Processing catalog photo batch.')
        preset=x.preset; model=x.model; width=1600; height=2000
        if x.profile:
            cfg=load_profile(Path(x.profile)); preset=cfg['preset_id']; model=cfg['model']; width=cfg['width']; height=cfg['height']
        r=batch_process(Path(x.input_dir),Path(x.output_dir),preset_id=preset,model=model,width=width,height=height,force=True)
        patch(st,status='complete',completed_at=now(),summary=str(Path(x.output_dir)/'batch.catalog.json'),count=r['count'],passed=r['pass'],review_required=r['review_required'],errors=r['errors'],preset=preset,message='Catalog batch complete.')
    except Exception as e:
        patch(st,status='error',failed_at=now(),error=str(e),traceback=traceback.format_exc()[-4000:],message='Catalog batch failed.')
        raise
if __name__=='__main__': main()
