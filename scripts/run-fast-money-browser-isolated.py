import json,tempfile,shutil,subprocess,socket,time,urllib.request,pathlib,os,sys
root=pathlib.Path.cwd();source=root/'apps/fast-money-client-ops'
with tempfile.TemporaryDirectory(prefix='whatif-lifecycle-') as temp:
 dst=pathlib.Path(temp)
 for f in ['server.py','local_auth.py','stripe_payments.py','offer_catalog.py','followup_planner.py','fast_money.config.json','seed-data.json']:
  shutil.copy2(source/f,dst/f)
 shutil.copytree(source/'static',dst/'static')
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 c=json.loads((dst/'fast_money.config.json').read_text());c['expected_port']=port;(dst/'fast_money.config.json').write_text(json.dumps(c))
 p=subprocess.Popen([sys.executable,'server.py'],cwd=dst,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  for _ in range(40):
   try:
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1) as r:
     if json.load(r)['ok']:break
   except Exception:time.sleep(.15)
  else:raise RuntimeError('server did not start')
  env=os.environ.copy();env['DEMO_URL']=f'http://127.0.0.1:{port}';env['VIEWPORT']=os.environ.get('VIEWPORT', json.dumps(dict(width=int(__import__('sys').argv[1]),height=int(__import__('sys').argv[2])) if len(__import__('sys').argv)>2 else dict(width=1366,height=850)))
  r=subprocess.run(['node','scripts/verify-fast-money-workflow.cjs'],cwd=root,env=env,capture_output=True,text=True,timeout=70)
  print('exit',r.returncode,'stdout',r.stdout,'stderr',r.stderr[:2500]);sys.exit(r.returncode)
 finally:p.terminate();p.wait(timeout=5)
