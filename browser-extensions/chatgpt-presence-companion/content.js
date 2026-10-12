(() => {
  const STOP_SELECTOR = 'button[data-testid="stop-button"], button[aria-label*="Stop" i]';
  const ASSISTANT_SELECTOR = '[data-message-author-role="assistant"]';
  const USER_SELECTOR = '[data-message-author-role="user"]';
  const WORKED_RE = /\bworked\s+for\s+(?:(\d+)h\s*)?(?:(\d+)m\s*)?(?:(\d+)s)?\b/ig;
  let previousStatus = null;
  let generationStartedAt = null;
  let lastSentSignature = '';
  let debounceTimer = null;

  function visible(el) {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    return style.visibility !== 'hidden' && style.display !== 'none' && el.getClientRects().length > 0;
  }

  function conversationKey() {
    const match = location.pathname.match(/\/c\/([a-zA-Z0-9_-]+)/);
    return match ? match[1] : '';
  }

  function cleanTitle() {
    return (document.title || '').replace(/\s*[-�?"�?"]\s*ChatGPT\s*$/i, '').trim().slice(0, 500);
  }

  function latestText(selector, max = 4000) {
    const nodes = document.querySelectorAll(selector);
    if (!nodes.length) return '';
    return (nodes[nodes.length - 1].innerText || '').trim().slice(0, max);
  }

  function workedSeconds(text) {
    let match;
    let latest = null;
    WORKED_RE.lastIndex = 0;
    while ((match = WORKED_RE.exec(text || '')) !== null) {
      latest = Number(match[1] || 0) * 3600 + Number(match[2] || 0) * 60 + Number(match[3] || 0);
    }
    return latest;
  }

  function alertError() {
    for (const node of document.querySelectorAll('[role="alert"]')) {
      const text = (node.innerText || '').trim();
      if (/something went wrong|error generating|network error|failed to/i.test(text)) return text.slice(0, 1000);
    }
    return '';
  }

  function snapshot() {
    const generating = [...document.querySelectorAll(STOP_SELECTOR)].some(visible);
    const error = generating ? '' : alertError();
    const status = generating ? 'active' : (error ? 'error' : 'idle');
    const now = new Date();

    if (status === 'active' && previousStatus !== 'active') generationStartedAt = now.toISOString();

    let lastDurationSeconds = null;
    if (previousStatus === 'active' && status !== 'active') {
      lastDurationSeconds = workedSeconds(latestText(ASSISTANT_SELECTOR, 12000));
      if (lastDurationSeconds == null) {
        lastDurationSeconds = workedSeconds((document.body?.innerText || '').slice(-30000));
      }
    }

    const payload = {
      external_thread_key: conversationKey(),
      runtime_id: 'chatgpt',
      conversation_url: location.href,
      title: cleanTitle(),
      status,
      current_task: latestText(USER_SELECTOR, 1200),
      generation_started_at: status === 'active' ? generationStartedAt : null,
      last_duration_seconds: lastDurationSeconds,
      error
    };

    previousStatus = status;
    if (status !== 'active') generationStartedAt = null;
    return payload;
  }

  let lastNoticeState = '';
  function showWorkerActivity(status) {
    const project = location.pathname.includes('g-p-6a91003e980c81919b8920cfc9e0941e') && location.pathname.includes('/c/');
    const old = document.getElementById('synapse-worker-activity-toast');
    if (!project) { if (old) old.remove(); return; }
    if (status !== 'active') { if (old) old.remove(); lastNoticeState = status; return; }
    if (lastNoticeState === 'active') return;
    lastNoticeState = 'active';
    const el = document.createElement('div');
    el.id = 'synapse-worker-activity-toast';
    el.textContent = 'Synapse is active in this worker group';
    Object.assign(el.style, {position:'fixed',bottom:'90px',right:'18px',
      background:'#152a36',color:'#e7fbff',padding:'12px 17px',border:'1px solid #31bad8',
      borderRadius:'12px',boxShadow:'0 4px 22px #0007',font:'13px system-ui',
      zIndex:'2147483646',pointerEvents:'none'});
    document.body.appendChild(el);
    setTimeout(() => { if (el.isConnected) el.remove(); }, 4800);
  }

  function send(force = false) {
    const payload = snapshot();
    showWorkerActivity(payload.status);
    const signature = JSON.stringify(payload);
    if (!force && signature === lastSentSignature && payload.status !== 'active') return;
    lastSentSignature = signature;
    chrome.runtime.sendMessage({type: 'synapse-chatgpt-observation', payload}).catch(() => {});
  }

  const observer = new MutationObserver(() => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => send(false), 500);
  });
  observer.observe(document.documentElement, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ['aria-label', 'data-testid']
  });

  window.addEventListener('popstate', () => setTimeout(() => send(true), 300));
  window.addEventListener('hashchange', () => setTimeout(() => send(true), 300));

  let lastUrl = location.href;
  setInterval(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      send(true);
    } else {
      send(false);
    }
  }, 5000);

  send(true);
})();
