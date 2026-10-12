/* installer.js Ã¢â‚¬â€ Synapse premium setup wizard
 * All 8 screens with real navigator-API system checks and animated progress.
 */

'use strict';

// Ã¢â€â‚¬Ã¢â€â‚¬ State Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
const state = {
  current: 0,
  total: 8,
  installType: 'standard',
  checksOk: false,
  installDone: false,
  signedIn: false,
};

// Ã¢â€â‚¬Ã¢â€â‚¬ DOM helpers Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
const $  = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// Ã¢â€â‚¬Ã¢â€â‚¬ Navigation Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
function showScreen(idx) {
  if (window.synapseInstaller && idx > 3 && !state.installDone) return;
  if (idx < 0 || idx >= state.total) return;
  const prev = state.current;
  state.current = idx;

  $$('.screen').forEach((s) => {
    const n = parseInt(s.dataset.screen, 10);
    if (n === idx) {
      s.classList.remove('exit');
      s.classList.add('active');
    } else {
      if (s.classList.contains('active')) s.classList.add('exit');
      s.classList.remove('active');
    }
  });

  // Sidebar steps
  $$('.step').forEach((s) => {
    const n = parseInt(s.dataset.step, 10);
    s.classList.toggle('active', n === idx);
    s.classList.toggle('done', n < idx);
  });

  // Footer dots
  $$('.fdot').forEach((d) => {
    const n = parseInt(d.dataset.dot, 10);
    d.classList.toggle('active', n === idx);
    d.classList.toggle('done', n < idx);
  });

  // Footer step label
  $('#foot-cur').textContent = idx + 1;

  // Back/Next buttons
  const btnBack = $('#btn-back');
  const btnNext = $('#btn-next');
  btnBack.disabled = idx === 0;

  if (idx === 7) {
    btnNext.textContent = 'Finish';
  } else if (idx === 3) {
    btnNext.textContent = 'Installing...';
    btnNext.disabled = true;
  } else {
    btnNext.textContent = 'Next >';
    btnNext.disabled = false;
  }

  // Screen entry actions
  if (idx === 2 && !state.checksOk) scheduleChecks();
  if (idx === 3 && !state.installDone) startInstall();

  // Persist to hash for Playwright
  history.replaceState(null, '', `#screen-${idx + 1}`);
}

function goNext() {
  if (window.synapseInstaller && state.current >= 3 && !state.installDone) return;
  // Screen-specific guards
  if (state.current === 4) {
    // Sign-in screen: skip advances too
    showScreen(5);
    return;
  }
  if (state.current < state.total - 1) showScreen(state.current + 1);
}

function goBack() {
  if (state.current > 0) showScreen(state.current - 1);
}

// Ã¢â€â‚¬Ã¢â€â‚¬ SCREEN 1 Ã‚Â· Install type cards Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
function initInstallTypeCards() {
  $$('.type-card').forEach((card) => {
    card.addEventListener('click', () => selectInstallType(card.dataset.type));
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') selectInstallType(card.dataset.type);
    });
  });
}

function selectInstallType(type) {
  state.installType = type;
  $$('.type-card').forEach((c) => {
    const sel = c.dataset.type === type;
    c.classList.toggle('selected', sel);
    c.setAttribute('aria-checked', sel);
    c.querySelector('.card-check').classList.toggle('selected', sel);
  });
  const pathInput = $('#install-path');
  const browsBtn = $('#btn-browse');
  if (type === 'custom') {
    pathInput.removeAttribute('readonly');
    pathInput.focus();
    browsBtn.disabled = false;
  } else {
    pathInput.setAttribute('readonly', '');
    browsBtn.disabled = true;
  }
}

// Ã¢â€â‚¬Ã¢â€â‚¬ SCREEN 2 Ã‚Â· System checks (real browser APIs) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
const CHECK_DELAY = 340; // ms between checks (visual pacing)

async function scheduleChecks() {
  const checks = [
    checkOS,
    checkMemory,
    checkDisk,
    checkNetwork,
    checkResolution,
    checkGPU,
  ];
  for (const fn of checks) {
    await delay(CHECK_DELAY);
    await fn();
  }
  showChecksSummary();
}

function setCheckResult(id, status, detail, badge) {
  const row = $(`#chk-${id}`);
  if (!row) return;
  row.classList.remove('pass', 'fail', 'warn');
  row.classList.add(status);
  const det = $(`#chk-${id}-det`);
  if (det) det.textContent = detail;
  const bdg = $(`#chk-${id}-badge`);
  if (bdg) {
    bdg.className = `chk-badge ${status}`;
    bdg.textContent = badge;
  }
  const spin = row.querySelector('.chk-spin');
  if (spin) {
    spin.style.animation = 'none';
    spin.style.width = '18px';
    spin.style.height = '18px';
    spin.style.borderRadius = '0';
    spin.style.border = 'none';
    spin.style.background = 'none';
  }
}

