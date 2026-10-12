import {
  ensureGroup, groupOpenWorkerTabs, getWorkerTabs, isWorkerConversation,
} from './group-workers.js';

const BASE = 'http://127.0.0.1:7878/api/v1';
const PARK_MENU = 'synapse-park-worker';
const TAB_STORE_PREFIX = 'synapse-worker-tab-';
const tabKeys = new Map();
const tabUrls = new Map();
const activeTabs = new Set();
const refreshing = new Map();
const autoGroupTimers = new Map();
let cachedToken = '';
let tokenLoadedAt = 0;

async function localToken() {
  if (cachedToken && Date.now() - tokenLoadedAt < 60000) return cachedToken;
  const response = await fetch(BASE + '/auth/local-token', {cache: 'no-store'});
  if (!response.ok) throw new Error('Synapse token unavailable: ' + response.status);
  const body = await response.json();
  cachedToken = body.token || '';
  tokenLoadedAt = Date.now();
  if (!cachedToken) throw new Error('Synapse returned an empty token');
  return cachedToken;
}

async function postObservation(payload) {
  const response = await fetch(BASE + '/thread-presence/browser-observe', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Synapse-Token': await localToken()},
    body: JSON.stringify(payload),
  });
  if (response.status === 401) {
    cachedToken = '';
    tokenLoadedAt = 0;
  }
  if (!response.ok) throw new Error('Synapse observation failed: ' + response.status);
  return response.json();
}

async function rememberTab(tabId, key, url) {
  if (!isWorkerConversation(url)) return;
  tabKeys.set(tabId, key);
  tabUrls.set(tabId, url);
  // Session storage survives MV3 service-worker suspension but not Chrome restarts.
  await chrome.storage.session.set({
    [TAB_STORE_PREFIX + tabId]: {key, url},
  });
}

async function forgetTab(tabId) {
  const sessionKey = TAB_STORE_PREFIX + tabId;
  const prior = await chrome.storage.session.get(sessionKey).catch(() => ({}));
  await chrome.storage.session.remove(sessionKey).catch(() => {});
  const remembered = prior?.[sessionKey] || {};
  const key = tabKeys.get(tabId) || remembered.key;
  const url = tabUrls.get(tabId) || remembered.url;
  tabKeys.delete(tabId);
  tabUrls.delete(tabId);
  activeTabs.delete(tabId);
  return {key, url};
}

async function markGone(key, tabId, url = '') {
  if (!key) return;
  try {
    await postObservation({
      external_thread_key: key,
      runtime_id: 'chatgpt',
      browser_tab_id: String(tabId),
      conversation_url: isWorkerConversation(url) ? url : '',
      status: 'gone',
    });
  } catch {
    // Local daemon may be temporarily unavailable. The durable catalog
    // also derives parked presence after its heartbeat timeout.
  }
}

async function refreshBadge(windowId) {
  if (windowId == null) return;
  const tabs = (await chrome.tabs.query({})).filter(t => isWorkerConversation(t.url || ''));
  const ids = new Set(tabs.map(t => t.id));
  const active = [...activeTabs].filter(id => ids.has(id)).length;
  const count = tabs.length;
  await chrome.action.setBadgeBackgroundColor({color: active ? '#15966B' : '#6D4BCE'});
  await chrome.action.setBadgeText({text: String(count)});
  await chrome.action.setTitle({title: 'Synapse Workers: ' + count + ' open, ' + active + ' active'});
  await chrome.storage.local.set({workerCount: count, activeCount: active});
  return {count, active};
}

async function organize(windowId, collapse = false) {
  if (windowId == null) return;
  if (refreshing.has(windowId)) return refreshing.get(windowId);
  const operation = (async () => {
    const grouped = await groupOpenWorkerTabs(windowId, {collapse});
    const counts = await refreshBadge(windowId);
    if (grouped.groupId != null) {
      const localTabs = await getWorkerTabs(windowId);
      const active = localTabs.filter(t => activeTabs.has(t.id)).length;
      const title = 'Synapse Workers (' + localTabs.length +
        (active ? ', ' + active + ' active' : '') + ')';
      await chrome.tabGroups.update(grouped.groupId, {title, color: 'cyan'});
    }
    return {...grouped, ...counts};
  })().finally(() => refreshing.delete(windowId));
  refreshing.set(windowId, operation);
  return operation;
}

