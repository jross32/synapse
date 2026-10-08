#!/usr/bin/env node
// Optional, read-only browser UI audit. Usage: node scripts/ui-audit.mjs https://example.com [output-dir]
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
const start = process.argv[2];
if (!start || !/^https?:\/\//.test(start)) { console.error('Usage: node scripts/ui-audit.mjs URL [output-dir]'); process.exit(2); }
const out = path.resolve(process.argv[3] || 'ui-audit-results');
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true});
const report={url:start,generated:new Date().toISOString(),pages:[],limitations:['Read-only navigation and DOM checks do not prove every button action or authenticated workflow.']};
const origin=new URL(start).origin;
try {
 for (const device of [{name:'desktop',width:1365,height:900},{name:'mobile',width:390,height:844}]) {
  const ctx=await browser.newContext({viewport:{width:device.width,height:device.height},isMobile:device.name==='mobile',hasTouch:device.name==='mobile'});
  const queue=[start],seen=new Set();
  while(queue.length && seen.size<20) {
   const url=queue.shift(); if(seen.has(url))continue;seen.add(url);
   const page=await ctx.newPage(),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   let status=null;
   try {const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:20000});status=response?.status()??null;await page.waitForTimeout(300);
    const data=await page.evaluate(()=>{
      const els=[...document.querySelectorAll('button,a[href],input,select,textarea,[role="button"]')];
      const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'};
      const controls=els.filter(visible).map(e=>({tag:e.tagName,text:(e.innerText||e.getAttribute('aria-label')||e.getAttribute('title')||'').trim().slice(0,90),disabled:e.disabled||false,hasName:!!(e.innerText?.trim()||e.getAttribute('aria-label')||e.getAttribute('title')||e.labels?.length),href:e.getAttribute('href')}));
      const theme=[...document.querySelectorAll('.rt-theme-switch')].map(e=>({parent:e.parentElement?.className||'',y:Math.round(e.getBoundingClientRect().top)}));
      const links=[...document.querySelectorAll('a[href]')].map(e=>e.href).filter(Boolean);
      return {title:document.title,width:innerWidth,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,controls,unnamed:controls.filter(e=>!e.hasName).length,theme,links};
    });
    await page.evaluate(()=>window.scrollTo(0,document.documentElement.scrollHeight));await page.waitForTimeout(120);
    const bottom=await page.evaluate(()=>({scrollY,footerVisible:!!document.querySelector('footer'),themeAtBody:[...document.querySelectorAll('body > .rt-theme-switch')].length}));
    await page.screenshot({path:path.join(out,device.name+'-'+seen.size+'.png'),fullPage:true});
    report.pages.push({device:device.name,url,status,errors,...data,bottom,overflow:data.scrollWidth>data.width+1});
    for(const link of data.links){try{const u=new URL(link);u.hash='';if(u.origin===origin&&!seen.has(u.href)&&!queue.includes(u.href))queue.push(u.href)}catch{}}
   }catch(e){report.pages.push({device:device.name,url,status,errors:[...errors,String(e)]});}
   finally{await page.close();}
  }
  await ctx.close();
 }
}finally{await browser.close();}
await fs.writeFile(path.join(out,'report.json'),JSON.stringify(report,null,2));
const failures=report.pages.filter(p=>p.errors?.length||p.overflow||p.status>=400||p.bottom?.themeAtBody);
console.log(JSON.stringify({pages:report.pages.length,failures:failures.length,report:path.join(out,'report.json'),issues:failures.map(p=>({device:p.device,url:p.url,status:p.status,errors:p.errors,overflow:p.overflow,themeAtBody:p.bottom?.themeAtBody}))},null,2));
process.exitCode=failures.length?1:0;
