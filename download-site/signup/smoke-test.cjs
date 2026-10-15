const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  for(const viewport of [{width:1440,height:900},{width:390,height:844},{width:320,height:700}]){
   const page=await browser.newPage({viewport});
   let posted=null;
   await page.route('https://accounts-api-production-f84a.up.railway.app/v1/auth/signup',async route=>{
    posted=route.request().postDataJSON();
    await route.fulfill({status:200,contentType:'application/json',body:'{"access_token":"TEST-DO-NOT-STORE","refresh_token":"TEST-DO-NOT-STORE"}',headers:{"access-control-allow-origin":"*"}});
   });
   const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto('http://127.0.0.1:8879/signup/',{waitUntil:'domcontentloaded'});
   await page.locator('[name=username]').fill('testuser');
   await page.locator('[name=email]').fill('test@example.com');
   await page.locator('[name=password]').fill('test-password-123');
   await page.locator('[name=confirm]').fill('wrong-password');
   await page.locator('#submit-signup').click();
   if(posted!==null)throw Error('Mismatched password submitted');
   await page.locator('[name=confirm]').fill('test-password-123');
   await page.locator('#submit-signup').click();
   await page.getByText('Account created.',{exact:false}).waitFor({timeout:5000});
   if(await page.locator('label').first().isVisible())throw Error('Fields remain visible');
   if(await page.locator('#submit-signup').isVisible())throw Error('Submit control remains visible');
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
   const stored=await page.evaluate(()=>JSON.stringify(localStorage)+JSON.stringify(sessionStorage));
   if(!posted||posted.username!=='testuser'||overflow||stored.includes('TEST-DO-NOT-STORE')||errors.length)throw Error(JSON.stringify({viewport,posted,overflow,errors}));
   console.log('signup mock passed',JSON.stringify(viewport));
   await page.close();
  }
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
