const BASE = 'http://127.0.0.1:7878/api/v1';
let cachedToken = '';
let tokenLoadedAt = 0;
const tabKeys = new Map();

async function localToken() {
  if (cachedToken && Date.now() - tokenLoadedAt < 60000) return cachedToken;
  const response = await fetch(BASE + '/auth/local-token', {cache: 'no-store'});
  if (!response.ok) throw new Error('Synapse local token unavailable: ' + response.status);
  const body = await response.json();
  cachedToken = body.token || '';
  tokenLoadedAt = Date.now();
  if (!cachedToken) throw new Error('Synapse returned an empty local token');
  return cachedToken;
}

async function postObservation(payload) {
  const token = await localToken();
  const response = await fetch(BASE + '/thread-presence/browser-observe', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Synapse-Token': token},
    body: JSON.stringify(payload)
  });
  if (response.status === 401) {
    cachedToken = '';
    tokenLoadedAt = 0;
  }
  if (!response.ok) throw new Error('Synapse observation failed: ' + response.status);
  return response.json();
}

async function markGone(key, tabId) {
  if (!key) return;
  try {
    await postObservation({
      external_thread_key: key,
      runtime_id: 'chatgpt',
      browser_tab_id: String(tabId),
      status: 'gone'
    });
  } catch {}
}

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type !== 'synapse-chatgpt-observation') return;
  const tabId = sender.tab?.id;
  if (tabId == null) return;

  const raw = message.payload || {};
  const key = raw.external_thread_key || ('pending-tab-' + tabId);
  const previous = tabKeys.get(tabId);
  tabKeys.set(tabId, key);

  if (previous && previous !== key) void markGone(previous, tabId);

  void postObservation({...raw, external_thread_key: key, browser_tab_id: String(tabId)}).catch(() => {});
});

chrome.tabs.onRemoved.addListener((tabId) => {
  const key = tabKeys.get(tabId);
  tabKeys.delete(tabId);
  if (key) void markGone(key, tabId);
});