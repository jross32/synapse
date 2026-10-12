'use strict';
const assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events'),ts=require('typescript');
const {metadata}=require('./stage-release-publication.cjs');
const {verifyGithubAsset}=require('./publish-release-stage.cjs');
const pair=crypto.generateKeyPairSync('ed25519'),publicKey=pair.publicKey.export({type:'spki',format:'pem'}).toString();
const bytes=Buffer.from('Test installer fixture');
const release=metadata('0.2.219',bytes,{feedUrl:'https://download.whatapc.com/updates.json',publicKey},pair.privateKey,'Proof-bound fixture');
const payload=JSON.stringify({version:release.manifest.version,notes:release.manifest.notes,windows:release.manifest.windows});
assert.equal(crypto.verify(null,Buffer.from(payload),publicKey,Buffer.from(release.manifest.signature,'base64')),true);
assert.equal(crypto.verify(null,Buffer.from(payload+'tampered'),publicKey,Buffer.from(release.manifest.signature,'base64')),false);
assert.equal(release.releases.artifacts[0].sha256,release.manifest.windows.sha256);
assert.equal(release.releases.artifacts[0].size_bytes,bytes.length);
assert.match(release.latest,new RegExp('sha512: '+crypto.createHash('sha512').update(bytes).digest('base64').replace(/[.*+?^$()|[\]\\]/g,'\\$&')));
const valid={draft:false,prerelease:false,tag_name:'v0.2.219',assets:[{name:'Synapse.Setup.0.2.219.exe',state:'uploaded',size:bytes.length,digest:'sha256:'+release.manifest.windows.sha256}]};
const receipt={version:'0.2.219',installerSize:bytes.length,installerSha256:release.manifest.windows.sha256};
assert.equal(verifyGithubAsset(valid,receipt),valid.assets[0]);
for(const changed of [{...valid,draft:true},{...valid,tag_name:'v0.1.217'},{...valid,assets:[{...valid.assets[0],digest:null}]},{...valid,assets:[{...valid.assets[0],name:'Old.exe'}]}])assert.throws(()=>verifyGithubAsset(changed,receipt));
function updater(redirects){
 const seen=[];
 const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../electron/desktop-updater.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;
 const exports={};
 vm.runInNewContext(source,{exports,require:name=>name==='electron'?{app:{isPackaged:true,getVersion:()=> '0.2.218'},ipcMain:{handle:()=>{}}}:name==='./update-publisher.json'?{feedUrl:'https://download.whatapc.com/updates.json',publicKey}:name==='node:https'?{get:(url,options,callback)=>{
  const request=new EventEmitter();request.destroy=error=>request.emit('error',error);seen.push(url.href);
  queueMicrotask(()=>{const response=new EventEmitter();response.resume=()=>{};
   response.statusCode=seen.length<=redirects?302:200;response.headers={location:'/next-'+seen.length};callback(response)});
  return request;
 }}:require(name),process,Buffer,URL,console});
 return {exports,seen};
}
(async()=>{
 const bounded=updater(3);await bounded.exports.openPublisherResponse('https://download.whatapc.com/start',1000);assert.equal(bounded.seen.length,4);
 const loop=updater(99);await assert.rejects(loop.exports.openPublisherResponse('https://download.whatapc.com/start',1000),/redirect limit/);assert.equal(loop.seen.length,6);
 const invalid=updater(0);
 for(const url of ['http://download.whatapc.com/x','https://username:password@example.test/x','https://example.test:444/x'])await assert.rejects(invalid.exports.openPublisherResponse(url,1000),/HTTPS/);
 assert.equal(invalid.seen.length,0);
 console.log('PASS signed metadata, site/latest consistency, GitHub proof gate and bounded secure updater redirects');
})().catch(error=>{console.error(error);process.exitCode=1});
