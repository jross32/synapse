import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const base = new URL('./', import.meta.url);
const workerSource = readFileSync(new URL('group-workers.js', base), 'utf8');
globalThis.workerFns = await import('data:text/javascript,' + encodeURIComponent(workerSource));
const projectId = globalThis.workerFns.PROJECT_KEY;
const chat = id => 'https://chatgpt.com/g/' + projectId + '-synapse2gpt-workers/c/' + id;
const tabs = [
  {id: 1, windowId: 7, url: chat('one'), groupId: -1},
  {id: 2, windowId: 7, url: chat('two'), groupId: -1},
  {id: 99, windowId: 7, url: 'https://example.com/', groupId: -1},
];
const groups = [];
const events = {};
const on = name => ({addListener: fn => {events[name] = fn;}});
const observations = [];
const session = {};
const local = {};
const menuEntries = [];
let badge = '';
let badgeColor = '';
let title = '';
let createdGroups = 0;
let nextTab = 100;
let safety = {canPark: true};
globalThis.chrome = {
  tabs: {
    query: async query => tabs.filter(t => query?.windowId == null || t.windowId === query.windowId),
    create: async data => {
      const tab = {id: nextTab++, groupId: -1, ...data};
      tabs.push(tab);
      return tab;
    },
    group: async ({tabIds, groupId}) => {
      if (groupId == null) {
        groupId = 20 + createdGroups++;
        groups.push({id: groupId, title: '', windowId: 7});
      }
      for (const id of tabIds) tabs.find(t => t.id === id).groupId = groupId;
      return groupId;
    },
    sendMessage: async () => safety,
    remove: async id => {
      const index = tabs.findIndex(t => t.id === id);
      assert.ok(index >= 0);
      const tab = tabs[index];
      tabs.splice(index, 1);
      events.tabRemoved(id, {windowId: tab.windowId});
    },
    onCreated: on('tabCreated'),
    onUpdated: on('tabUpdated'),
    onRemoved: on('tabRemoved'),
    onActivated: on('tabActivated'),
  },
  tabGroups: {
    query: async ({windowId}) => groups.filter(g => g.windowId === windowId),
    update: async (id, changes) => Object.assign(groups.find(g => g.id === id), changes),
  },
  windows: {
    getLastFocused: async () => ({id: 7}),
    onFocusChanged: on('focusChanged'),
    WINDOW_ID_NONE: -1,
  },
  runtime: {
    onMessage: on('message'),
    onInstalled: on('installed'),
    onStartup: on('startup'),
  },
  contextMenus: {
    onClicked: on('contextClicked'),
    removeAll: async () => {menuEntries.length = 0;},
    create: item => {menuEntries.push(item);return item.id;},
  },
  action: {
    onClicked: on('clicked'),
    setBadgeBackgroundColor: async args => {badgeColor = args.color;},
    setBadgeText: async args => {badge = args.text;},
    setTitle: async args => {title = args.title;},
  },
  storage: {
    local: {set: async values => Object.assign(local, values)},
    session: {
      get: async key => key in session ? {[key]: session[key]} : {},
      set: async values => Object.assign(session, values),
      remove: async key => {delete session[key];},
    },
  },
};
globalThis.fetch = async (url, options = {}) => {
  url = String(url);
  if (url.includes('/auth/local-token')) return {ok: true, json: async () => ({token: 'test'})};
  if (url.includes('/thread-presence/browser-observe')) {
    observations.push(JSON.parse(options.body));
    return {ok: true, json: async () => ({ok: true})};
  }
  throw new Error('Unexpected mock fetch: ' + url);
};
let source = readFileSync(new URL('service-worker.js', base), 'utf8');
source = source.replace(
  /^\uFEFF?import[\s\S]*?from '\.\/group-workers\.js';\s*/m,
  'const {ensureGroup, groupOpenWorkerTabs, getWorkerTabs, isWorkerConversation} = globalThis.workerFns;\n',
);
await import('data:text/javascript,' + encodeURIComponent(source));
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

events.installed();
await delay(100);
assert.equal(menuEntries.length, 1);
assert.equal(createdGroups, 1);
assert.equal(badge, '2');
assert.equal(local.workerCount, 2);
assert.equal(local.activeCount, 0);
assert.equal(groups[0].title, 'Synapse Workers (2)');
assert.equal(tabs[2].groupId, -1);

events.message({type: 'synapse-chatgpt-observation', payload: {
  external_thread_key: 'one', conversation_url: chat('one'), status: 'active',
}}, {tab: tabs[0]});
await delay(850);
assert.equal(local.activeCount, 1);
assert.equal(badge, '2');
assert.equal(badgeColor, '#15966B');
assert.equal(groups[0].title, 'Synapse Workers (2, 1 active)');
assert.equal(session['synapse-worker-tab-1'].url, chat('one'));

events.message({type: 'synapse-chatgpt-observation', payload: {
  external_thread_key: 'one', conversation_url: chat('one'), status: 'idle',
}}, {tab: tabs[0]});
await delay(850);
assert.equal(local.activeCount, 0);
assert.equal(groups[0].title, 'Synapse Workers (2)');

await events.clicked({windowId: 7});
assert.equal(groups.length, 1);
assert.equal(groups[0].collapsed, true);
assert.equal(badge, '2');
assert.equal(title, 'Synapse Workers: 2 open, 0 active');

// Simulate MV3 service-worker suspension: in-memory state is empty, session data remains.
events.message({type: 'synapse-chatgpt-observation', payload: {
  external_thread_key: 'two', conversation_url: chat('two'), status: 'idle',
}}, {tab: tabs[1]});
await delay(40);
safety = {canPark: false, generating: true};
events.contextClicked({menuItemId: 'synapse-park-worker'}, tabs[1]);
await delay(40);
assert.equal(tabs.some(t => t.id === 2), true, 'Active/unsafe tab must stay open');

safety = {canPark: true, generating: false, hasDraft: false};
events.contextClicked({menuItemId: 'synapse-park-worker'}, tabs[1]);
await delay(850);
assert.equal(tabs.some(t => t.id === 2), false, 'Idle tab should be parked');
assert.equal(badge, '1', 'Badge counts only open worker chats');
assert.ok(observations.some(x =>
  x.status === 'gone' && x.external_thread_key === 'two' &&
  x.conversation_url === chat('two')
), 'Close observation must preserve canonical conversation URL');

console.log('PASS: group creation/reuse, count, active/idle, safe park, persisted URL on close');
