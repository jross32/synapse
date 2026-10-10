#!/usr/bin/env node
// Synapse Visual QA full scenario orchestrator. One browser process per scenario,
// hard watchdog and optionally approved-reference screenshot comparison.
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn,spawnSync} from 'node:child_process';
const manifestPath=path.resolve(process.argv[2]||'');
if(!process.argv[2]){console.error('Usage: node scripts/visual-qa-suite.mjs manifest.json [report-dir]');process.exit(2)}
const m=JSON.parse(await fs.readFile(manifestPath,'utf8'));
if(!m.baseUrl||!Array.isArray(m.scenarios)||!m.scenarios.length||m.scenarios.length>50)throw new Error('Manifest needs baseUrl and 1-50 scenarios');
const base=new URL(m.baseUrl);
if(!['http:','https:'].includes(base.protocol))throw new Error('Only HTTP(S) baseUrl supported');
const output=path.resolve(process.argv[3]||'visual-qa-suite-results');
await fs.mkdir(output,{recursive:true});
const ROOT=path.resolve(import.meta.dirname,'..');
const report={url:base.origin,generated:new Date().toISOString(),scenarios:[],notes:['A PASS only covers declared scenarios and checks; it does not prove full app coverage.','Screenshots are not visual-fidelity proof without an approved matched-size baseline.']};
function run(command,args,{cwd=ROOT,timeout=30000}={}){
 return new Promise(resolve=>{
  const p=spawn(command,args,{cwd,windowsHide:true,stdio:['ignore','pipe','pipe']});
  let stdout='',stderr='',ended=false,timedOut=false;
  const cap=(a,v)=>(a+v).slice(-6000);
  p.stdout.on('data',x=>{stdout=cap(stdout,x.toString())});
  p.stderr.on('data',x=>{stderr=cap(stderr,x.toString())});
  const timer=setTimeout(()=>{
   timedOut=true;
   if(process.platform==='win32') {
    try{spawnSync('taskkill',['/T','/F','/PID',String(p.pid)],{timeout:3500,windowsHide:true,stdio:'ignore'})}catch{}
   }
   try{p.kill('SIGKILL')}catch{}
  },timeout);
  function finish(code,error){if(ended)return;ended=true;clearTimeout(timer);resolve({code,error:error?String(error):null,timedOut,stdout,stderr})}
  p.on('error',err=>finish(-1,err));
  p.on('close',code=>finish(code));
 });
}
for(let i=0;i<m.scenarios.length;i++){
 const scenario=m.scenarios[i];
 const folder=path.join(output,'scenario-'+String(i+1).padStart(2,'0'));
 await fs.mkdir(folder,{recursive:true});
 const limit=Math.min(55000,Math.max(10000,Number(scenario.timeoutMs)||35000));
 const worker=await run(process.execPath,[path.join(ROOT,'scripts','visual-qa-e2e-worker.mjs'),manifestPath,String(i),folder],{timeout:limit});
 let result;
 try{result=JSON.parse(await fs.readFile(path.join(folder,'result.json'),'utf8'))}
 catch{result={name:scenario.name||'unnamed',status:'BLOCKED',errors:[worker.timedOut?'Browser watchdog timed out':'Browser worker did not produce a result'],steps:[]}};
 if(worker.timedOut){result.status='BLOCKED';result.errors.push('Process-level watchdog timed out after '+limit+'ms')}
 if(worker.error){result.status='BLOCKED';result.errors.push(worker.error)}
 if(result.screenshot&&scenario.baseline){
  const baseline=path.resolve(path.dirname(manifestPath),scenario.baseline);
  const actual=path.join(folder,result.screenshot);
  const py=process.env.SYNAPSE_PYTHON||path.join(ROOT,'.venv','Scripts','python.exe');
  const comparison=await run(py,[path.join(ROOT,'tools','ui_lab_reference_compare.py'),baseline,actual,'--output',path.join(folder,'comparison')],{timeout:16000});
  try{result.reference=JSON.parse(await fs.readFile(path.join(folder,'comparison','report.json'),'utf8'))}
  catch{result.reference={status:'BLOCKED',reason:comparison.timedOut?'Comparison timed out':'Comparison produced no report'}}
  if(result.reference.status!=='PASS')result.status=result.reference.status==='BLOCKED'?'BLOCKED':'FAIL';
 }else if(scenario.requireVisualMatch===true){
  result.reference={status:'BLOCKED',reason:'Approved baseline is required for this scenario'};
  result.status='BLOCKED';
 }
 report.scenarios.push({folder:path.relative(output,folder),...result});
 console.log((i+1)+'/'+m.scenarios.length+' '+(scenario.name||'unnamed')+': '+result.status+' ('+(result.steps?.length||0)+' steps)');
}
report.counts={passed:report.scenarios.filter(x=>x.status==='PASS').length,failed:report.scenarios.filter(x=>x.status==='FAIL').length,blocked:report.scenarios.filter(x=>x.status==='BLOCKED').length};
await fs.writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n','utf8');
console.log(JSON.stringify({report:path.join(output,'report.json'),...report.counts},null,2));
process.exitCode=report.counts.failed||report.counts.blocked?1:0;
