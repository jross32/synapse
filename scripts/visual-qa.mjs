#!/usr/bin/env node
// Isolated, bounded UI visual audit. Zero changes to the target website.
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
const start=process.argv[2],out=path.resolve(process.argv[3]||'visual-qa-results');
if(!start||!/^https?:\/\//.test(start)){console.error('Usage: node scripts/visual-qa.mjs URL [output-dir]');process.exit(2);}
await fs.mkdir(out,{recursive:true});
const sizes=[{name:'desktop',width:1365,height:900},{name:'mobile',width:390,height:844},{name:'small-mobile',width:320,height:740}];
const report={url:start,generated:new Date().toISOString(),pages:[],limitations:['Interaction tests need a disposable authenticated test account and explicit scenarios. This read-only audit does not submit or mutate.', 'Reference screenshots require approved image files; this audit captures fresh images without claiming visual equivalence.']};
for(const device of sizes){
  let browser,context,page;
  const entry={device:device.name,url:start,status:null,errors:[],consoleErrors:[],overflow:[],contrast:[],screenshots:[]};
  try {
    // New browser per device: no long-lived browser session that can poison later tests.
    browser=await chromium.launch({headless:true,executablePath:process.env.SYNAPSE_CHROME_PATH||undefined,timeout:12000});
    context=await browser.newContext({viewport:{width:device.width,height:device.height},isMobile:device.name!=='desktop',hasTouch:device.name!=='desktop'});
    page=await context.newPage();page.setDefaultTimeout(6500);
    page.on('pageerror',e=>entry.errors.push('JS: '+e.message));
    page.on('console',m=>{if(m.type()==='error')entry.consoleErrors.push(m.text().slice(0,300));});
    const response=await page.goto(start,{waitUntil:'commit',timeout:9000});
    entry.status=response?.status()??null;
    try{await page.waitForLoadState('domcontentloaded',{timeout:4500});}catch(e){entry.errors.push('DOM readiness timeout: '+e.message.slice(0,140));}
    try{await page.waitForTimeout(250);}catch{}
    const data=await page.evaluate(()=>{
      const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};
      const backgrounds=[document.documentElement,document.body,document.querySelector('#app'),document.querySelector('main')].filter(Boolean).map(e=>({element:e.id||e.tagName,background:getComputedStyle(e).backgroundColor,foreground:getComputedStyle(e).color}));
      const overflow=[...document.querySelectorAll('body *')].filter(visible).map(e=>({e,r:e.getBoundingClientRect()})).filter(x=>x.r.left < -2 || x.r.right>innerWidth+2).slice(0,30).map(x=>({tag:x.e.tagName,selector:x.e.id?'#'+x.e.id:(x.e.className?.baseVal||x.e.className||'').toString().slice(0,80),left:Math.round(x.r.left),right:Math.round(x.r.right)}));
      const parse=c=>{const m=c.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);return m?[+m[1],+m[2],+m[3]]:null};
      const luminance=rgb=>{const a=rgb.map(v=>{v/=255;return v<=0.04045?v/12.92:((v+0.055)/1.055)**2.4});return a[0]*.2126+a[1]*.7152+a[2]*.0722};
      const contrast=[];
      for(const e of [...document.querySelectorAll('h1,h2,h3,p,label,button,a,small,span')].filter(visible).slice(0,220)){
        const s=getComputedStyle(e);let bg=e;let bgColor=null;
        while(bg){let v=getComputedStyle(bg).backgroundColor;if(v!=='rgba(0, 0, 0, 0)'&&v!=='transparent'){bgColor=v;break;}bg=bg.parentElement;}
        const f=parse(s.color),b=parse(bgColor||'rgb(255,255,255)');
        if(!f||!b||!e.textContent?.trim())continue;
        const v1=luminance(f),v2=luminance(b),ratio=(Math.max(v1,v2)+.05)/(Math.min(v1,v2)+.05);
        if(ratio<4.5&&Number.parseFloat(s.fontSize)<24)contrast.push({tag:e.tagName,text:e.textContent.trim().slice(0,50),fg:s.color,bg:bgColor,ratio:+ratio.toFixed(2)});
      }
      const controls=[...document.querySelectorAll('button,a[href],input,textarea,select')].filter(visible).map(e=>({tag:e.tagName,text:(e.getAttribute('aria-label')||e.innerText||e.getAttribute('placeholder')||'').trim().slice(0,70),disabled:!!e.disabled}));return{title:document.title,width:innerWidth,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,backgrounds,overflow,contrast:contrast.slice(0,35),controls,unnamedControls:controls.filter(e=>!e.text).length};
    });
    Object.assign(entry,data);entry.horizontalOverflow=data.scrollWidth>data.width+1;
    const shot=device.name+'.png';await page.screenshot({path:path.join(out,shot),fullPage:true,timeout:8500,animations:'disabled'});entry.screenshots.push(shot);
  }catch(e){entry.errors.push(String(e).slice(0,550));}
  finally{
    if(page)try{await Promise.race([page.close({runBeforeUnload:false}),new Promise(resolve=>setTimeout(resolve,1200))]);}catch{}
    if(context)try{await Promise.race([context.close(),new Promise(resolve=>setTimeout(resolve,1200))]);}catch{}
    if(browser)try{await Promise.race([browser.close(),new Promise(resolve=>setTimeout(resolve,1800))]);}catch{}
    report.pages.push(entry);
    console.log(device.name+': '+(entry.errors.length?'errors='+entry.errors.length:'captured')+', overflow='+(entry.overflow?.length||0)+', contrast candidates='+(entry.contrast?.length||0));
  }
}
const failures=report.pages.filter(x=>x.errors.length||x.status>=400||x.horizontalOverflow||x.overflow?.length);
report.failureCount=failures.length;await fs.writeFile(path.join(out,'report.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify({report:path.join(out,'report.json'),devices:report.pages.length,failures:failures.length},null,2));
process.exitCode=failures.length?1:0;
