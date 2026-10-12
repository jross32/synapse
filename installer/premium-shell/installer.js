'use strict';
// Native setup and design preview share the approved eight-screen layout.
const state={current:0,total:8,checksOk:false,checking:false,installDone:false,installRunning:false,installError:null,furthest:0,launched:false};
const native=window.synapseInstaller;
const $=selector=>document.querySelector(selector);
const $$=selector=>document.querySelectorAll(selector);
const text=(selector,value)=>{const element=$(selector);if(element)element.textContent=value};
function errorAt(selector,message){
 const element=$(selector);if(!element)return;
 element.textContent=message||'';element.classList.toggle('hidden',!message);
}
function refreshControls(){
 const next=$('#btn-next');
 $('#btn-back').disabled=state.current===0||state.installRunning||state.checking;
 const blocked=!native||(state.current===2&&(!state.checksOk||state.checking))||state.installRunning;
 next.disabled=blocked;
 next.textContent=state.current===2?'Install':state.current===3?(state.installRunning?'Installing...':state.installDone?'Continue':'Retry installation'):state.current===7?'Finish':'Next';
 if(state.current===7)next.disabled=!native||state.installRunning||!state.launched;
 $$('.fdot').forEach(dot=>{
  const index=Number(dot.dataset.dot);
  dot.disabled=state.installRunning||state.checking||index>state.furthest;
  dot.classList.toggle('active',index===state.current);
  dot.classList.toggle('done',index<state.current);
  dot.setAttribute('aria-current',index===state.current?'step':'false');
 });
}
function showScreen(index){
 if(index<0||index>=state.total||state.installRunning||state.checking)return;
 if(native&&index>3&&!state.installDone)return;
 state.current=index;state.furthest=Math.max(state.furthest,index);
 $$('.screen').forEach(screen=>{
  const selected=Number(screen.dataset.screen)===index;
  screen.classList.toggle('active',selected);screen.classList.remove('exit');
  screen.inert=!selected;screen.setAttribute('aria-hidden',String(!selected));
 });
 $$('.step').forEach(step=>{const n=Number(step.dataset.step);step.classList.toggle('active',n===index);step.classList.toggle('done',n<index)});
 text('#foot-cur',String(index+1));
 refreshControls();
 const title=$('#title-'+index);if(title)title.focus();
 if(index===2&&!state.checksOk)scheduleChecks();
 // Entering the installing screen is possible only via explicit Install/Retry.
}
async function scheduleChecks(){
 if(!native||state.checking||state.installRunning)return;
 state.checking=true;state.checksOk=false;refreshControls();
 text('#sum-text','Checking your Windows system and the bundled package...');
 $('#checks-summary').classList.remove('hidden');
 try{
  const result=await native.preflight();
  const rows=[
   ['Windows',result.meetsBasicPlatform,result.platform+' / '+result.architecture+' / '+result.osRelease],
   ['Package',!result.packageError,result.packageError||'SHA-256 verified, Synapse '+result.version],
   ['Disk space',result.freeBytes!==null&&result.freeBytes>=result.requiredBytes,result.freeBytes===null?(result.spaceError||'Unavailable'):(result.freeBytes/1073741824).toFixed(1)+' GB free / '+(result.requiredBytes/1073741824).toFixed(1)+' GB required']
  ];
  $('#checks-list').replaceChildren();
  for(const [label,pass,detail] of rows){
   const row=document.createElement('li');row.className='check-row '+(pass?'pass':'fail');
   const info=document.createElement('div');info.className='chk-info';
   const name=document.createElement('strong');name.className='chk-name';name.textContent=label;
   const description=document.createElement('span');description.className='chk-detail';description.textContent=detail;
   const badge=document.createElement('span');badge.className='chk-badge '+(pass?'pass':'fail');badge.textContent=pass?'PASS':'FAIL';
   info.append(name,description);row.append(info,badge);$('#checks-list').append(row);
  }
  state.checksOk=result.canInstall===true;
  text('#sum-text',state.checksOk?'Checks passed. Choose Install to continue.':'Resolve the failed checks before installation.');
  text('#install-path',result.installLocation||'Local Programs folder');
  const path=$('#install-path');if(path)path.value=result.installLocation||'Local Programs folder';
  $$('[data-release-version]').forEach(element=>{element.textContent=result.version||'Unavailable'});
 }catch(error){text('#sum-text','System checks failed: '+error.message)}
 finally{state.checking=false;$('#btn-retry-checks').classList.toggle('hidden',state.checksOk);refreshControls()}
}
async function startInstall(){
 if(!native||state.installRunning||state.installDone||!state.checksOk)return;
 state.installRunning=true;state.installError=null;refreshControls();errorAt('#install-error',null);
 text('#prog-pct','Working');text('#prog-eta','Windows setup does not report a percentage.');
 $('#prog-fill').style.width='35%';$('#prog-track').removeAttribute('aria-valuenow');
 text('#prog-step-label','Checking and installing the bundled Synapse package...');
 try{
  const result=await native.install();
  if(!result||!result.ok)throw Error(result?.error||'Windows setup failed');
  state.installDone=true;text('#inst-loc',result.installedPath);
  $$('[data-release-version]').forEach(element=>{element.textContent=result.version});
  text('#prog-pct','Complete');$('#prog-fill').style.width='100%';$('#prog-track').setAttribute('aria-valuenow','100');
  text('#prog-step-label','Installed application version and daemon verified.');text('#prog-eta','Setup complete.');
 }catch(error){
  state.installError=error.message;errorAt('#install-error',state.installError);
  text('#prog-pct','Failed');$('#prog-fill').style.width='0%';
  text('#prog-step-label','Installation did not complete.');text('#prog-eta','Choose Retry installation to try again.');
 }finally{state.installRunning=false;refreshControls()}
}
function goNext(){
 if(state.installRunning||state.checking||!native)return;
 if(state.current===2){if(!state.checksOk)return;showScreen(3);void startInstall();return}
 if(state.current===3&&!state.installDone){void startInstall();return}
 if(state.current===7){if(state.launched)native.windowAction('close');return}
 showScreen(state.current+1);
}
function goBack(){if(!state.installRunning&&!state.checking)showScreen(state.current-1)}
async function launchInstalled(){
 if(!native||!state.installDone||state.installRunning)return;
 const button=$('#btn-launch');button.disabled=true;errorAt('#launch-error',null);
 text('#launch-status','Starting the installed Synapse application...');
 try{
  const result=await native.launch();if(!result?.ok)throw Error(result?.error||'Launch failed');
  state.launched=true;text('#launch-status','Synapse process started. Sign in or create your account in the app.');
 }catch(error){errorAt('#launch-error',error.message);text('#launch-status','');button.disabled=false}
 refreshControls();
}
document.addEventListener('DOMContentLoaded',()=>{
 text('#runtime-notice',native?'Verified bundled Windows setup. Account sign-in happens after launch.':'Design preview only. No installation or account action occurs.');
 text('#build-mode',native?'WINDOWS SETUP':'DESIGN PREVIEW');
 $('#btn-welcome-start').addEventListener('click',()=>showScreen(1));
 $('#btn-next').addEventListener('click',goNext);$('#btn-back').addEventListener('click',goBack);
 $('#btn-retry-checks').addEventListener('click',scheduleChecks);
 $('#btn-launch').disabled=!native;$('#btn-launch').addEventListener('click',launchInstalled);
 $$('.fdot').forEach(dot=>dot.addEventListener('click',()=>{const index=Number(dot.dataset.dot);if(index<=state.furthest)showScreen(index)}));
 $('.wmin').addEventListener('click',()=>native?.windowAction('minimize'));
 $('.wclose').addEventListener('click',()=>{if(!state.installRunning)native?.windowAction('close')});
 if(native?.onStatus)native.onStatus(status=>{
  text('#prog-step-label',status.message);
  const row=document.createElement('li');row.className='log-entry';row.textContent=status.message;$('#install-log').append(row);
 });
 if(!native){
  // Explicit preview routing shows layouts, never reports actual installation.
  const match=location.hash.match(/^#screen-(\d+)$/);
  showScreen(match?Math.min(7,Math.max(0,Number(match[1])-1)):0);
 }else showScreen(0);
});
