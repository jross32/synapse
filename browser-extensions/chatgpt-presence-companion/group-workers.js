// One reusable Chrome tab group for the user's Synapse2GPT Workers project.
export const PROJECT_KEY = 'g-p-6a91003e980c81919b8920cfc9e0941e';
export const PROJECT_URL = 'https://chatgpt.com/g/' + PROJECT_KEY + '/project';
export const GROUP_TITLE = 'Synapse Workers';
const API = 'http://127.0.0.1:7878/api/v1';
export function isWorkerUrl(value) {
  try {
    const u = new URL(value);
    return u.protocol === 'https:' && u.hostname === 'chatgpt.com' &&
      (u.pathname.startsWith('/g/' + PROJECT_KEY + '/') || u.pathname.startsWith('/g/' + PROJECT_KEY + '-')) &&
      (u.pathname.endsWith('/project') || u.pathname.includes('/c/'));
  } catch { return false; }
}
export function isWorkerConversation(value) {
  return isWorkerUrl(value) && new URL(value).pathname.includes('/c/');
}
export function matchesGroupTitle(title) {
  return /synapse *workers|synapseworkers|synapse2gpt workers/i.test(title || '');
}
export async function getWorkerTabs(windowId) {
  return (await chrome.tabs.query({windowId})).filter(t => isWorkerConversation(t.url || ''));
}
export async function findGroup(windowId) {
  return (await chrome.tabGroups.query({windowId})).find(g => matchesGroupTitle(g.title));
}
export async function ensureGroup(windowId, firstTabId) {
  const existing = await findGroup(windowId);
  if (existing) return existing.id;
  if (firstTabId == null) {
    const home = await chrome.tabs.create({windowId, url: PROJECT_URL, active: false});
    firstTabId = home.id;
  }
  const id = await chrome.tabs.group({tabIds: [firstTabId]});
  await chrome.tabGroups.update(id, {title: GROUP_TITLE, color: 'cyan', collapsed: false});
  return id;
}
export async function groupOpenWorkerTabs(windowId, {collapse = false} = {}) {
  const tabs = await getWorkerTabs(windowId);
  const existing = await findGroup(windowId);
  if (!tabs.length && !existing) return {grouped: 0, reason: 'No open Synapse worker chats'};
  const id = existing?.id ?? await ensureGroup(windowId, tabs[0]?.id);
  const ids = tabs.map(t => t.id);
  const missing = tabs.filter(t => t.groupId !== id).map(t => t.id);
  if (missing.length) await chrome.tabs.group({tabIds: missing, groupId: id});
  if (collapse) await chrome.tabGroups.update(id, {collapsed: true});
  return {grouped: ids.length, groupId: id};
}
export async function groupSynapseWorkers(token, windowId) {
  // A disconnected backend must not prevent grouping ALREADY OPEN worker tabs.
  let urls = [];
  try {
    const response = await fetch(API + '/chatgpt-workers?include_archived=false', {
      headers: {'X-Synapse-Token': token}, cache: 'no-store'
    });
    if (response.ok) {
      const data = await response.json();
      urls = [...new Set((data.workers || []).map(w => w.conversation_url).filter(isWorkerConversation))];
    }
  } catch {}
  if (windowId == null) windowId = (await chrome.windows.getLastFocused()).id;
  const existing = await chrome.tabs.query({});
  const live = await getWorkerTabs(windowId);
  if (!urls.length && !live.length) {
    // Button click is also a quick way to prepare a new, empty worker group.
    await ensureGroup(windowId);
    return {grouped: 0, reason: 'Worker group ready; open a chat in Synapse2GPT Workers'};
  }
  const groupId = await ensureGroup(windowId, live[0]?.id);
  for (const url of urls) {
    const open = existing.find(t => t.url === url);
    if (open) {
      if (open.windowId === windowId) await chrome.tabs.group({tabIds: [open.id], groupId});
      // Never pull a user's existing tab out of another window.
    } else {
      const tab = await chrome.tabs.create({url, windowId, active: false});
      await chrome.tabs.group({tabIds: [tab.id], groupId});
    }
  }
  return groupOpenWorkerTabs(windowId, {collapse: true});
}
