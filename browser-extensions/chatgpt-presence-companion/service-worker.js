import {groupSynapseWorkers, groupOpenWorkerTabs, getWorkerTabs, isWorkerConversation} from './group-workers.js';
const BASE = 'http://127.0.0.1:7878/api/v1';
let cachedToken = '';
let tokenLoadedAt = 0;
const tabKeys = new Map();
const activeTabs = new Set();
const refreshing = new Map();
const autoGroupTimers = new Map();

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
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-Synapse-Token': await localToken()},
    body: JSON.stringify(payload)
  });
  if (response.status === 401) { cachedToken = ''; tokenLoadedAt = 0; }
  if (!response.ok) throw new Error('Synapse observation failed: ' + response.status);
  return response.json();
}
async function markGone(key, tabId) {
  if (!key) return;
  try {
    await postObservation({external_thread_key: key, runtime_id: 'chatgpt',
      browser_tab_id: String(tabId), status: 'gone'});
  } catch {}
}
async function refreshBadge(windowId) {
  if (windowId == null) return;
  const tabs = (await chrome.tabs.query({})).filter(t => isWorkerConversation(t.url || ''));
  const ids = new Set(tabs.map(t => t.id));
  const active = [...activeTabs].filter(id => ids.has(id)).length;
  const count = tabs.length;
  await chrome.action.setBadgeBackgroundColor({color: active ? '#15966B' : '#6D4BCE'});
  await chrome.action.setBadgeText({text: count ? String(count) : '0'});
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
      const localActive = localTabs.filter(t => activeTabs.has(t.id)).length;
      const label = 'Synapse Workers (' + localTabs.length + (localActive ? ', ' + localActive + ' active' : '') + ')';
      await chrome.tabGroups.update(grouped.groupId, {title: label, color: 'cyan'});
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
  const previous = tabKeys.get(tabId);
  tabKeys.set(tabId, key);
  if (previous && previous !== key) void markGone(previous, tabId);
  if (isWorkerConversation(sender.tab?.url || raw.conversation_url || '')) {
    if (raw.status === 'active') activeTabs.add(tabId);
    else activeTabs.delete(tabId);
    scheduleOrganize(sender.tab.windowId);
  }
  void postObservation({...raw, external_thread_key: key,
    browser_tab_id: String(tabId)}).catch(() => {});
});
chrome.tabs.onCreated.addListener(tab => scheduleOrganize(tab.windowId));
chrome.tabs.onUpdated.addListener((id, change, tab) => {
  if (change.url || change.status === 'complete') scheduleOrganize(tab.windowId);
});
chrome.tabs.onRemoved.addListener((tabId, info) => {
  const key = tabKeys.get(tabId);
  tabKeys.delete(tabId);
  activeTabs.delete(tabId);
  if (key) void markGone(key, tabId);
  scheduleOrganize(info.windowId);
});
chrome.tabs.onActivated.addListener(info => scheduleOrganize(info.windowId));
chrome.windows.onFocusChanged.addListener(windowId => {
  if (windowId !== chrome.windows.WINDOW_ID_NONE) scheduleOrganize(windowId);
});
chrome.runtime.onInstalled.addListener(() => {
  void chrome.windows.getLastFocused().then(w => organize(w.id)).catch(() => {});
});
chrome.runtime.onStartup.addListener(() => {
  void chrome.windows.getLastFocused().then(w => organize(w.id)).catch(() => {});
});
// Click the extension to collect any registered but unopened Synapse worker chats.
chrome.action.onClicked.addListener(async tab => {
  try {
    const windowId = tab?.windowId ?? (await chrome.windows.getLastFocused()).id;
    const token = await localToken().catch(() => '');
    await groupSynapseWorkers(token, windowId);
    await organize(windowId, true);
  } catch (error) {
    await chrome.action.setBadgeBackgroundColor({color: '#B42318'});
    await chrome.action.setBadgeText({text: '!'});
    await chrome.action.setTitle({title: 'Synapse grouping failed: ' + String(error.message || error)});
  }
});
