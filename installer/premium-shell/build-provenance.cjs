'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'../..');
const receiptPath=path.join(__dirname,'build-source.json'),startPath=path.join(__dirname,'build-source-start.json');
const hash=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const inputs=['.gitattributes','requirements-release-windows.lock','CHANGELOG.md','package.json','package-lock.json','pyproject.toml','vite.config.ts','tsconfig.json','tailwind.config.ts','postcss.config.js','electron','renderer','daemon/synapse_daemon','daemon/packaged_daemon_main.py','tools','templates','scripts','installer/installer.nsh','installer/build-daemon.ps1','installer/assets','installer/premium-shell/host-chatgpt.cjs','installer/premium-shell/preload-chatgpt.cjs','installer/premium-shell/installer.js','installer/premium-shell/native-adapter-chatgpt.js','installer/premium-shell/index.html','installer/premium-shell/installer.css','installer/premium-shell/premium-polish.css','installer/premium-shell/assets','mobile','ai_os','assets','docs/roadmap.json'];
function sourceDigest(){
 const files=[];
 function visit(relative){
  const full=path.join(root,relative);if(!fs.existsSync(full))return;
  if(fs.statSync(full).isDirectory()){for(const entry of fs.readdirSync(full).sort())if(!['__pycache__','node_modules','.git','dist','dist-electron','build','screenshots','logs','test-results','coverage'].includes(entry))visit(relative+'/'+entry)}
  else if(!/\.(pyc)$/i.test(relative))files.push([relative.replace(/\\/g,'/'),hash(full)]);
 }
 for(const input of inputs)visit(input);
 const shell=JSON.parse(fs.readFileSync(path.join(__dirname,'package.json'),'utf8'));delete shell.version;if(shell.build)delete shell.build.extraResources;
 files.push(['installer/premium-shell/package.json (stable config)',crypto.createHash('sha256').update(JSON.stringify(shell)).digest('hex')]);
 return crypto.createHash('sha256').update(JSON.stringify(files)).digest('hex');
}
function begin(){
 const version=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8')).version;
 fs.writeFileSync(startPath,JSON.stringify({version,sourceDigest:sourceDigest(),startedAt:new Date().toISOString()},null,2));
 if(fs.existsSync(receiptPath))fs.unlinkSync(receiptPath);
 console.log('Release source inputs frozen for '+version);
}
function finish(){
 const started=JSON.parse(fs.readFileSync(startPath,'utf8'));
 const version=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8')).version;
 if(version!==started.version||sourceDigest()!==started.sourceDigest)throw Error('Source changed during release build. Restart the build freeze.');
 const payload=path.join(root,'release','Synapse Setup '+version+'.exe');
 const daemon=path.join(root,'installer/daemon-dist/synapse-daemon.exe');
 for(const file of [payload,daemon]){
  if(!fs.existsSync(file))throw Error('Build artifact missing: '+file);
  if(fs.statSync(file).mtimeMs<Date.parse(started.startedAt)-2000)throw Error('Stale build artifact: '+file);
 }
 const receipt={...started,finishedAt:new Date().toISOString(),payloadSha256:hash(payload),daemonSha256:hash(daemon)};
 fs.writeFileSync(receiptPath,JSON.stringify(receipt,null,2)+'\n');
 console.log('Release source and fresh NSIS/daemon build receipt recorded');
}
function wrapper(){
 const receipt=JSON.parse(fs.readFileSync(receiptPath,'utf8'));
 if(sourceDigest()!==receipt.sourceDigest)throw Error('Source changed before premium wrapper attestation');
 const pkg=JSON.parse(fs.readFileSync(path.join(__dirname,'package.json'),'utf8'));
 const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,'payload-manifest.json'),'utf8'));
 if(pkg.version!==receipt.version||manifest.version!==receipt.version||manifest.sha256!==receipt.payloadSha256)throw Error('Premium wrapper payload/version differs from source-build receipt');
 const file=path.join(root,'release-premium-shell','Synapse Premium Setup '+receipt.version+'.exe');
 if(!fs.existsSync(file)||fs.statSync(file).mtimeMs<Date.parse(receipt.finishedAt)-2000)throw Error('Fresh premium wrapper missing');
 receipt.wrapperSha256=hash(file);receipt.wrapperFinishedAt=new Date().toISOString();
 fs.writeFileSync(receiptPath,JSON.stringify(receipt,null,2)+'\n');
 console.log('Fresh premium wrapper digest recorded');
}
module.exports={sourceDigest,hash};
if(require.main===module){if(process.argv[2]==='begin')begin();else if(process.argv[2]==='finish')finish();else if(process.argv[2]==='wrapper')wrapper();else throw Error('Usage: node build-provenance.cjs begin|finish|wrapper')}