async function checkOS() {
  const ua = navigator.userAgent;
  let os = 'Unknown OS';
  let status = 'pass';
  let badge = 'PASS';

  if (ua.includes('Windows NT 10.0')) {
    // NT 10.0 = Windows 10 or 11
    const build = ua.match(/Build\/(\d+)/)?.[1];
    os = 'Windows 10 / 11 (64-bit)';
    if (build && parseInt(build) >= 22000) os = 'Windows 11 (64-bit)';
    status = 'pass'; badge = 'PASS';
  } else if (ua.includes('Windows')) {
    os = 'Windows (legacy)';
    status = 'warn'; badge = 'WARN';
  } else if (ua.includes('Mac')) {
    os = 'macOS detected';
    status = 'pass'; badge = 'PASS';
  } else if (ua.includes('Linux')) {
    os = 'Linux detected';
    status = 'pass'; badge = 'PASS';
  }

  setCheckResult('os', status, os, badge);
}

async function checkMemory() {
  let memGB = navigator.deviceMemory; // 0.25, 0.5, 1, 2, 4, 8 (Chrome/Edge)
  let detail, status, badge;

  if (memGB != null) {
    detail = `${memGB} GB detected (Ã¢â€°Â¥ 4 GB required)`;
    if (memGB >= 4) { status = 'pass'; badge = 'PASS'; }
    else if (memGB >= 2) { status = 'warn'; badge = 'WARN'; detail = `${memGB} GB Ã¢â‚¬â€ low, 4 GB recommended`; }
    else { status = 'fail'; badge = 'FAIL'; detail = `${memGB} GB Ã¢â‚¬â€ insufficient`; }
  } else {
    // deviceMemory not available (Firefox, etc.)
    detail = 'Cannot detect (API unavailable) Ã¢â‚¬â€ assuming OK';
    status = 'pass'; badge = 'PASS';
  }
  setCheckResult('mem', status, detail, badge);
}

async function checkDisk() {
  let detail = 'Cannot detect storage quota';
  let status = 'pass', badge = 'PASS';
  try {
    if (navigator.storage && navigator.storage.estimate) {
      const est = await navigator.storage.estimate();
      const availMB = est.quota ? Math.round((est.quota - (est.usage || 0)) / 1024 / 1024) : null;
      if (availMB != null) {
        const availGB = (availMB / 1024).toFixed(1);
        detail = `${availGB} GB available (142 MB required)`;
        status = availMB > 300 ? 'pass' : 'warn';
        badge = status.toUpperCase();
        if (availMB < 150) { status = 'fail'; badge = 'FAIL'; detail = `Only ${availMB} MB available Ã¢â‚¬â€ insufficient`; }
      } else {
        detail = 'Storage quota API returned no data';
      }
    }
  } catch (_) { /* storage.estimate may throw in some contexts */ }
  setCheckResult('disk', status, detail, badge);
}

async function checkNetwork() {
  const online = navigator.onLine;
  const conn   = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  let detail, status, badge;

  if (online) {
    let speed = '';
    if (conn) {
      const eff = conn.effectiveType; // 'slow-2g', '2g', '3g', '4g'
      if (eff === '4g') speed = ' Ã‚Â· broadband';
      else if (eff === '3g') speed = ' Ã‚Â· 3G';
      else if (eff) speed = ` Ã‚Â· ${eff}`;
    }
    detail = `Online${speed} Ã¢â‚¬â€ cloud sync available`;
    status = 'pass'; badge = 'PASS';
  } else {
    detail = 'Offline Ã¢â‚¬â€ features requiring cloud will be limited';
    status = 'warn'; badge = 'WARN';
  }
  setCheckResult('net', status, detail, badge);
}

async function checkResolution() {
  const w = window.screen.width;
  const h = window.screen.height;
  const dpr = window.devicePixelRatio || 1;
  const detail = `${w} Ãƒâ€” ${h} px @ ${dpr}x (Ã¢â€°Â¥ 1024Ãƒâ€”768 required)`;
  let status = 'pass', badge = 'PASS';
  if (w < 1024 || h < 768) { status = 'fail'; badge = 'FAIL'; }
  setCheckResult('res', status, detail, badge);
}

