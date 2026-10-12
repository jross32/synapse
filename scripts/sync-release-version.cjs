'use strict';
const fs=require('node:fs'),path=require('node:path');
const {spawnSync}=require('node:child_process');
function synchronize(root,version,expected){
 if(!/^\d+\.\d+\.\d+$/.test(version))throw Error('Release version must be major.minor.patch');
 const read=name=>fs.readFileSync(path.join(root,name),'utf8').replace(/^\uFEFF/,'');
 const pkg=JSON.parse(read('package.json'));
 if(pkg.version!==expected)throw Error('Source version changed since this request; choose a fresh release run');
 const parts=value=>value.split('.').map(Number);
 const a=parts(version),b=parts(expected);
 if(a.some((number,index)=>number!==b[index]&&a.slice(0,index).every((prior,j)=>prior===b[j])&&number<b[index]))throw Error('Release version cannot downgrade source metadata');
 const tag=spawnSync('git',['rev-parse','--verify','--quiet','refs/tags/v'+version],{cwd:root,encoding:'utf8',windowsHide:true});
 if(tag.status===0)throw Error('This version already has a release tag; choose a new version');
 const originals=new Map();
 for(const name of ['package.json','package-lock.json','pyproject.toml','daemon/synapse_daemon/__init__.py'])originals.set(name,read(name));
 const lock=JSON.parse(originals.get('package-lock.json'));
 pkg.version=version;lock.version=version;if(lock.packages?.[''])lock.packages[''].version=version;
 const project=originals.get('pyproject.toml').replace(/^version\s*=\s*["'][^"']+["']/m,'version = "'+version+'"');
 const daemon=originals.get('daemon/synapse_daemon/__init__.py').replace(/^__version__\s*=\s*["'][^"']+["']/m,'__version__ = "'+version+'"');
 if(!project.includes('version = "'+version+'"')||!daemon.includes('__version__ = "'+version+'"'))throw Error('Source version markers are missing');
 const updates=new Map([['package.json',JSON.stringify(pkg,null,2)+'\n'],['package-lock.json',JSON.stringify(lock,null,2)+'\n'],['pyproject.toml',project],['daemon/synapse_daemon/__init__.py',daemon]]);
 try{for(const [name,value]of updates)fs.writeFileSync(path.join(root,name),value)}
 catch(error){for(const [name,value]of originals)fs.writeFileSync(path.join(root,name),value);throw error}
 return {version,previousVersion:expected,files:[...updates.keys()],gitCommitCreated:false};
}
module.exports={synchronize};
if(require.main===module){
 const expectedIndex=process.argv.indexOf('--expected');
 if(!process.argv[2]||expectedIndex<0||!process.argv[expectedIndex+1])throw Error('Usage: sync-release-version.cjs VERSION --expected SOURCE_VERSION');
 console.log(JSON.stringify(synchronize(path.resolve(__dirname,'..'),process.argv[2],process.argv[expectedIndex+1])));
}
