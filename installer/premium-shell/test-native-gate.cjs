const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage();
 await page.addInitScript(()=>{
  window.synapseInstaller={
   preflight:async()=>({platform:'win32',architecture:'x64',osRelease:'test',freeBytes:1024*1024*1024*50,meetsBasicPlatform:true}),
   
   install:async()=>({ok:false,exitCode:1})
  };
 });
 await page.goto('file:///C:/Users/justi/synapse/installer/premium-shell/index.html');
 await page.evaluate(()=>showScreen(3));
 await page.waitForTimeout(200);
 const state=await page.evaluate(()=>({installed:window.state?.installDone,percent:document.querySelector('#prog-pct')?.textContent,button:document.querySelector('#btn-next')?.disabled}));
 if(state.percent==='100%')throw Error('Native flow displayed false 100%');
 await page.evaluate(()=>document.querySelector('#btn-next').click()); const step=await page.evaluate(()=>state.current); if(step!==3)throw Error('Native flow allows skipping installation');
 console.log('PASS native installer never claims success without a payload',state);
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

