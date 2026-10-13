const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async () => {
 const browser = await chromium.launch({headless:true});
 try {
 const page = await browser.newPage({viewport:{width:1280,height:800}});
 const errors=[]; page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:5198/qa-first-launch.html',{waitUntil:'domcontentloaded'});
 await page.getByRole('button',{name:/Get started/i}).first().click();
 assert.equal(await page.getByRole('button',{name:'Continue',exact:true}).isDisabled(),true);
 await page.getByRole('button',{name:/Continue locally without an account/i}).click();
 await page.getByRole('heading',{name:'This computer'}).waitFor();
 await page.getByRole('button',{name:'Continue',exact:true}).click();
 await page.getByRole('heading',{name:'AI and MCP connections'}).waitFor();
 await page.getByRole('button',{name:'Continue',exact:true}).click();
 await page.getByRole('heading',{name:'Choose your companion'}).waitFor();
 await page.getByRole('button',{name:/Ninja/i}).click();
 await page.getByRole('button',{name:'Continue',exact:true}).click();
 await page.getByRole('heading',{name:'Ready to launch'}).waitFor();
 await page.getByRole('button',{name:/Open Synapse/i}).click();
 const saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('synapse:first-launch:v1')));
 assert.equal(saved.completed,true);assert.equal(saved.mode,'guest');assert.equal(saved.companion,'ninja');
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:true,mode:saved.mode,companion:saved.companion,errors}));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