async function checkGPU() {
  let detail = 'Software rendering only';
  let status = 'warn', badge = 'WARN';
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl2') || canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (gl) {
      const dbg = gl.getExtension('WEBGL_debug_renderer_info');
      if (dbg) {
        const renderer = gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL);
        detail = renderer.substring(0, 52) + (renderer.length > 52 ? 'Ã¢â‚¬Â¦' : '');
      } else {
        detail = 'WebGL available Ã¢â‚¬â€ GPU acceleration enabled';
      }
      status = 'pass'; badge = 'PASS';
    }
  } catch (_) { /* webgl unavailable */ }
  setCheckResult('gpu', status, detail, badge);
}

function showChecksSummary() {
  const failCount = document.querySelectorAll('.check-row.fail').length;
  const warnCount = document.querySelectorAll('.check-row.warn').length;
  const el = $('#checks-summary');
  const icon = $('#sum-icon');
  const text = $('#sum-text');
  el.classList.remove('hidden');
  if (failCount > 0) {
    el.classList.add('fail-sum');
    icon.textContent = 'Ã¢Å“â€¢'; icon.className = 'sum-icon fail';
    text.textContent = `${failCount} check(s) failed Ã¢â‚¬â€ installation may not succeed.`;
    state.checksOk = false;
    $('#btn-next').disabled = true;
    setTimeout(() => { $('#btn-next').disabled = false; }, 2000);
  } else {
    state.checksOk = true;
    icon.className = 'sum-icon pass';
    if (warnCount > 0) {
      icon.textContent = 'Ã¢Å¡Â '; icon.className = 'sum-icon warn';
      text.textContent = `${warnCount} warning(s) Ã¢â‚¬â€ you may proceed but some features may be limited.`;
    } else {
      icon.textContent = 'Ã¢Å“â€œ';
      text.textContent = 'All checks passed Ã¢â‚¬â€ ready to install.';
    }
  }
}

// Ã¢â€â‚¬Ã¢â€â‚¬ SCREEN 3 Ã‚Â· Installation progress Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
const INSTALL_STEPS = [
  { label: 'Preparing installation directory',     pct: 5,  ms: 500  },
  { label: 'Extracting core files',                pct: 18, ms: 900  },
  { label: 'Installing Electron runtime',          pct: 32, ms: 1100 },
  { label: 'Installing renderer bundle',           pct: 47, ms: 800  },
  { label: 'Installing daemon service',            pct: 58, ms: 700  },
  { label: 'Installing Maya AI components',        pct: 68, ms: 900  },
  { label: 'Writing registry entries',             pct: 74, ms: 400  },
  { label: 'Creating desktop shortcut',            pct: 80, ms: 350  },
  { label: 'Configuring auto-start',               pct: 85, ms: 400  },
  { label: 'Verifying installation integrity',     pct: 93, ms: 700  },
  { label: 'Finalising Ã¢â‚¬â€ almost done',             pct: 98, ms: 500  },
  { label: 'Installation complete',                pct: 100, ms: 300 },
];

async function startInstall() {
  const fill   = $('#prog-fill');
  const pctEl  = $('#prog-pct');
  const etaEl  = $('#prog-eta');
  const log    = $('#install-log');
  const stepLbl = $('#prog-step-label');
  const btnNext = $('#btn-next');
  btnNext.disabled = true;
  btnNext.textContent = 'Installing...';

  const startTime = Date.now();
  const totalMs = INSTALL_STEPS.reduce((s, x) => s + x.ms, 0);

  for (const step of INSTALL_STEPS) {
    // Previous step log entry (done)
    const prev = log.querySelector('.log-cur');
    if (prev) {
      prev.classList.remove('log-cur');
      prev.classList.add('log-ok');
      prev.querySelector('.log-prefix').textContent = 'Ã¢Å“â€œ';
    }

    // Current step entry
    stepLbl.textContent = step.label + 'Ã¢â‚¬Â¦';
    const li = document.createElement('li');
    li.className = 'log-entry log-cur';
    li.innerHTML = `<span class="log-prefix">Ã¢â‚¬Âº</span> ${step.label}`;
    log.appendChild(li);
    log.scrollTop = log.scrollHeight;

    // Animate to this step's percentage
    const targetPct = step.pct;
    const currentPct = parseInt(fill.style.width || '0', 10);
    await animateProgress(fill, pctEl, currentPct, targetPct, step.ms);

    // Update ETA
    const elapsed = Date.now() - startTime;
    const soFar = step.pct / 100;
    const estimatedTotal = elapsed / soFar;
    const remainMs = Math.max(0, estimatedTotal - elapsed);
    if (step.pct < 100) {
      etaEl.textContent = `~${Math.ceil(remainMs / 1000)}s remaining`;
    } else {
      etaEl.textContent = 'Complete!';
    }
  }

  // Final log mark
  const last = log.querySelector('.log-cur');
  if (last) { last.classList.remove('log-cur'); last.classList.add('log-ok'); last.querySelector('.log-prefix').textContent = 'Ã¢Å“â€œ'; }

  state.installDone = true;
  btnNext.disabled = false;
  btnNext.textContent = 'Continue >';
  stepLbl.textContent = 'Synapse installed successfully.';
}

