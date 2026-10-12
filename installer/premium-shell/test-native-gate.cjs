'use strict';
const {chromium}=require(process.env.SYNAPSE_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),path=require('node:path');
const {pathToFileURL}=require('node:url');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1060,height:720}});const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(()=>{
   window.attempts=0;window.failChecks=false;
   window.synapseInstaller={
    preflight:async()=>({platform:'win32',architecture:'x64',osRelease:'10.0',freeBytes:5*1073741824,requiredBytes:2*1073741824,version:'0.2.219',meetsBasicPlatform:true,canInstall:!window.failChecks,packageError:window.failChecks?'Corrupt payload':null}),
    install:async()=>{window.attempts++;if(window.attempts===1)return {ok:false,error:'Install rejected'};return await new Promise(resolve=>{window.finishInstall=()=>resolve({ok:true,installedPath:'C:\\Synapse.exe',version:'0.2.219'})})},
    launch:async()=>{throw Error('Launch denied')},windowAction:()=>{},onStatus:()=>{}
   };
  });
  await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href);
  await page.click('#btn-welcome-start');await page.click('#btn-next');
  await page.waitForFunction(()=>!state.checking);
  assert.equal(await page.locator('#btn-next').isDisabled(),false);
  await page.screenshot({path:path.join(__dirname,'screenshots','unified-system-check.png')});
  await page.click('#btn-next');await page.waitForFunction(()=>state.installError);
  assert.equal(await page.evaluate(()=>state.installDone),false);assert.equal(await page.evaluate(()=>state.current),3);
  await page.click('#btn-next');await page.waitForFunction(()=>window.attempts===2);
  assert.equal(await page.locator('#btn-back').isDisabled(),true);
  await page.evaluate(()=>{goBack();showScreen(5);goNext()});
  assert.equal(await page.evaluate(()=>state.current),3);assert.equal(await page.evaluate(()=>window.attempts),2);
  await page.evaluate(()=>window.finishInstall());await page.waitForFunction(()=>state.installDone);
  await page.click('#btn-next');assert.equal(await page.evaluate(()=>state.current),4);
  await page.click('#btn-next');await page.click('#btn-next');await page.click('#btn-next');
  await page.click('#btn-launch');await page.waitForFunction(()=>document.querySelector('#launch-error').textContent.includes('Launch denied'));
  assert.equal(await page.evaluate(()=>state.launched),false);assert.equal(await page.locator('#btn-next').isDisabled(),true);
  await page.evaluate(()=>{state.installDone=false;state.furthest=2;state.checksOk=false;window.failChecks=true;showScreen(2)});
  await page.waitForFunction(()=>!state.checking);assert.equal(await page.locator('#btn-next').isDisabled(),true);
  await page.evaluate(()=>goNext());assert.equal(await page.evaluate(()=>state.current),2);
  assert.deepEqual(errors,[]);
  const preview=await browser.newPage();await preview.goto(pathToFileURL(path.join(__dirname,'index.html')).href+'#screen-6');
  assert.equal(await preview.evaluate(()=>state.installDone),false);assert.equal(await preview.locator('#btn-launch').isDisabled(),true);
  assert.match(await preview.locator('#runtime-notice').textContent(),/Design preview only/);
  console.log('PASS browser: actual retry, busy navigation lock, failed checks, launch failure and no preview success');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
