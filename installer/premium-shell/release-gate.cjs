'use strict';
const fs=require('node:fs'),path=require('node:path');
const {sourceDigest,hash}=require('./build-provenance.cjs');
const root=__dirname,appRoot=path.resolve(root,'../..'),errors=[];
function check(condition,message){if(!condition)errors.push(message)}
try{
 const pkg=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8'));
 const manifest=JSON.parse(fs.readFileSync(path.join(root,'payload-manifest.json'),'utf8'));
 const application=JSON.parse(fs.readFileSync(path.join(appRoot,'package.json'),'utf8'));
 const lock=JSON.parse(fs.readFileSync(path.join(appRoot,'package-lock.json'),'utf8'));
 check(pkg.version===manifest.version&&manifest.version===application.version&&lock.version===application.version,'Application, lockfile, shell and payload versions differ');
 const daemonSource=fs.readFileSync(path.join(appRoot,'daemon/synapse_daemon/__init__.py'),'utf8');
 check(daemonSource.includes('__version__ = "'+application.version+'"')||daemonSource.includes("__version__ = '"+application.version+"'"),'Daemon source version differs');
 const payload=path.join(root,'payload',manifest.filename);
 check(fs.existsSync(payload),'Embedded NSIS payload is missing');
 if(fs.existsSync(payload))check(hash(payload)===manifest.sha256,'Embedded payload SHA256 mismatch');
 check(pkg.build.extraResources?.some(item=>item.to==='synapse-payload/'+manifest.filename),'Bundled payload not configured');
 const receiptPath=path.join(root,'build-source.json');
 check(fs.existsSync(receiptPath),'Fresh-source build receipt missing (build-provenance.cjs begin before build, finish afterward)');
 if(fs.existsSync(receiptPath)){
  const receipt=JSON.parse(fs.readFileSync(receiptPath,'utf8'));
  check(receipt.version===application.version&&receipt.sourceDigest===sourceDigest(),'Source changed since verified release build');
  check(receipt.payloadSha256===manifest.sha256,'Payload differs from attested source build');
  const wrapper=path.join(appRoot,'release-premium-shell','Synapse Premium Setup '+application.version+'.exe');
  check(fs.existsSync(wrapper)&&receipt.wrapperSha256===hash(wrapper),'Premium wrapper differs from attested build');
  const daemon=path.join(appRoot,'installer/daemon-dist/synapse-daemon.exe');
  check(fs.existsSync(daemon)&&receipt.daemonSha256===hash(daemon),'Packaged daemon differs from source-build receipt');
 }
 const output=path.resolve(root,'../../release-premium-shell');
 check(fs.existsSync(output)&&fs.readdirSync(output).some(name=>name.endsWith('.exe')&&name.includes(manifest.version)),'Version-matched distributable not built');
}catch(error){errors.push(error.message)}
console.log('Synapse premium release provenance gate: '+(errors.length?'BLOCKED':'PASS (provenance only; Windows E2E and signing are separate)'));
for(const error of errors)console.error('BLOCKER: '+error);
if(errors.length)process.exitCode=1;