function scheduleOrganize(windowId) {
  if (windowId == null) return;
  clearTimeout(autoGroupTimers.get(windowId));
  autoGroupTimers.set(windowId, setTimeout(() => {
    autoGroupTimers.delete(windowId);
    void organize(windowId).catch(() => {});
  }, 700));
}

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type !== 'synapse-chatgpt-observation') return;
  const tabId = sender.tab?.id;
  if (tabId == null) return;
  const raw = message.payload || {};
  const key = raw.external_thread_key || ('pending-tab-' + tabId);
  const previousKey = tabKeys.get(tabId);
  const previousUrl = tabUrls.get(tabId) || '';
  const url = sender.tab?.url || raw.conversation_url || '';
  if (previousKey && previousKey !== key) {
    void markGone(previousKey, tabId, previousUrl);
  }
  if (isWorkerConversation(url)) {
    void rememberTab(tabId, key, url).catch(() => {});
    if (raw.status === 'active') activeTabs.add(tabId);
    else activeTabs.delete(tabId);
    scheduleOrganize(sender.tab.windowId);
  }
  void postObservation({
    ...raw,
    external_thread_key: key,
    browser_tab_id: String(tabId),
  }).catch(() => {});
});

chrome.tabs.onCreated.addListener(tab => scheduleOrganize(tab.windowId));
chrome.tabs.onUpdated.addListener((tabId, change, tab) => {
  if (change.url && !isWorkerConversation(change.url) && tabUrls.has(tabId)) {
    void forgetTab(tabId).then(prior => markGone(prior.key, tabId, prior.url));
  }
  if (change.url || change.status === 'complete') scheduleOrganize(tab.windowId);
});
chrome.tabs.onRemoved.addListener((tabId, info) => {
  // The canonical URL is retained in session storage for a suspended worker.
  void forgetTab(tabId).then(prior => markGone(prior.key, tabId, prior.url));
  scheduleOrganize(info.windowId);
});
chrome.tabs.onActivated.addListener(info => scheduleOrganize(info.windowId));
chrome.windows.onFocusChanged.addListener(windowId => {
  if (windowId !== chrome.windows.WINDOW_ID_NONE) scheduleOrganize(windowId);
});

function installContextMenu() {
  void chrome.contextMenus.removeAll().then(() => {
    chrome.contextMenus.create({
      id: PARK_MENU,
      title: 'Park Synapse worker (close tab, keep saved chat)',
      contexts: ['page'],
      documentUrlPatterns: ['https://chatgpt.com/g/*'],
    });
  }).catch(() => {});
}
chrome.runtime.onInstalled.addListener(() => {
  installContextMenu();
  void chrome.windows.getLastFocused().then(w => organize(w.id)).catch(() => {});
});
chrome.runtime.onStartup.addListener(() => {
  installContextMenu();
  void chrome.windows.getLastFocused().then(w => organize(w.id)).catch(() => {});
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== PARK_MENU || tab?.id == null ||
      !isWorkerConversation(tab.url || '')) return;
  void (async () => {
    // Do not close a worker in the middle of generating or editing a draft.
    const state = await chrome.tabs.sendMessage(tab.id, {
      type: 'synapse-worker-can-park',
    }).catch(() => null);
    if (!state || state.canPark !== true) {
      await chrome.action.setTitle({
        title: 'Worker not parked: active, unsent draft, or could not verify safety',
      });
      return;
    }
    await chrome.tabs.remove(tab.id);
  })().catch(() => {});
});

// Toolbar click prepares/reuses a single group; it never reopens parked workers.
chrome.action.onClicked.addListener(async tab => {
  try {
    const windowId = tab?.windowId ?? (await chrome.windows.getLastFocused()).id;
    await ensureGroup(windowId);
    await organize(windowId, true);
  } catch (error) {
    await chrome.action.setBadgeBackgroundColor({color: '#B42318'});
    await chrome.action.setBadgeText({text: '!'});
    await chrome.action.setTitle({
      title: 'Synapse grouping failed: ' + String(error.message || error),
    });
  }
});
