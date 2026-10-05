#!/usr/bin/env python3
import json, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
EDITOR=ROOT/'templates/skills/ui-forge/scripts/direct_ast_edit.mjs'
def run(src,op):
  with tempfile.TemporaryDirectory(prefix='uif-mixed-') as td:
    root=Path(td); (root/'src').mkdir(); f=root/'src/App.jsx'; f.write_text(src,encoding='utf-8')
    col=src.index('<button')+1; e={'source':f'src/App.jsx:1:{col}','operation':op}; ep=root/'edit.json'; ep.write_text(json.dumps(e),encoding='utf-8')
    p=subprocess.run(['node',str(EDITOR),str(root),str(ep)],capture_output=True,text=True); out=f.read_text(encoding='utf-8')
    try: payload=json.loads(p.stdout)
    except: payload={'ok':False,'error':p.stdout+p.stderr}
    return p.returncode,payload,out
checks={}
src='export function A(){return <button><span aria-hidden="true">+</span> Add item <kbd>N</kbd></button>}'
code,p,out=run(src,{'type':'set_text_segment','segment_index':0,'expected_text':'Add item','value':'Add listing'})
checks['icon_text_kbd_edit_succeeds']=code==0 and p.get('ok') is True
checks['nested_elements_preserved']= '<span aria-hidden="true">+</span>' in out and '<kbd>N</kbd>' in out
checks['surrounding_whitespace_preserved']='</span> Add listing <kbd>' in out
checks['only_target_text_changed']=out==src.replace('Add item','Add listing')
code,p,out=run(src,{'type':'set_text_segment','segment_index':0,'expected_text':'Wrong','value':'Launch'})
checks['stale_expected_text_refused']=code!=0 and out==src and 'expected_text' in p.get('error','')
code,p,out=run(src,{'type':'set_text_segment','segment_index':4,'value':'Launch'})
checks['invalid_segment_refused']=code!=0 and out==src
code,p,out=run(src,{'type':'set_text_segment','segment_index':0,'value':'<b>Launch</b>'})
checks['structural_text_refused']=code!=0 and out==src
src2='export function B(){return <button> Save <span>/</span> Publish </button>}'
code,p,out=run(src2,{'type':'set_text_segment','segment_index':1,'expected_text':'Publish','value':'Deploy'})
checks['second_static_segment_supported']=code==0 and out==src2.replace('Publish','Deploy')
result={'schema':'ui-forge-mixed-content-text-benchmark-v1','checks':checks,'passed':sum(checks.values()),'total':len(checks),'overall_pass':all(checks.values()),'claims':{'safe_mixed_content_static_text_segment_edit':all(checks.values()),'not_a_full_ui_forge_or_lovable_claim':True}}
print(json.dumps(result,indent=2)); raise SystemExit(0 if result['overall_pass'] else 1)