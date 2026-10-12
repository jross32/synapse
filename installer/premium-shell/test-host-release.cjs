'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events');
const code=fs.readFileSync(path.join(__dirname,'host-chatgpt.cjs'),'utf8');
function harness(options={}){
 const handlers=new Map(),seen=[];
 const version='0.2.219',exe='C:\\Users\\test\\AppData\\Local\\Programs\\Synapse\\Synapse.exe';
 const manifest={version,filename:'Synapse Setup '+version+'.exe',sha256:'a'.repeat(64)};
 const disk=options.freeBytes??5*1024*1024*1024;
 const fakeFs={
  existsSync:filename=>!options.missingDaemon||!filename.endsWith('synapse-daemon.exe'),
  readFileSync:filename=>JSON.stringify(filename.endsWith('payload-manifest.json')?manifest:{name:'synapse',version:options.installedVersion||version}),
  createReadStream:()=>{const stream=new EventEmitter();queueMicrotask(()=>{stream.emit('data',Buffer.from('payload'));stream.emit('end')});return stream}
 };
 function fakeSpawn(command,args){
  const child=new EventEmitter();child.stdout=new EventEmitter();child.stderr=new EventEmitter();child.kill=()=>{};child.unref=()=>{};seen.push([command,args]);
  queueMicrotask(()=>{
   if(command==='powershell.exe'){child.stdout.emit('data',Buffer.from(args.at(-1).includes('Win32_LogicalDisk')?String(disk):'[]'));child.emit('exit',0)}
   else if(command.includes('synapse-payload'))child.emit('exit',options.installExit??0);
   else if(options.launchError)child.emit('error',Error('Launch denied'));
   else child.emit('spawn');
  });return child;
 }
 const electron={app:{whenReady:()=>({then:()=>{}}),on:()=>{},quit:()=>{}},BrowserWindow:function(){},ipcMain:{handle:(name,fn)=>handlers.set(name,fn)}};
 vm.runInNewContext(code,{
  require:name=>({'electron':electron,'node:os':{release:()=>options.osRelease||'10.0.22631'},'node:fs':fakeFs,'node:path':path.win32,'node:crypto':{createHash:()=>({update:()=>{},digest:()=>options.badHash?'b'.repeat(64):'a'.repeat(64)})},'node:child_process':{spawn:fakeSpawn},'./daemon-version-check.cjs':{awaitMatchingDaemonVersion:async(expected)=>{if(options.liveDaemonVersion&&options.liveDaemonVersion!==expected)throw Error('Background daemon version mismatch');return {ok:true,version:expected}}}}[name]),
  __dirname:'C:\\shell',process:{resourcesPath:'C:\\resources',platform:options.platform||'win32',arch:options.arch||'x64',env:{LOCALAPPDATA:'C:\\Users\\test\\AppData\\Local'}},
  setTimeout,clearTimeout,Buffer,console
 });
 return {call:(name)=>handlers.get('setup:'+name)(),seen,exe};
}
(async()=>{
 for(const options of [{badHash:true},{freeBytes:100},{arch:'arm64'},{osRelease:'6.3'}]){
  const h=harness(options),pre=await h.call('preflight');assert.equal(pre.canInstall,false);
  const outcome=await h.call('install');assert.equal(outcome.ok,false);assert.equal(h.seen.some(([cmd])=>cmd.includes('synapse-payload')),false);
 }
 for(const options of [{installedVersion:'0.1.209'},{missingDaemon:true},{installExit:1}]){
  const h=harness(options);assert.equal((await h.call('install')).ok,false);await assert.rejects(h.call('launch'));
 }
 const good=harness();assert.equal((await good.call('install')).ok,true);assert.equal((await good.call('launch')).ok,true);
 const stale=harness({liveDaemonVersion:'0.1.209'});assert.equal((await stale.call('install')).ok,true);await assert.rejects(stale.call('launch'),/daemon version mismatch/);
 const denied=harness({launchError:true});assert.equal((await denied.call('install')).ok,true);await assert.rejects(denied.call('launch'),/Launch denied/);
 console.log('PASS host: compatibility, disk, hash, old-version, daemon, install exit and launch failure gates');
})().catch(error=>{console.error(error);process.exitCode=1});
