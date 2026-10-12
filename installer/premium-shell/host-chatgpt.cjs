'use strict';
const {app,BrowserWindow,ipcMain} = require('electron');
const os=require('node:os'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
let window=null,running=false,installedPath=null;
const ROOT=__dirname;
const RESOURCES=process.resourcesPath;
const manifestPath=path.join(ROOT,'payload-manifest.json');
function payloadInfo(){
 const manifest=JSON.parse(fs.readFileSync(manifestPath,'utf8'));
 if(!/^0\.\d+\.\d+$/.test(manifest.version)||!/^([0-9a-f]{64})$/.test(manifest.sha256)||!/^Synapse Setup [\w. -]+\.exe$/.test(manifest.filename))throw Error('Invalid bundled payload manifest');
 const target=path.join(RESOURCES,'synapse-payload',manifest.filename);
 if(!fs.existsSync(target))throw Error('Bundled Synapse installer missing');
 return {manifest,target};
}
function digest(file){
 return new Promise((resolve,reject)=>{
  const h=crypto.createHash('sha256');const input=fs.createReadStream(file);
  input.on('data',buf=>h.update(buf));input.on('error',reject);input.on('end',()=>resolve(h.digest('hex')));
 });
}
function makeWindow(){
 window=new BrowserWindow({width:1060,height:720,minWidth:780,minHeight:580,backgroundColor:'#070d20',frame:false,webPreferences:{preload:path.join(ROOT,'preload-chatgpt.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
 window.loadFile(path.join(ROOT,'index.html'));
}
function runPS(script){return new Promise((resolve,reject)=>{
 const child=spawn('powershell.exe',['-NoProfile','-NonInteractive','-Command',script],{windowsHide:true,stdio:['ignore','pipe','pipe']});
 let stdout='',stderr='';child.stdout.on('data',b=>stdout+=String(b).slice(0,16000));child.stderr.on('data',b=>stderr+=String(b).slice(0,16000));
 child.on('error',reject);child.on('exit',code=>code===0?resolve(stdout.trim()):reject(new Error(stderr.slice(0,1000)||'PowerShell error '+code)));
});}
function findInstalled(){
 const roots=[process.env.LOCALAPPDATA&&path.join(process.env.LOCALAPPDATA,'Programs','Synapse','Synapse.exe'),process.env.PROGRAMFILES&&path.join(process.env.PROGRAMFILES,'Synapse','Synapse.exe'),process.env['PROGRAMFILES(X86)']&&path.join(process.env['PROGRAMFILES(X86)'],'Synapse','Synapse.exe')].filter(Boolean);
 return roots.find(p=>fs.existsSync(p))||null;
}
ipcMain.handle('setup:preflight',async()=>{
 let freeBytes=null,spaceError=null;
 if(process.platform==='win32')try{
  const root=path.parse(process.env.LOCALAPPDATA||process.env.USERPROFILE||'C:\\').root;
  const result=await runPS(`(Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='${root.slice(0,2)}'").FreeSpace`);
  freeBytes=Number(result);if(!Number.isFinite(freeBytes))throw Error('Disk metric unavailable');
 }catch(error){spaceError=String(error.message)}
 return {platform:process.platform,architecture:process.arch,osRelease:os.release(),freeBytes,spaceError,meetsBasicPlatform:process.platform==='win32'&&process.arch==='x64'};
});
ipcMain.handle('setup:install',async()=>{
 if(running)throw Error('An installation is already active');
 if(process.platform!=='win32')throw Error('Windows required');
 running=true;
 const notify=(state,message)=>{if(window&&!window.isDestroyed())window.webContents.send('setup:status',{state,message})};
 try{
  const {manifest,target}=payloadInfo();notify('verifying','Verifying embedded Synapse setup');
  const actual=await digest(target);if(actual!==manifest.sha256)throw Error('Installer integrity check failed');
  notify('installing','Installing Synapse '+manifest.version+' (Windows installer may require permission)');
  const result=await new Promise(resolve=>{
   const child=spawn(target,['/S'],{windowsHide:true,stdio:'ignore'});let settled=false;
   const finish=value=>{if(!settled){settled=true;resolve(value)}};
   child.on('error',e=>finish({ok:false,error:e.message}));child.on('exit',code=>finish({ok:code===0,exitCode:code}));
  });
  if(!result.ok)throw Error(result.error||'Installer exited with code '+result.exitCode);
  installedPath=findInstalled();if(!installedPath)throw Error('Installer returned success but Synapse.exe was not found in known installation directories');
  notify('finished','Verified Synapse executable at '+installedPath);
  return {ok:true,installedPath,version:manifest.version};
 }catch(e){notify('failed',String(e.message||e));return {ok:false,error:String(e.message||e)}}
 finally{running=false}
});
ipcMain.handle('setup:launch',async()=>{
 if(running)throw Error('Installation still in progress');
 if(!installedPath||!fs.existsSync(installedPath))throw Error('Installed Synapse executable not verified');
 const child=spawn(installedPath,[],{detached:true,stdio:'ignore',windowsHide:false});child.unref();return {ok:true};
});
ipcMain.handle('setup:window',(_e,action)=>{if(!window)return;if(action==='minimize')window.minimize();if(action==='close'&&!running)window.close()});
app.whenReady().then(makeWindow);app.on('window-all-closed',()=>app.quit());