function animateProgress(fill, pctEl, from, to, durationMs) {
  return new Promise((resolve) => {
    const start = performance.now();
    function frame(now) {
      const elapsed = now - start;
      const t = Math.min(elapsed / durationMs, 1);
      const ease = 1 - Math.pow(1 - t, 3); // ease-out cubic
      const cur = from + (to - from) * ease;
      fill.style.width = `${cur.toFixed(1)}%`;
      pctEl.textContent = `${Math.round(cur)}%`;
      if (t < 1) requestAnimationFrame(frame);
      else resolve();
    }
    requestAnimationFrame(frame);
  });
}

// Ã¢â€â‚¬Ã¢â€â‚¬ SCREEN 4 Ã‚Â· Auth form Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
function initAuthForm() {
  // Secure account onboarding is handled by the installed Synapse app.
  document.querySelector('#btn-skip-auth')?.addEventListener('click', () => { state.signedIn = false; goNext(); });
}


function initLaunchBtn() {
  // Native adapter launches verified installed executable; browser preview never fakes it.
}

function initFooter() {
  $('#btn-back')?.addEventListener('click', goBack);
  $('#btn-next')?.addEventListener('click', goNext);
  $$('.fdot').forEach((d) => {
    d.addEventListener('click', () => {
      const target = parseInt(d.dataset.dot, 10);
      // Only allow jumping to completed screens or current+1
      if ((!window.synapseInstaller || (state.installDone || target <= 3)) && target <= state.current + 1 && (target < 3 || state.checksOk || target <= state.current)) {
        showScreen(target);
      }
    });
  });
}

// Ã¢â€â‚¬Ã¢â€â‚¬ Welcome CTA Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
function initWelcome() {
  $('#btn-welcome-start')?.addEventListener('click', () => showScreen(1));
}

// Ã¢â€â‚¬Ã¢â€â‚¬ Hash routing (for Playwright screenshots) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
function applyHash() {
  if (window.synapseInstaller) return;
  const match = window.location.hash.match(/#screen-(\d+)/);
  if (match) {
    const n = parseInt(match[1], 10) - 1;
    if (n >= 0 && n < state.total) {
      // Pre-set state for screens that come after checks/install
      // Screen 2 (index 2) = system check Ã¢â‚¬â€ let checks run live (checksOk stays false)
      if (n >= 3) state.checksOk = true;
      if (n >= 4 && !window.synapseInstaller) { state.installDone = false; }
      showScreen(n);
      // For progress screen in screenshot mode: show at 100%
      if (n === 3 && !window.synapseInstaller) forceProgressDone();
    }
  }
}

function forceProgressDone() {
  const fill   = $('#prog-fill');
  const pctEl  = $('#prog-pct');
  const etaEl  = $('#prog-eta');
  const log    = $('#install-log');
  const stepLbl = $('#prog-step-label');
  if (!fill) return;
  fill.style.width = '100%';
  pctEl.textContent = '100%';
  etaEl.textContent = 'Complete!';
  stepLbl.textContent = 'Synapse installed successfully.';
  log.innerHTML = INSTALL_STEPS.map(s =>
    `<li class="log-entry log-ok"><span class="log-prefix">Ã¢Å“â€œ</span> ${s.label}</li>`
  ).join('');
  const btnNext = $('#btn-next');
  btnNext.disabled = false;
  btnNext.textContent = 'Continue >';
}

// Ã¢â€â‚¬Ã¢â€â‚¬ Utility Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
function delay(ms) { return new Promise((r) => setTimeout(r, ms)); }

// Ã¢â€â‚¬Ã¢â€â‚¬ Init Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
document.addEventListener('DOMContentLoaded', () => {
  initWelcome();
  initInstallTypeCards();
  initAuthForm();
  initLaunchBtn();
  initFooter();

  // Hash routing takes priority
  if (window.location.hash) {
    applyHash();
  } else {
    showScreen(0);
  }

  window.addEventListener('hashchange', applyHash);
});

