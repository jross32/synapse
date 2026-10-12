import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const base=new URL('./',import.meta.url);
const workerSource=readFileSync(new URL('group-workers.js',base),'utf8');
globalThis.workerFns=await import('data:text/javascript,'+encodeURIComponent(workerSource));
const key=globalThis.workerFns.PROJECT_KEY;
const chat=n=>'https://chatgpt.com/g/'+key+'-synapse2gpt-workers/c/'+n;
const tabs=[
 {id:1,windowId:7,url:chat('one'),groupId:-1},
 {id:2,windowId:7,url:chat('two'),groupId:-1},
 {id:99,windowId:7,url:'https://example.com/',groupId:-1}
];
const groups=[];
const events={};
const on=name=>({addListener:fn=>events[name]=fn});
let badge='',badgeColor='',title='',createdGroups=0, nextTab=100;
const storage={};
globalThis.chrome={
 tabs:{
  query:async filter=>tabs.filter(t=>filter?.windowId==null||t.windowId===filter.windowId),
  create:async d=>{const t={id:nextTab++,groupId:-1,...d};tabs.push(t);return t;},
  group:async ({tabIds,groupId})=>{
   if(groupId==null){groupId=20+createdGroups++;groups.push({id:groupId,title:'',windowId:7});}
   for(const id of tabIds)tabs.find(t=>t.id===id).groupId=groupId;
   return groupId;
  },
  onCreated:on('tabCreated'),onUpdated:on('tabUpdated'),onRemoved:on('tabRemoved'),
  onActivated:on('tabActivated')
 },
 tabGroups:{
  query:async ({windowId})=>groups.filter(g=>g.windowId===windowId),
  update:async (id,change)=>Object.assign(groups.find(g=>g.id===id),change)
 },
 windows:{getLastFocused:async()=>({id:7}),onFocusChanged:on('focusChanged'),WINDOW_ID_NONE:-1},
 runtime:{onMessage:on('message'),onInstalled:on('installed'),onStartup:on('startup')},
 action:{
  onClicked:on('clicked'),
  setBadgeBackgroundColor:async a=>{badgeColor=a.color;},
  setBadgeText:async a=>{badge=a.text;},
  setTitle:async a=>{title=a.title;}
 },
 storage:{local:{set:async x=>Object.assign(storage,x)}}
};
globalThis.fetch=async input=>{
 const u=String(input);
 if(u.includes('/auth/local-token'))return {ok:true,json:async()=>({token:'test'})};
 if(u.includes('/thread-presence/browser-observe'))return {ok:true,json:async()=>({ok:true})};
 if(u.includes('/chatgpt-workers'))return {ok:true,json:async()=>({workers:[]})};
 throw new Error('unexpected mock fetch '+u);
};
let sw=readFileSync(new URL('service-worker.js',base),'utf8');
sw=sw.replace(/^\uFEFF?import .*?;\s*/m,`const {groupSynapseWorkers, groupOpenWorkerTabs, getWorkerTabs, isWorkerConversation} = globalThis.workerFns;\n`);
await import('data:text/javascript,'+encodeURIComponent(sw));
const delay=ms=>new Promise(r=>setTimeout(r,ms));
events.installed();
await delay(60);
assert.equal(createdGroups,1);
assert.equal(badge,'2');
assert.equal(storage.workerCount,2);
assert.equal(storage.activeCount,0);
assert.equal(groups[0].title,'Synapse Workers (2)');
assert.equal(tabs[2].groupId,-1);
events.message({type:'synapse-chatgpt-observation',payload:{
 external_thread_key:'one',conversation_url:chat('one'),status:'active'
}},{tab:tabs[0]});
await delay(850);
assert.equal(badge,'2');
assert.equal(storage.activeCount,1);
assert.equal(badgeColor,'#15966B');
assert.equal(groups[0].title,'Synapse Workers (2, 1 active)');
events.message({type:'synapse-chatgpt-observation',payload:{
 external_thread_key:'one',conversation_url:chat('one'),status:'idle'
}},{tab:tabs[0]});
await delay(850);
assert.equal(storage.activeCount,0);
assert.equal(groups[0].title,'Synapse Workers (2)');
await events.clicked({windowId:7});
assert.equal(groups.length,1);
assert.equal(groups[0].collapsed,true);
assert.equal(badge,'2');
assert.equal(title,'Synapse Workers: 2 open, 0 active');
console.log('PASS: automatic creation, count=2, live active=1, idle recovery, toolbar reuse/collapse');
