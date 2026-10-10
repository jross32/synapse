#!/usr/bin/env node
// One scenario per process. This is invoked by visual-qa-suite.mjs, not a shared browser session.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
const [manifestFile,scenarioIndex,outDir]=process.argv.slice(2);
const manifest=JSON.parse(await fs.readFile(manifestFile,'utf8'));
const test=manifest.scenarios?.[Number(scenarioIndex)];
if(!test)throw new Error('Invalid scenario index');
const root=new URL(manifest.baseUrl);
if(!['http:','https:'].includes(root.protocol))throw new Error('Only HTTP(S) URLs allowed');
const steps=test.steps||[];
const mutations=new Set(['click','fill','upload','check','press']);
if(steps.some(s=>mutations.has(s.action))&&!(manifest.authorizedTestEnvironment===true&&test.allowInteractions===true)){
 throw new Error('Interactive steps require authorizedTestEnvironment=true and scenario.allowInteractions=true');
}
const safeName=(test.name||'case').replace(/[^a-z0-9-]/gi,'_').slice(0,50);
const out=path.resolve(outDir);await fs.mkdir(out,{recursive:true});
const report={name:test.name,viewport:test.viewport||{width:390,height:844},url:root.origin,steps:[],errors:[],consoleErrors:[],requestsFailed:[],status:'FAIL',screenshot:null};
let browser,ctx,page;
try{
 browser=await chromium.launch({headless:true,timeout:10000,executablePath:process.env.SYNAPSE_CHROME_PATH||undefined});
 ctx=await browser.newContext({viewport:report.viewport,isMobile:report.viewport.width<700,hasTouch:report.viewport.width<700,storageState:test.storageStatePath||undefined,acceptDownloads:false});
 page=await ctx.newPage();page.setDefaultTimeout(5500);
 page.on('pageerror',e=>report.errors.push(e.message));
 page.on('console',m=>{if(m.type()==='error')report.consoleErrors.push(m.text().slice(0,350))});
 page.on('requestfailed',req=>report.requestsFailed.push({resource:req.resourceType(),failure:req.failure()?.errorText||'unknown'}));
 const url=new URL(test.path||'/',root);
 if(url.origin!==root.origin)throw new Error('Cross-origin test navigation is not permitted');
 const response=await page.goto(url.href,{waitUntil:'commit',timeout:8500});
 report.httpStatus=response?.status()??null;
 if(report.httpStatus>=400)throw new Error('Navigation returned HTTP '+report.httpStatus);
 try{await page.waitForLoadState('domcontentloaded',{timeout:4500})}catch{report.errors.push('DOM content readiness timed out')}
 for(const step of steps){
   const start=Date.now(),selector=step.selector;
   if(step.action==='click')await page.locator(selector).click();
   else if(step.action==='fill')await page.locator(selector).fill(String(step.value??''));
   else if(step.action==='upload'){const f=path.resolve(path.dirname(manifestFile),step.file);await page.locator(selector).setInputFiles(f)}
   else if(step.action==='check')await page.locator(selector).check();
   else if(step.action==='press')await page.locator(selector).press(step.key||'Enter');
   else if(step.action==='expectVisible')await page.locator(selector).waitFor({state:'visible',timeout:5500});
   else if(step.action==='expectText'){const s=await page.locator(selector).innerText();if(!s.includes(String(step.text)))throw new Error('Expected text not found in '+selector)}
   else if(step.action==='expectValue'){const s=await page.locator(selector).inputValue();if(s!==String(step.value??''))throw new Error('Expected form value not found in '+selector)}
   else if(step.action==='expectUrl'){if(!page.url().includes(String(step.text)))throw new Error('Expected URL substring not found')}
   else if(step.action==='waitFor')await page.locator(selector).waitFor({state:step.state||'visible',timeout:5500});
   else if(step.action==='screenshot'){await page.screenshot({path:path.join(out,safeName+'-step-'+report.steps.length+'.png'),animations:'disabled',timeout:7500})}
   else throw new Error('Unknown action '+step.action);
   report.steps.push({action:step.action,selector:selector||null,status:'PASS',ms:Date.now()-start});
 }
 report.metrics=await page.evaluate(()=>{
  const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'};
  const overflow=[...document.querySelectorAll('body *')].filter(visible).filter(e=>e.getBoundingClientRect().right>innerWidth+2||e.getBoundingClientRect().left< -2).slice(0,30).map(e=>({tag:e.tagName,id:e.id||null,className:String(e.className||'').slice(0,75)}));
  const controls=[...document.querySelectorAll('button,input,a[href],textarea,select')].filter(visible);
  return {title:document.title,viewport:innerWidth,scrollWidth:document.documentElement.scrollWidth,overflow,unnamedControls:controls.filter(e=>!(e.getAttribute('aria-label')||e.innerText||e.getAttribute('placeholder')||e.labels?.length)).length,samples:[...document.querySelectorAll('body,main,header,button,input')].filter(visible).slice(0,15).map(e=>({tag:e.tagName,bg:getComputedStyle(e).backgroundColor,fg:getComputedStyle(e).color}))};
 });
 const screenshot=safeName+'.png';await page.screenshot({path:path.join(out,screenshot),fullPage:true,animations:'disabled',timeout:7500});
 report.screenshot=screenshot;report.status=(report.metrics.overflow.length||report.errors.length||report.consoleErrors.length||report.requestsFailed.length)?'FAIL':'PASS';
}catch(e){report.errors.push(String(e).slice(0,500));}
finally{
 await fs.writeFile(path.join(out,'result.json'),JSON.stringify(report,null,2));
 if(page)try{await Promise.race([page.close({runBeforeUnload:false}),new Promise(r=>setTimeout(r,1000))])}catch{}
 if(ctx)try{await Promise.race([ctx.close(),new Promise(r=>setTimeout(r,1000))])}catch{}
 if(browser)try{await Promise.race([browser.close(),new Promise(r=>setTimeout(r,1500))])}catch{}
}
console.log(JSON.stringify({name:report.name,status:report.status,errors:report.errors.length,steps:report.steps.length}));
process.exitCode=report.status==='PASS'?0:1;
