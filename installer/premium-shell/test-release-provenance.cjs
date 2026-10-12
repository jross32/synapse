'use strict';
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'release-gate.cjs'),'utf8');
function run(changes={}){
 const process={exitCode:0},version='0.2.219',hash='a'.repeat(64),source='source';
 const payload={version,filename:'Synapse Setup '+version+'.exe',sha256:hash};
 const receipt={version,sourceDigest:source,payloadSha256:hash,daemonSha256:hash,wrapperSha256:hash,...changes.receipt};
 const pkg={version:changes.shellVersion||version,build:{extraResources:[{to:'synapse-payload/'+payload.filename}]}};
 const mockFs={
  existsSync:file=>!(changes.missingReceipt&&file.endsWith('build-source.json')),
  readdirSync:()=>['Synapse Premium Setup '+version+'.exe'],
  readFileSync:file=>{
   if(file.endsWith('__init__.py'))return '__version__ = "'+(changes.daemonVersion||version)+'"';
   if(file.endsWith('payload-manifest.json'))return JSON.stringify(payload);
   if(file.endsWith('build-source.json'))return JSON.stringify(receipt);
   if(file.endsWith('package-lock.json'))return JSON.stringify({version:changes.lockVersion||version});
   return JSON.stringify(file.includes('premium-shell')?pkg:{version});
  }
 };
 vm.runInNewContext(code,{require:name=>({'node:fs':mockFs,'node:path':path.win32,'./build-provenance.cjs':{sourceDigest:()=>changes.source||source,hash:file=>changes.badPayload&&file.includes('payload')?'bad':hash}}[name]),__dirname:'C:\\repo\\installer\\premium-shell',process,console:{log:()=>{},error:()=>{}}});
 return process.exitCode;
}
assert.equal(run(),0);
for(const mutation of [{missingReceipt:true},{shellVersion:'0.1.209'},{lockVersion:'0.1.209'},{daemonVersion:'0.1.209'},{source:'changed'},{badPayload:true},{receipt:{daemonSha256:'bad'}},{receipt:{payloadSha256:'bad'}},{receipt:{wrapperSha256:'bad'}}])assert.equal(run(mutation),1,JSON.stringify(mutation));
console.log('PASS release provenance gate: version drift, missing receipt, edited source, payload and daemon mismatch');
