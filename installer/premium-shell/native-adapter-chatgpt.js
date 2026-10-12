'use strict';
(function(){
 const native=window.synapseInstaller;
 const get=(selector)=>document.querySelector(selector);
 const show=(selector,value)=>{const el=get(selector);if(el)el.textContent=value};
 const button=(label,disabled)=>{const el=get('#btn-next');if(el){el.textContent=label;el.disabled=disabled}};
 async function installActual(){
  state.installDone=false;button('Installing...',true);
  show('#prog-pct','0%');const fill=get('#prog-fill');if(fill)fill.style.width='0%';
  show('#prog-eta','Actual progress is managed by Windows setup');
  if(!native){show('#prog-step-label','UI preview only, no installation');return;}
  show('#prog-step-label','Preparing verified bundled Synapse setup');
  try{
   const outcome=await native.install();
   if(!outcome.ok)throw Error(outcome.error||'Windows installation failed');
   state.installDone=true;
   if(fill)fill.style.width='100%';show('#prog-pct','100%');
   show('#prog-step-label','Synapse installed and executable verified');
   show('#prog-eta','Setup complete');button('Continue',false);
  }catch(error){show('#prog-step-label','Installation failed: '+String(error.message||error));show('#prog-eta','');button('Retry installation',false)}
 }
 async function realChecks(){
  if(!native){for(const n of ['os','mem','disk','net','res','gpu'])setCheckResult(n,'warn','Preview only','PREVIEW');state.checksOk=true;showChecksSummary();return}
  try{
   const sys=await native.preflight();
   setCheckResult('os',sys.meetsBasicPlatform?'pass':'fail',sys.platform+' / '+sys.architecture+' / '+sys.osRelease,sys.meetsBasicPlatform?'PASS':'FAIL');
   const enough=sys.freeBytes!==null&&sys.freeBytes>=1073741824;
   setCheckResult('disk',enough?'pass':'warn',sys.freeBytes!==null?(sys.freeBytes/1073741824).toFixed(1)+' GB available':'Disk check unavailable: '+(sys.spaceError||'unknown'),enough?'PASS':'WARN');
   await Promise.all([checkMemory(),checkNetwork(),checkResolution(),checkGPU()]);showChecksSummary();
  }catch(error){setCheckResult('os','fail',String(error.message||error),'FAIL');state.checksOk=false;showChecksSummary()}
 }
 const originalNext=window.goNext;
 window.goNext=function(){if(state.current===3&&!state.installDone){show('#prog-step-label','Complete installation before continuing');return}return originalNext()};
 window.startInstall=installActual;window.scheduleChecks=realChecks;
 document.addEventListener('DOMContentLoaded',()=>{
  const launch=get('#btn-launch');if(launch){launch.disabled=!native;launch.addEventListener('click',async(event)=>{
   if(!native)return;event.stopImmediatePropagation();launch.disabled=true;launch.textContent='Launching Synapse...';
   try{await native.launch();launch.textContent='Synapse launched'}catch(error){launch.textContent='Launch failed: '+String(error.message||error);launch.disabled=false}
  },true)}
  const auth=get('#auth-form');if(auth)auth.addEventListener('submit',event=>{
   event.preventDefault();event.stopImmediatePropagation();
   const err=get('#auth-error');if(err){err.textContent='Sign in securely after launching Synapse. Account credentials are never entered into setup.';err.classList.remove('hidden')}
  },true);
  if(!native){const notice=document.createElement('div');notice.style.cssText='position:fixed;bottom:8px;left:50%;transform:translateX(-50%);padding:7px 16px;border-radius:25px;background:#102046;color:#bdd9ff;z-index:10000';notice.textContent='DESIGN PREVIEW — no installation occurs';document.body.appendChild(notice)}
 });
})();
