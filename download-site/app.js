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

// Rotating hero copy: 30-second readable holds, then a rapid erase-and-type transition.
// The original headline stays in HTML for search engines, no-JS browsers, and reduced motion.
const heroLede = document.querySelector('.hero .lede');
if (heroLede && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  const heroMessages = [
    heroLede.textContent.trim(),
    'One command center for your AI assistants, projects, favorite tools, and connected computers.',
    'Give your AI staff clear roles. Keep their goals, assignments, and progress in view.',
    'Turn big ideas into real builds with coding agents, shared tools, and an organized workspace.',
    'See what your AI workers are doing, what needs attention, and what comes next.',
    'Keep your projects, decisions, and development history connected instead of scattered across tabs.',
    'Bring ChatGPT, Claude, Codex, and other AI workflows closer to the tools you already use.',
    'Build, test, improve, and repeat—without losing track of the work already in motion.',
    'From your desktop to your next device, keep your connected workspace ready to grow.',
    'Create with AI. Coordinate your team. Stay in control of the projects that matter most.'
  ];
  // Time spent in a hidden tab does not count toward the 30-second display period.
  function visibleDelay(milliseconds) {
    return new Promise(resolve => {
      let remaining = milliseconds;
      let timer;
      let startedAt = 0;
      function finish() {
        document.removeEventListener('visibilitychange', onVisibilityChange);
        resolve();
      }
      function resume() {
        if (document.hidden) return;
        startedAt = performance.now();
        timer = window.setTimeout(finish, remaining);
      }
      function onVisibilityChange() {
        window.clearTimeout(timer);
        if (document.hidden) {
          remaining = Math.max(0, remaining - (performance.now() - startedAt));
        } else {
          resume();
        }
      }
      document.addEventListener('visibilitychange', onVisibilityChange);
      resume();
    });
  }
  async function cycleHeroMessages() {
    let current = 0;
    while (heroLede.isConnected) {
      await visibleDelay(30000);
      const next = (current + 1) % heroMessages.length;
      heroLede.classList.add('is-typing');
      const outgoing = heroMessages[current];
      for (let length = outgoing.length - 1; length >= 0; length--) {
        heroLede.textContent = outgoing.slice(0, length);
        await visibleDelay(7);
      }
      const incoming = heroMessages[next];
      for (let length = 1; length <= incoming.length; length++) {
        heroLede.textContent = incoming.slice(0, length);
        await visibleDelay(16);
      }
      heroLede.classList.remove('is-typing');
      current = next;
    }
  }
  void cycleHeroMessages();
}
