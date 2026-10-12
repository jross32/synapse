'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
function protectedKeyPath(){
 if(process.platform!=='win32'||!process.env.LOCALAPPDATA)throw Error('Publisher keys require Windows user-scoped DPAPI');
 return path.join(process.env.LOCALAPPDATA,'Synapse','publisher','release-ed25519.dpapi');
}
function dpapi(value,decrypt){
 const action=decrypt?'Unprotect':'Protect';
 const script="$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Security; $data=[Convert]::FromBase64String([Console]::In.ReadToEnd()); $result=[Security.Cryptography.ProtectedData]::"+action+"($data,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser); [Console]::Out.Write([Convert]::ToBase64String($result))";
 const result=spawnSync('powershell.exe',['-NoProfile','-NonInteractive','-Command',script],{input:Buffer.from(value).toString('base64'),encoding:'utf8',windowsHide:true,maxBuffer:1024*1024});
 if(result.status!==0)throw Error('Windows DPAPI operation failed'); // Never include child output or private material.
 return Buffer.from(result.stdout.trim(),'base64');
}
function loadPrivateKey(){
 const filename=protectedKeyPath();
 if(!fs.existsSync(filename))throw Error('Protected publisher signing key is missing; prepare publisher first');
 return crypto.createPrivateKey(dpapi(fs.readFileSync(filename),true));
}
function preparePublisher(feedUrl){
 const parsed=new URL(feedUrl);if(parsed.protocol!=='https:'||parsed.username||parsed.password||(parsed.port&&parsed.port!=='443'))throw Error('Publisher feed must be credential-free HTTPS');
 const filename=protectedKeyPath();let created=false;
 const destination=path.resolve(__dirname,'../electron/update-publisher.json');
 const existing=fs.existsSync(destination)?JSON.parse(fs.readFileSync(destination,'utf8')):null;
 if(!fs.existsSync(filename)&&existing?.publicKey)throw Error('Existing publisher public key has no protected private key here. Restore the original user-scoped key; automatic key rotation is forbidden.');
 if(!fs.existsSync(filename)){
  fs.mkdirSync(path.dirname(filename),{recursive:true});
  const pair=crypto.generateKeyPairSync('ed25519');
  const privatePem=pair.privateKey.export({type:'pkcs8',format:'pem'});
  const protectedBytes=dpapi(Buffer.from(privatePem),false);
  // wx refuses to replace a key another release process just created.
  try{fs.writeFileSync(filename,protectedBytes,{flag:'wx',mode:0o600});created=true}catch(error){if(error.code!=='EEXIST')throw error}
 }
 const privateKey=loadPrivateKey();
 if(privateKey.asymmetricKeyType!=='ed25519')throw Error('Existing protected publisher key is not Ed25519');
 const publicKey=crypto.createPublicKey(privateKey).export({type:'spki',format:'pem'}).toString();
 if(existing?.publicKey){
  const expected=crypto.createPublicKey(existing.publicKey).export({type:'spki',format:'der'});
  const actual=crypto.createPublicKey(privateKey).export({type:'spki',format:'der'});
  if(!expected.equals(actual))throw Error('Protected publisher key differs from the existing trusted public key; rotation is forbidden.');
 }
 const config={schema:'synapse.update-publisher/v1',feedUrl:parsed.href,publicKey};
 fs.writeFileSync(destination,JSON.stringify(config,null,2)+'\n');
 const fingerprint=crypto.createHash('sha256').update(publicKey).digest('hex');
 return {config,fingerprint,created};
}
module.exports={preparePublisher,loadPrivateKey};
if(require.main===module){
 const result=preparePublisher(process.argv[2]||'https://download.whatapc.com/updates.json');
 console.log(JSON.stringify({publisherPublicKeyFingerprint:result.fingerprint,protectedKeyCreated:result.created,feedUrl:result.config.feedUrl}));
}
