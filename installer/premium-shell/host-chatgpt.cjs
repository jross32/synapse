'use strict';
const {app,BrowserWindow,ipcMain}=require('electron');
const os=require('node:os'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const {awaitMatchingDaemonVersion}=require('./daemon-version-check.cjs');
let window=null,running=false,installedPath=null,installedVersion=null;
const ROOT=__dirname,RESOURCES=process.resourcesPath;
const manifestPath=path.join(ROOT,'payload-manifest.json');
const REQUIRED_BYTES=2*1024*1024*1024;
function payloadInfo(){
 const manifest=JSON.parse(fs.readFileSync(manifestPath,'utf8'));
 if(!/^\d+\.\d+\.\d+$/.test(manifest.version)||!/^([0-9a-f]{64})$/.test(manifest.sha256)||manifest.filename!=='Synapse Setup '+manifest.version+'.exe')throw Error('Invalid bundled payload manifest');
 const target=path.join(RESOURCES,'synapse-payload',manifest.filename);
 if(!fs.existsSync(target))throw Error('Bundled Synapse installer missing');
 return {manifest,target};
}
function digest(file){
 return new Promise((resolve,reject)=>{
  const hash=crypto.createHash('sha256'),input=fs.createReadStream(file);
  input.on('data',buf=>hash.update(buf));input.on('error',reject);input.on('end',()=>resolve(hash.digest('hex')));
 });
}
function makeWindow(){
 window=new BrowserWindow({width:1060,height:720,minWidth:780,minHeight:580,backgroundColor:'#070d20',frame:false,webPreferences:{preload:path.join(ROOT,'preload-chatgpt.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
 window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
 window.webContents.on('will-navigate',event=>event.preventDefault());
 window.on('close',event=>{if(running)event.preventDefault()});
 window.loadFile(path.join(ROOT,'index.html'));
}
function runPS(script){
 return new Promise((resolve,reject)=>{
  const child=spawn('powershell.exe',['-NoProfile','-NonInteractive','-Command',script],{windowsHide:true,stdio:['ignore','pipe','pipe']});
  let stdout='',stderr='';
  const timer=setTimeout(()=>{child.kill();reject(Error('Windows system check timed out'))},15000);
  child.stdout.on('data',b=>{stdout=(stdout+String(b)).slice(-16000)});
  child.stderr.on('data',b=>{stderr=(stderr+String(b)).slice(-16000)});
  child.on('error',error=>{clearTimeout(timer);reject(error)});
  child.on('exit',code=>{clearTimeout(timer);code===0?resolve(stdout.trim()):reject(Error(stderr.slice(0,1000)||'PowerShell error '+code))});
 });
}
function standardInstalled(){
 return process.env.LOCALAPPDATA?path.join(process.env.LOCALAPPDATA,'Programs','Synapse','Synapse.exe'):null;
}
async function installLocation(){
 // NSIS remembers custom installation directories under the application's uninstall key.
 const script="$ErrorActionPreference='Stop'; $keys=@('HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*','HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*','HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'); $items=Get-ItemProperty $keys -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -eq 'Synapse' -and $_.InstallLocation }; @($items | ForEach-Object { $_.InstallLocation }) | ConvertTo-Json -Compress";
 let entries=[];
 try{const raw=await runPS(script);if(raw){const parsed=JSON.parse(raw);entries=Array.isArray(parsed)?parsed:[parsed]}}catch(_){}
 const candidates=entries.filter(x=>typeof x==='string'&&path.isAbsolute(x)).map(x=>path.join(x,'Synapse.exe'));
 candidates.push(standardInstalled());
 return candidates.find(x=>x&&fs.existsSync(x))||standardInstalled();
}
function attestInstalled(executable,expected){
 if(!executable||!fs.existsSync(executable))throw Error('Installed Synapse executable was not found');
 // Electron fs transparently reads ASAR paths; never accept an old executable alone.
 const packagePath=path.join(path.dirname(executable),'resources','app.asar','package.json');
 const pkg=JSON.parse(fs.readFileSync(packagePath,'utf8'));
 if(pkg.name!=='synapse'||pkg.version!==expected)throw Error('Installed application version does not match bundled Synapse '+expected);
 const daemon=path.join(path.dirname(executable),'resources','daemon','synapse-daemon.exe');
 if(!fs.existsSync(daemon))throw Error('Installed Synapse daemon is missing');
 return pkg.version;
}
async function preflight(){
 let freeBytes=null,spaceError=null,packageError=null,version=null;
 const location=await installLocation();
 const meetsBasicPlatform=process.platform==='win32'&&process.arch==='x64'&&Number(os.release().split('.')[0])>=10;
 if(process.platform==='win32'&&location)try{
  const root=path.parse(location).root.slice(0,2);
  if(!/^[A-Za-z]:$/.test(root))throw Error('Installation drive cannot be checked');
  const result=await runPS("(Get-CimInstance Win32_LogicalDisk -Filter \"DeviceID='"+root+"'\").FreeSpace");
  freeBytes=Number(result);if(!Number.isFinite(freeBytes)||freeBytes<0)throw Error('Disk metric unavailable');
 }catch(error){spaceError=String(error.message);freeBytes=null}
 try{const info=payloadInfo();version=info.manifest.version;if(await digest(info.target)!==info.manifest.sha256)throw Error('Installer integrity check failed')}catch(error){packageError=String(error.message)}
 const canInstall=meetsBasicPlatform&&!packageError&&freeBytes!==null&&freeBytes>=REQUIRED_BYTES;
 return {platform:process.platform,architecture:process.arch,osRelease:os.release(),freeBytes,requiredBytes:REQUIRED_BYTES,spaceError,packageError,version,installLocation:location,meetsBasicPlatform,canInstall};
}
ipcMain.handle('setup:preflight',preflight);
ipcMain.handle('setup:install',async()=>{
 if(running)return {ok:false,error:'An installation is already active'};
 running=true;installedPath=null;installedVersion=null;
 const notify=(state,message)=>{if(window&&!window.isDestroyed())window.webContents.send('setup:status',{state,message})};
 try{
  notify('verifying','Checking Windows, disk space and bundled package');
  const checks=await preflight();
  if(!checks.canInstall)throw Error(checks.packageError||checks.spaceError||(!checks.meetsBasicPlatform?'Windows 10 or later, x64 required':'At least 2 GB free space is required'));
  const {manifest,target}=payloadInfo();
  notify('installing','Installing Synapse '+manifest.version);
  const result=await new Promise(resolve=>{
   const child=spawn(target,['/S'],{windowsHide:true,stdio:'ignore'});let settled=false;
   const finish=value=>{if(!settled){settled=true;resolve(value)}};
   child.on('error',error=>finish({ok:false,error:error.message}));
   child.on('exit',code=>finish({ok:code===0,exitCode:code}));
  });
  if(!result.ok)throw Error(result.error||'Installer exited with code '+result.exitCode);
  const executable=await installLocation();
  const version=attestInstalled(executable,manifest.version);
  installedPath=executable;installedVersion=version;
  notify('finished','Installed application and daemon verified');
  return {ok:true,installedPath,version};
 }catch(error){notify('failed',String(error.message));return {ok:false,error:String(error.message)}}
 finally{running=false}
});
ipcMain.handle('setup:launch',async()=>{
 if(running)throw Error('Installation still in progress');
 if(!installedPath||!installedVersion)throw Error('Installed Synapse has not been verified');
 attestInstalled(installedPath,installedVersion);
 await new Promise((resolve,reject)=>{
  const child=spawn(installedPath,[],{detached:true,stdio:'ignore',windowsHide:false});
  child.once('error',reject);child.once('spawn',()=>{child.unref();resolve()});
 });
 // Verify the daemon that actually owns the API port. An older daemon can
 // survive installation and silently break device/account sync. Do not kill
 // existing work; surface actionable instructions if the old daemon remains.
 await awaitMatchingDaemonVersion(installedVersion);
 return {ok:true};
});
ipcMain.handle('setup:window',(_event,action)=>{if(!window)return;if(action==='minimize')window.minimize();if(action==='close'&&!running)window.close()});
app.whenReady().then(makeWindow);app.on('window-all-closed',()=>app.quit());
