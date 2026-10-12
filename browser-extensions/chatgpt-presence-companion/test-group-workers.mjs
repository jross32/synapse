import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = readFileSync(new URL('./group-workers.js', import.meta.url), 'utf8');
const mod = await import('data:text/javascript,' + encodeURIComponent(source));
const project = mod.PROJECT_KEY;
const url = n => 'https://chatgpt.com/g/' + project + '-synapse2gpt-workers/c/' + n;
assert.equal(mod.isWorkerConversation(url('abc')), true);
assert.equal(mod.isWorkerConversation(mod.PROJECT_URL), false);
assert.equal(mod.isWorkerConversation('https://other.example.com/g/' + project + '/c/abc'), false);
assert.equal(mod.isWorkerConversation('https://chatgpt.com/g/g-p-other/c/a'), false);
assert.equal(mod.matchesGroupTitle('Synapseworkers ChatGPT automation setup'), true);
assert.equal(mod.matchesGroupTitle('Synapse Workers (2, 1 active)'), true);
const tabs = [{id:1,windowId:7,url:url('one'),groupId:-1},
              {id:2,windowId:7,url:url('two'),groupId:-1},
              {id:99,windowId:7,url:'https://example.com/',groupId:-1}];
const groups = [];
let nextTab = 100;
let nextGroup = 10;
let creates = 0;
globalThis.chrome = {
 tabs: {
  query: async filter => tabs.filter(t => filter?.windowId == null || t.windowId === filter.windowId),
  create: async data => { const t={id:nextTab++,groupId:-1,...data};tabs.push(t);return t; },
  group: async ({tabIds,groupId}) => {
    const ids=Array.isArray(tabIds)?tabIds:[tabIds];
    if(groupId == null){ groupId=nextGroup++;groups.push({id:groupId,title:'',windowId:7});creates++; }
    for(const id of ids){const t=tabs.find(t=>t.id===id);assert.ok(t);t.groupId=groupId;}
    return groupId;
  }
 },
 tabGroups:{
  query:async ({windowId})=>groups.filter(g=>g.windowId===windowId),
  update:async (id,changes)=>{const g=groups.find(g=>g.id===id);Object.assign(g,changes);return g;}
 },
 windows:{getLastFocused:async()=>({id:7})}
};
const first=await mod.groupOpenWorkerTabs(7);
assert.equal(first.grouped,2);
assert.equal(creates,1);
assert.equal(tabs[0].groupId,tabs[1].groupId);
assert.equal(tabs[2].groupId,-1);
const second=await mod.groupOpenWorkerTabs(7);
assert.equal(second.grouped,2);
assert.equal(creates,1);
groups[0].title='Synapseworkers ChatGPT automation setup';
const third=await mod.groupOpenWorkerTabs(7,{collapse:true});
assert.equal(third.grouped,2);
assert.equal(groups[0].collapsed,true);
globalThis.fetch=async()=>({ok:true,json:async()=>({workers:[]})});
const empty=await mod.groupSynapseWorkers('test-token',7);
assert.equal(empty.grouped,2);
assert.equal(creates,1);
globalThis.fetch=async()=>({ok:true,json:async()=>({workers:[{conversation_url:url('three')}]})});
const registered=await mod.groupSynapseWorkers('test-token',7);
assert.equal(registered.grouped,3);
assert.equal(creates,1);
assert.equal(tabs.filter(t=>t.url===url('three')).length,1);
const again=await mod.groupSynapseWorkers('test-token',7);
assert.equal(again.grouped,3);
assert.equal(tabs.filter(t=>t.url===url('three')).length,1);
console.log('PASS: URL scope, create/reuse, idempotent grouping, empty-registry fallback, saved URLs, collapse, unrelated tabs');
// Clicking from an empty profile creates a project-home tab and reusable group.
tabs.splice(0,tabs.length);
groups.splice(0,groups.length);
globalThis.fetch=async()=>({ok:true,json:async()=>({workers:[]})});
const prepared=await mod.groupSynapseWorkers('test-token',7);
assert.equal(prepared.grouped,0);
assert.equal(groups.length,1);
assert.equal(tabs.length,1);
assert.equal(tabs[0].url,mod.PROJECT_URL);
const reuse=await mod.groupSynapseWorkers('test-token',7);
assert.equal(reuse.grouped,0);
assert.equal(groups.length,1);
assert.equal(tabs.length,1);
console.log('PASS: empty button creates project-home group, repeats idempotently');
