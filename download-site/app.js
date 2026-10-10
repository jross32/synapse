const menu=document.getElementById('menu-toggle');const nav=document.getElementById('primary-nav');menu?.addEventListener('click',()=>{const open=nav.classList.toggle('open');menu.setAttribute('aria-expanded',String(open));menu.setAttribute('aria-label',open?'Close menu':'Open menu')});nav?.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>{nav.classList.remove('open');menu?.setAttribute('aria-expanded','false');menu?.setAttribute('aria-label','Open menu')}));document.addEventListener('keydown',e=>{if(e.key==='Escape'){nav?.classList.remove('open');menu?.setAttribute('aria-expanded','false')}});
// Use only published stable GitHub releases and exact official installer assets.
const githubApi='https://api.github.com/repos/jross32/synapse/releases/latest';
const fallbackVersion='0.1.214';
const windowsLink=document.getElementById('download-windows');
const windowsDetail=document.getElementById('windows-detail');
const releaseStatus=document.getElementById('release-status');
async function updateLatestRelease(){
  try{
    const response=await fetch(githubApi,{headers:{Accept:'application/vnd.github+json'},cache:'no-store',signal:AbortSignal.timeout(9000)});
    if(!response.ok)throw new Error('GitHub releases temporarily unavailable');
    const release=await response.json();
    if(release.draft||release.prerelease||!/^v?\d+\.\d+\.\d+$/.test(release.tag_name))throw new Error('No verified stable version');
    const version=release.tag_name.replace(/^v/,'');
    const expected='Synapse.Setup.'+version+'.exe';
    const url='https://github.com/jross32/synapse/releases/download/'+release.tag_name+'/'+expected;
    const asset=(release.assets||[]).find(a=>a.name===expected&&a.state==='uploaded'&&a.size>50000000&&a.browser_download_url===url);
    if(!asset)throw new Error('Release has no verified Windows installer');
    if(windowsLink)windowsLink.href=asset.browser_download_url;
    if(windowsDetail)windowsDetail.textContent='v'+version+' · Official GitHub release';
    if(releaseStatus){releaseStatus.replaceChildren(document.createTextNode('Latest verified Windows release v'+version+' · '));const a=document.createElement('a');a.href=release.html_url;a.textContent='Release notes & checksums ↗';a.target='_blank';a.rel='noopener noreferrer';releaseStatus.appendChild(a)}
  }catch(e){
    if(windowsDetail)windowsDetail.textContent='v'+fallbackVersion+' · Verified fallback release';
    console.info('Synapse release check unavailable; using verified fallback.',e?.message||'');
  }
}
void updateLatestRelease();
