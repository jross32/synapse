const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const BASE='http://127.0.0.1:5173/qa-sync.html';
const now=()=>new Date().toISOString();
const host=(id,name,current=false)=>({id,name,platform:'win32',current_host:current,last_seen_at:now(),created_at:now(),updated_at:now()});
async function scenario(browser,name,mode,viewport){
 const page=await browser.newPage({viewport});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let patchCount=0;let savedAt=null;
 await page.route('**/api/v1/profile/hosts',r=>r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({hosts:[host('qa-desktop','This computer',true),host('qa-laptop','QA Laptop')]})}));
 await page.route('**/api/v1/profile',async r=>{
  const method=r.request().method();
  if(method==='PATCH'){patchCount++;savedAt=mode==='fresh'?now():new Date(Date.now()-3600000).toISOString();return r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({sync_enabled:true,last_sync_at:savedAt,account_backend_reachable:true,last_sync_error:null})});}
  return r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({sync_enabled:true,last_sync_at:savedAt,account_backend_reachable:true,last_sync_error:null})});
 });
 await page.goto(BASE,{waitUntil:'domcontentloaded'});
 const dialog=page.getByRole('dialog');await dialog.waitFor({timeout:10000}).catch(async e=>{console.log('DEBUG',await page.title(),await page.locator('body').innerText(),errors);throw e});
 assert.equal(await dialog.getByText('QA Laptop').count(),1);
 assert.equal(await page.locator('.syn-sync-neural-mark').count(),1);
 if(mode==='dismiss'){await dialog.getByRole('button',{name:'Not now'}).click();assert.equal(await dialog.count(),0);await page.reload();assert.equal(await dialog.count(),0);}
 else{
  await dialog.getByRole('button',{name:'Enable sync'}).click();
  if(mode==='fresh'){await dialog.getByText('Account settings synchronized',{exact:true}).first().waitFor();await dialog.getByText('100%',{exact:true}).waitFor({timeout:5000});}
  else{await dialog.getByText('Account sync needs attention').waitFor();assert.equal(await dialog.getByText('100%',{exact:true}).count(),0);}
  assert.equal(patchCount,1);
 }
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
 assert.equal(overflow,false);
 assert.deepEqual(errors,[]);
 await page.screenshot({path:'sync-onboarding-'+name+'.png'});
 await page.close();
 return {name,passed:true,overflow,errors};
}
(async()=>{const b=await chromium.launch({headless:true});try{
 const results=[];
 results.push(await scenario(b,'desktop-success','fresh',{width:1366,height:900}));
 results.push(await scenario(b,'desktop-stale','stale',{width:1366,height:900}));
 results.push(await scenario(b,'mobile-success','fresh',{width:390,height:844}));
 results.push(await scenario(b,'dismiss','dismiss',{width:1366,height:900}));
 console.log(JSON.stringify({passed:true,results},null,2));
}finally{await b.close()}})().catch(e=>{console.error(e.stack);process.exit(1)});
