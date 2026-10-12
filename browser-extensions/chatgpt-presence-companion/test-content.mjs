import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('./content.js',import.meta.url),'utf8');
const key='g-p-6a91003e980c81919b8920cfc9e0941e';
let generating=false;
let clock=Date.now();
class TestDate extends Date { static now(){return clock;} }
let draft="";
let onContentMessage=null;
const messages=[];
const timers=[];
const notices=new Map();
const document={
 title:'Worker Chat - ChatGPT',
 documentElement:{},
 body:{innerText:''},
 querySelectorAll(selector){
   if(selector.includes('stop-button'))return generating?[{
      getClientRects:()=>[{}]
   }]:[];
   if(selector.includes('contenteditable'))return draft?[{getClientRects:()=>[{}],value:draft}]:[];
   return [];
 },
 getElementById(id){return notices.get(id)||null;},
 createElement(){
   const el={style:{},textContent:'',isConnected:false};
   el.remove=()=>{el.isConnected=false;notices.delete(el.id);};
   return el;
 }
};
document.body.appendChild=el=>{el.isConnected=true;notices.set(el.id,el);};
const window={
 getComputedStyle:()=>({visibility:'visible',display:'block'}),
 addEventListener:()=>{}
};
const context={
 document,window,location:{pathname:'/g/'+key+'-synapse2gpt-workers/c/a123',href:'https://chatgpt.com/g/'+key+'-synapse2gpt-workers/c/a123'},
 chrome:{runtime:{sendMessage:async m=>{messages.push(m);},onMessage:{addListener:fn=>{onContentMessage=fn;}}}},
 MutationObserver:class{observe(){}},
 setInterval:fn=>timers.push(fn),
 setTimeout:()=>0,clearTimeout:()=>{},
 Date:TestDate,JSON,String,Number,RegExp
};
vm.runInNewContext(source,context,{filename:'content.js'});
assert.equal(messages.at(-1).payload.status,'idle');
generating=true;
timers[0]();
assert.equal(messages.at(-1).payload.status,'active');
assert.equal(notices.get('synapse-worker-activity-toast')?.textContent,'Synapse is active in this worker group');
generating=false;
timers[0]();
assert.equal(messages.at(-1).payload.status,'idle');
assert.equal(notices.size,0);
const idleCount = messages.length;
timers[0]();
assert.equal(messages.length,idleCount,'idle duplicate suppressed');
clock += 31000;
timers[0]();
assert.equal(messages.length,idleCount+1,'idle heartbeat refreshes live browser presence');
console.log('PASS: content observer idle -> active -> idle and in-tab activity notice lifecycle');

let response=null;
onContentMessage({type:'synapse-worker-can-park'},null,value=>response=value);
assert.equal(response.canPark,true);
generating=true;
onContentMessage({type:'synapse-worker-can-park'},null,value=>response=value);
assert.equal(response.canPark,false);
generating=false;
draft='Unsent prompt';
onContentMessage({type:'synapse-worker-can-park'},null,value=>response=value);
assert.equal(response.canPark,false);
draft='';
onContentMessage({type:'synapse-worker-can-park'},null,value=>response=value);
assert.equal(response.canPark,true);
console.log('PASS: park denied for active generation or unsent draft');
