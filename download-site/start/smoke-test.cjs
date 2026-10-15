const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    for (const viewport of [{width:1440,height:900},{width:390,height:844},{width:320,height:700}]) {
      const page = await browser.newPage({viewport});
      const errors=[]; page.on('pageerror',e=>errors.push(e.message));
      await page.goto('http://127.0.0.1:8879/start/',{waitUntil:'domcontentloaded'});
      const title=await page.locator('h1').innerText();
      const links=await page.locator('a[href*="github.com/jross32/synapse/releases"]').count();
      const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
      if (!title.includes('Get started')||links<3||overflow||errors.length) throw new Error(JSON.stringify({viewport,title,links,overflow,errors}));
      console.log(JSON.stringify({viewport,title,links,overflow,errors}));
      await page.close();
    }
  } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
