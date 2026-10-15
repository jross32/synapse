const { chromium } = require('playwright');
(async()=>{
 const base=process.env.DEMO_URL;
 const browser=await chromium.launch({headless:true});
 const results=[];
 for (const viewport of [{width:1366,height:850},{width:390,height:844}]) {
  const page=await browser.newPage({viewport});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/signin',{waitUntil:'networkidle'});
  await page.locator('[data-local-role="customer"]').click();
  await page.waitForURL('**/portal');
  const customer=await page.locator('body').innerText();
  if(!customer.includes('Customer portal')) throw new Error('customer portal content absent');
  await page.goto(base+'/signin');
  await page.locator('[data-local-role="operator"]').click();
  await page.waitForURL('**/ops');
  const operator=await page.locator('body').innerText();
  if(!operator.includes('Operator console')) throw new Error('operator console content absent');
  const api=await page.evaluate(async()=>{let r=await fetch('/api/sales/offers');return {status:r.status,body:await r.json()}});
  if(api.status!==200||api.body.offers[0].draft_only!==true)throw new Error('offers API failed');
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+2);
  results.push({viewport,customer:true,operator:true,offer:true,horizontal_overflow:overflow,errors});
  await page.close();
 }
 await browser.close();console.log(JSON.stringify(results));
 if(results.some(x=>x.errors.length||x.horizontal_overflow))process.exitCode=2;
})().catch(e=>{console.error(e.stack);process.exit(1)});
