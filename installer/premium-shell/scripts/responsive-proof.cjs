'use strict';
const {chromium}=require('playwright');
const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const root=path.resolve(__dirname,'..');
 const sizes=[[1060,720],[780,580],[660,580],[1060,500]];
 const results=[];
 try {
 for(const [width,height] of sizes){
  const page=await browser.newPage({viewport:{width,height},reducedMotion:'reduce'});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('file:///'+path.join(root,'index.html').replace(/\\/g,'/'));
  await page.waitForTimeout(100);
  const computed=await page.evaluate(()=>{
   const root=document.querySelector('#installer-root');const stylesheet=[...document.styleSheets].some(s=>s.href?.includes('premium-polish.css'));
   return {stylesheet,width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight,availableHeight:root?.getBoundingClientRect().height,step:document.querySelector('#foot-cur')?.textContent};
  });
  if(!computed.stylesheet)throw Error('Premium polish stylesheet not loaded');
  if(computed.width>width+2)throw Error('Horizontal overflow at '+width+'x'+height+': '+computed.width);
  if(computed.height>height+2)throw Error('Vertical overflow at '+width+'x'+height+': '+computed.height);
  if(errors.length)throw Error('Browser errors: '+errors.join('; '));
  results.push({viewport:width+'x'+height, ...computed});
  await page.close();
 }
 console.log('PASS responsive premium shell',JSON.stringify(results));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
