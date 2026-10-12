'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
function command(executable,args,environment={}){
 const result=spawnSync(executable,args,{cwd:root,encoding:'utf8',windowsHide:true,maxBuffer:2*1024*1024,env:{...process.env,...environment}});
 if(result.status!==0)throw Error('Publisher command failed: '+executable+' '+args[0]); // Never copy credential-bearing CLI output.
 return result.stdout.trim();
}
function githubRelease(repository,version){
 return JSON.parse(command('gh',['api','repos/'+repository+'/releases/tags/v'+version]));
}
function verifyGithubAsset(release,metadata){
 if(release.draft||release.prerelease||release.tag_name!=='v'+metadata.version)throw Error('A published stable GitHub release is required');
 const expected='Synapse.Setup.'+metadata.version+'.exe';
 const artifact=release.assets.find(asset=>asset.name===expected&&asset.state==='uploaded');
 if(!artifact||artifact.size!==metadata.installerSize||artifact.digest!=='sha256:'+metadata.installerSha256)throw Error('GitHub installer name, size or SHA-256 does not match the lifecycle-tested premium artifact');
 return artifact;
}
function atomicWrite(destination,bytes){
 const temporary=destination+'.release-'+crypto.randomUUID()+'.tmp';
 try{fs.writeFileSync(temporary,bytes,{flag:'wx'});fs.renameSync(temporary,destination)}
 finally{if(fs.existsSync(temporary))fs.unlinkSync(temporary)}
}
function validateStagedPublication(receipt,update,siteManifest,latest,bytes,configuration){
 const filename='Synapse.Setup.'+receipt.version+'.exe';
 const digest=crypto.createHash('sha256').update(bytes).digest('hex');
 const sha512=crypto.createHash('sha512').update(bytes).digest('base64');
 const url=new URL('releases/'+filename,configuration.feedUrl).href;
 if(!/^\d+\.\d+\.\d+$/.test(receipt.version)||receipt.version!==update.version||receipt.feedUrl!==configuration.feedUrl)throw Error('Staged release versions or publisher feed differ');
 if(digest!==receipt.installerSha256||bytes.length!==receipt.installerSize||update.windows.sha256!==digest||update.windows.size!==bytes.length||update.windows.url!==url)throw Error('Staged installer/manifest bytes or URL differ');
 const payload=JSON.stringify({version:update.version,notes:update.notes??'',windows:update.windows});
 if(!crypto.verify(null,Buffer.from(payload),configuration.publicKey,Buffer.from(update.signature,'base64')))throw Error('Staged update signature is invalid');
 const expected={version:receipt.version,channel:'stable',artifacts:[{platform:'windows',status:'ready',url:'/releases/'+filename,sha256:digest,size_bytes:bytes.length}]};
 if(JSON.stringify(siteManifest)!==JSON.stringify(expected))throw Error('Staged download-site metadata differs from signed updater artifact');
 const match=latest.match(/^releaseDate: ([^\r\n]+)$/m);
 if(!match||!Number.isFinite(Date.parse(match[1])))throw Error('Staged latest.yml release date is invalid');
 const expectedLatest='version: '+receipt.version+'\nfiles:\n  - url: releases/'+filename+'\n    sha512: '+sha512+'\n    size: '+bytes.length+'\npath: releases/'+filename+'\nsha512: '+sha512+'\nreleaseDate: '+match[1]+'\n';
 if(latest!==expectedLatest)throw Error('Staged latest.yml differs from signed updater artifact');
 return {filename,digest};
}
function publish(staging,siteRoot,publishGithub=false){
 const stage=path.resolve(staging),site=path.resolve(siteRoot);
 const receipt=JSON.parse(fs.readFileSync(path.join(stage,'publication-receipt.json'),'utf8'));
 const update=JSON.parse(fs.readFileSync(path.join(stage,'updates.json'),'utf8'));
 const siteManifest=JSON.parse(fs.readFileSync(path.join(stage,'releases.json'),'utf8'));
 const latest=fs.readFileSync(path.join(stage,'latest.yml'),'utf8');
 const configuration=JSON.parse(fs.readFileSync(path.join(root,'electron/update-publisher.json'),'utf8'));
 const filename='Synapse.Setup.'+receipt.version+'.exe',artifactPath=path.join(stage,'releases',filename);
 const bytes=fs.readFileSync(artifactPath);
 const {digest}=validateStagedPublication(receipt,update,siteManifest,latest,bytes,configuration);
 const proof=JSON.parse(fs.readFileSync(path.join(stage,'lifecycle-proof.json'),'utf8'));
 const proofNames=['windows_clean_install','windows_upgrade','windows_repair','windows_uninstall','windows_rollback','background_startup','account_sign_up','account_sign_in','account_sync','two_device_sync','live_daemon_version','windows_signature'];
 if(proof.schema!=='synapse.release-proof/v1'||proof.version!==receipt.version||proof.installer_sha256!==digest)throw Error('Artifact-bound lifecycle proof is required before publication');
 for(const name of proofNames){const check=proof.checks?.[name],evidence=check?.evidence;if(check?.ok!==true||!evidence?.path||!fs.existsSync(evidence.path)||fs.statSync(evidence.path).size===0||crypto.createHash('sha256').update(fs.readFileSync(evidence.path)).digest('hex')!==evidence.sha256)throw Error('Missing verified lifecycle evidence: '+name)}
 if(proof.checks.live_daemon_version.version!==receipt.version||proof.checks.windows_signature.authenticode_status!=='Valid')throw Error('Lifecycle daemon/signature proof differs from the requested release');
 const signatureScript="$ErrorActionPreference='Stop'; $s=Get-AuthenticodeSignature -LiteralPath $env:SYNAPSE_RELEASE_ARTIFACT; @{status=[string]$s.Status;thumbprint=$s.SignerCertificate.Thumbprint}|ConvertTo-Json -Compress";
 const signature=JSON.parse(command('powershell.exe',['-NoProfile','-NonInteractive','-Command',signatureScript],{SYNAPSE_RELEASE_ARTIFACT:artifactPath}));
 if(signature.status!=='Valid'||!proof.checks.windows_signature.thumbprint||signature.thumbprint.toLowerCase()!==proof.checks.windows_signature.thumbprint.toLowerCase())throw Error('Windows trust rejected the publisher certificate');
 const {sourceDigest}=require('../installer/premium-shell/build-provenance.cjs');
 if(sourceDigest()!==receipt.sourceDigest)throw Error('Release source changed after staging; rebuild and verify it');
 if(command('git',['status','--porcelain','--untracked-files=no']))throw Error('Reviewed source changes must be committed before publishing; publisher never sweeps or commits changes');
 const revision=command('git',['rev-parse','HEAD']);
 const repository='jross32/synapse';
 if(command('git',['rev-list','-n','1','v'+receipt.version])!==revision)throw Error('Release tag does not match reviewed source HEAD');
 // Complete every local readonly site preflight before any GitHub publication.
 if(!fs.existsSync(path.join(site,'index.html'))||!fs.existsSync(path.join(site,'app.js')))throw Error('Configured public site root is missing');
 const processScript="$ErrorActionPreference='Stop'; $expected=$env:SYNAPSE_RELEASE_SITE_ROOT; $matches=@(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*http.server*8879*' -and $_.CommandLine.Contains($expected) }); if($matches.Count -ne 1){throw 'Static server directory cannot be verified'}; 'verified'";
 command('powershell.exe',['-NoProfile','-NonInteractive','-Command',processScript],{SYNAPSE_RELEASE_SITE_ROOT:site});
 const prior=JSON.parse(fs.readFileSync(path.join(site,'releases.json'),'utf8'));
 const index=fs.readFileSync(path.join(site,'index.html'),'utf8'),script=fs.readFileSync(path.join(site,'app.js'),'utf8');
 if(!/^\d+\.\d+\.\d+$/.test(prior.version))throw Error('Current site stable version is invalid');
 const assetUrl='https://github.com/'+repository+'/releases/download/v'+receipt.version+'/'+filename;
 const nextIndex=index.split('v'+prior.version).join('v'+receipt.version).replace(/https:\/\/github\.com\/jross32\/synapse\/releases\/download\/v[\d.]+\/Synapse\.Setup\.[\d.]+\.exe/g,assetUrl).replace(/src="app\.js(?:\?[^"]*)?"/g,'src="app.js?release='+receipt.version+'"');
 const nextScript=script.replace(/const fallbackVersion='[\d.]+';/,"const fallbackVersion='"+receipt.version+"';");
 if(nextScript===script&&prior.version!==receipt.version)throw Error('Download script fallback cannot be updated safely');
 const backup=path.join(stage,'site-backup');fs.mkdirSync(backup,{recursive:true});
 const names=['index.html','app.js','releases.json','updates.json','latest.yml'];
 const priorPresence=new Set(names.filter(name=>fs.existsSync(path.join(site,name))));
 for(const name of priorPresence)fs.copyFileSync(path.join(site,name),path.join(backup,name));
 fs.mkdirSync(path.join(site,'releases'),{recursive:true});
 const destination=path.join(site,'releases',filename);
 if(fs.existsSync(destination)&&crypto.createHash('sha256').update(fs.readFileSync(destination)).digest('hex')!==digest)throw Error('Refusing to overwrite different public installer bytes');
 let reference=JSON.parse(command('gh',['api','repos/'+repository+'/git/ref/tags/v'+receipt.version])).object;
 for(let depth=0;reference.type==='tag'&&depth<5;depth++)reference=JSON.parse(command('gh',['api','repos/'+repository+'/git/tags/'+reference.sha])).object;
 if(reference.type!=='commit'||reference.sha!==revision)throw Error('GitHub tag does not match reviewed source HEAD');
 let release;
 try{release=githubRelease(repository,receipt.version)}catch(error){
  if(!publishGithub)throw error;
  command('gh',['release','create','v'+receipt.version,artifactPath,'--repo',repository,'--verify-tag','--title','Synapse '+receipt.version,'--notes','Unified premium installer. SHA-256: '+digest]);
  release=githubRelease(repository,receipt.version);
 }
 verifyGithubAsset(release,receipt);
 if(!fs.existsSync(destination))atomicWrite(destination,bytes);
 try{
  atomicWrite(path.join(site,'index.html'),nextIndex);
  atomicWrite(path.join(site,'app.js'),nextScript);
  atomicWrite(path.join(site,'releases.json'),fs.readFileSync(path.join(stage,'releases.json')));
  atomicWrite(path.join(site,'latest.yml'),latest);
  atomicWrite(path.join(site,'updates.json'),fs.readFileSync(path.join(stage,'updates.json')));
 }catch(error){
  for(const name of names){
   if(priorPresence.has(name))atomicWrite(path.join(site,name),fs.readFileSync(path.join(backup,name)));
   else if(fs.existsSync(path.join(site,name)))fs.unlinkSync(path.join(site,name));
  }
  throw Error('Site publication failed; prior present/absent files restored');
 }
 console.log(JSON.stringify({status:'deployed_awaiting_live_verification',version:receipt.version,githubTag:release.tag_name,sourceRevision:revision,installerSha256:digest}));
}
module.exports={verifyGithubAsset,validateStagedPublication};
if(require.main===module){if(!process.argv[2]||!process.argv[3])throw Error('Usage: publish-release-stage.cjs STAGING VERIFIED_SITE_ROOT [--publish-github]');publish(process.argv[2],process.argv[3],process.argv.includes('--publish-github'))}
