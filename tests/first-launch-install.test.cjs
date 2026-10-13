const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const ts=require('typescript');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../electron/first-launch-install.ts'),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;
const moduleExports={};
vm.runInNewContext(code,{exports:moduleExports,require});
const {classifyInstallation,readInstallDisposition,installMarkerPath}=moduleExports;
test('new install with no userData is classified new',()=>{
 const dir=path.join(os.tmpdir(),'synapse-first-launch-nonexistent-'+process.pid);
 assert.equal(classifyInstallation(dir,true),'new');
});
test('existing installation data prevents surprise onboarding',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'synapse-existing-'));
 try{fs.mkdirSync(path.join(dir,'data'));assert.equal(classifyInstallation(dir,true),'existing');}
 finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test('dev mode skips first launch onboarding',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'synapse-dev-'));
 try{assert.equal(classifyInstallation(dir,false),'existing');}
 finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test('persisted install disposition survives daemon creating data later',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'synapse-fresh-'));
 try{
 assert.equal(classifyInstallation(dir,true),'new');
 fs.writeFileSync(installMarkerPath(dir),JSON.stringify({version:1,disposition:'new'}));
 fs.mkdirSync(path.join(dir,'data'));
 assert.equal(readInstallDisposition(dir,true),'new');
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test('existing marker stays existing after upgrade',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'synapse-upgrade-'));
 try{fs.writeFileSync(installMarkerPath(dir),JSON.stringify({version:1,disposition:'existing'}));assert.equal(readInstallDisposition(dir,true),'existing');}
 finally{fs.rmSync(dir,{recursive:true,force:true});}
});
