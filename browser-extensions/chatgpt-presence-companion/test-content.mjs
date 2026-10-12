import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('./content.js',import.meta.url),'utf8');
const key='g-p-6a91003e980c81919b8920cfc9e0941e';
let generating=false;
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
 chrome:{runtime:{sendMessage:async m=>{messages.push(m);}}},
 MutationObserver:class{observe(){}},
 setInterval:fn=>timers.push(fn),
 setTimeout:()=>0,clearTimeout:()=>{},
 Date,JSON,String,Number,RegExp
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
console.log('PASS: content observer idle -> active -> idle and in-tab activity notice lifecycle');
