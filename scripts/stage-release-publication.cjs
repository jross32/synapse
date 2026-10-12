'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {loadPrivateKey}=require('./prepare-release-publisher.cjs');
const root=path.resolve(__dirname,'..');
const hash=(bytes,algorithm)=>crypto.createHash(algorithm).update(bytes).digest(algorithm==='sha512'?'base64':'hex');
function metadata(version,artifact,publicConfig,privateKey,notes=''){
 if(!/^\d+\.\d+\.\d+$/.test(version))throw Error('Invalid release version');
 const feed=new URL(publicConfig.feedUrl);
 const filename='Synapse.Setup.'+version+'.exe';
 const url=new URL('releases/'+filename,feed).href;
 const windows={url,sha256:hash(artifact,'sha256'),size:artifact.length};
 const payload=JSON.stringify({version,notes,windows});
 const signature=crypto.sign(null,Buffer.from(payload),privateKey).toString('base64');
 const manifest={version,notes,windows,signature};
 if(!crypto.verify(null,Buffer.from(payload),publicConfig.publicKey,Buffer.from(signature,'base64')))throw Error('Signing key does not match embedded publisher key');
 const sha512=hash(artifact,'sha512');
 const latest='version: '+version+'\nfiles:\n  - url: releases/'+filename+'\n    sha512: '+sha512+'\n    size: '+artifact.length+'\npath: releases/'+filename+'\nsha512: '+sha512+'\nreleaseDate: '+new Date().toISOString()+'\n';
 const releases={version,channel:'stable',artifacts:[{platform:'windows',status:'ready',url:'/releases/'+filename,sha256:windows.sha256,size_bytes:windows.size}]};
 return {filename,manifest,latest,releases};
}
function stage(version,output){
 const provenance=JSON.parse(fs.readFileSync(path.join(root,'installer/premium-shell/build-source.json'),'utf8'));
 const {sourceDigest}=require('../installer/premium-shell/build-provenance.cjs');
 if(provenance.version!==version||provenance.sourceDigest!==sourceDigest())throw Error('Source-build provenance does not match current tree');
 const config=JSON.parse(fs.readFileSync(path.join(root,'electron/update-publisher.json'),'utf8'));
 const source=path.join(root,'release-premium-shell','Synapse Premium Setup '+version+'.exe');
 const artifact=fs.readFileSync(source);
 if(hash(artifact,'sha256')!==provenance.wrapperSha256)throw Error('Premium wrapper bytes are not attested to the source build');
 const result=metadata(version,artifact,config,loadPrivateKey());
 const destination=path.resolve(output);
 if(fs.existsSync(destination))throw Error('Refusing to overwrite staged publication');
 fs.mkdirSync(path.join(destination,'releases'),{recursive:true});
 fs.writeFileSync(path.join(destination,'releases',result.filename),artifact);
 fs.writeFileSync(path.join(destination,'updates.json'),JSON.stringify(result.manifest,null,2)+'\n');
 fs.writeFileSync(path.join(destination,'releases.json'),JSON.stringify(result.releases,null,2)+'\n');
 fs.writeFileSync(path.join(destination,'latest.yml'),result.latest);
 const receipt={schema:'synapse.release-publication/v1',version,installerSha256:result.manifest.windows.sha256,installerSize:artifact.length,sourceDigest:provenance.sourceDigest,feedUrl:config.feedUrl,publicationStatus:'staged'};
 fs.writeFileSync(path.join(destination,'publication-receipt.json'),JSON.stringify(receipt,null,2)+'\n');
 console.log(JSON.stringify(receipt));
 return receipt;
}
module.exports={metadata};
if(require.main===module){if(!process.argv[2]||!process.argv[3])throw Error('Usage: stage-release-publication.cjs VERSION NEW_STAGING_DIRECTORY');stage(process.argv[2],process.argv[3])}
