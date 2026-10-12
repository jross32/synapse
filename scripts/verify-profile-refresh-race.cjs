'use strict';
// Run the actual provider in Chromium with controlled network promises.
// No daemon/account writes; verifies account-state ordering and cleanup.
const assert = require('node:assert/strict');
const path = require('node:path');
const http = require('node:http');
const esbuild = require('esbuild');
const { chromium } = require('playwright');
(async () => {
  const root = path.resolve(__dirname, '..');
  const mocks = {
    './profile-client': "export function getProfile(){return new Promise((resolve,reject)=>window.qa.pending.push({resolve,reject}));}",
    './projects-client': "export async function listProjects(){return [];}",
    './api-client': "export async function apiFetch(){return {ok:true,version:'0.2.219'};} export function bootstrapLocalToken(){return Promise.resolve();} export function getAuthToken(){return 'qa-only';} export function setDaemonBase(){} export function daemonBase(){return 'http://127.0.0.1';}",
    './ws-client': "export class SynapseWsClient { onState(){return ()=>{};} onEvent(){return ()=>{};} start(){} stop(){} }"
  };
  const result = await esbuild.build({
    absWorkingDir: root, bundle: true, write: false, format: 'iife',
    define: {'process.env.NODE_ENV': '"test"'},
    stdin: { resolveDir: root, loader: 'tsx', contents: `
      import React from 'react';
      import {createRoot} from 'react-dom/client';
      import {DaemonProvider,useDaemon} from './renderer/lib/daemon-context';
      window.qa={pending:[]};
      function Probe(){const state=useDaemon();window.qa.refresh=state.refreshProfile;
        return <div id="state">{JSON.stringify({signed:state.profile?.signed_in,error:state.profileError})}</div>;}
      const root=createRoot(document.getElementById('root'));
      window.qa.unmount=()=>root.unmount();
      root.render(<DaemonProvider><Probe/></DaemonProvider>);
    ` },
    plugins: [{name:'fake-account-transport', setup(build) {
      build.onResolve({filter:/^\.\/(profile-client|projects-client|api-client|ws-client)$/},
        args => args.importer.endsWith('daemon-context.tsx') ? {path:args.path,namespace:'qa'} : null);
      build.onLoad({filter:/.*/,namespace:'qa'},args=>({contents:mocks[args.path],loader:'js'}));
    }}]
  });
  const server=http.createServer((req,res)=> {
    res.setHeader('Content-Type',req.url==='/bundle.js'?'application/javascript':'text/html');
    res.end(req.url==='/bundle.js'?result.outputFiles[0].text:'<div id="root"></div><script src="/bundle.js"></script>');
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage(); const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto('http://127.0.0.1:'+server.address().port);
    await page.waitForFunction(()=>window.qa.pending.length===1);
    await page.evaluate(()=>window.qa.pending.shift().resolve({signed_in:false}));
    await page.waitForFunction(()=>document.getElementById('state').textContent.includes('"signed":false'));
    for(const scenario of ['signin','signout','stale-error']){
      await page.evaluate(()=>{window.qa.first=window.qa.refresh();window.qa.second=window.qa.refresh();});
      await page.waitForFunction(()=>window.qa.pending.length===2);
      const latestSigned=scenario!=='signout';
      await page.evaluate(signed=>window.qa.pending[1].resolve({signed_in:signed}),latestSigned);
      await page.waitForFunction(signed=>JSON.parse(document.getElementById('state').textContent).signed===signed,latestSigned);
      await page.evaluate(scenario=>{
        const older=window.qa.pending[0];
        if(scenario==='stale-error')older.reject(new Error('old-session-network-error'));
        else older.resolve({signed_in:scenario==='signout'});
      },scenario);
      const staleResult=await page.evaluate(async()=>{const result=await window.qa.first;await window.qa.second;window.qa.pending=[];return result;});
      assert.equal(staleResult,null,'Stale response must not become the action result');
      const state=await page.locator('#state').textContent();
      assert.equal(JSON.parse(state).signed,latestSigned);
      assert.equal(JSON.parse(state).error,null,'Stale failure must not poison the current session');
    }
    await page.evaluate(()=>{window.qa.last=window.qa.refresh();window.qa.unmount();window.qa.pending[0].resolve({signed_in:true});});
    assert.equal(await page.evaluate(()=>window.qa.last),null,'Unmounted request must be ignored');
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({passed:true,scenarios:['stale-signout-after-signin','stale-signin-after-signout','stale-error-after-success','unmounted-response'],scope:'Actual React provider; mocked account transport; no real accounts changed'}));
  }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
