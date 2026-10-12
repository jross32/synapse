const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const OUT = path.resolve(__dirname, '../artifacts/usage-costs');
fs.mkdirSync(OUT, {recursive:true});
(async () => {
  const browser = await chromium.launch({headless:true});
  const result = {desktop:{},mobile:{},errors:[]};
  for (const [label,width,height] of [['desktop',1536,1024],['mobile',390,844]]) {
    const page = await browser.newPage({viewport:{width,height},deviceScaleFactor:1});
    page.on('pageerror', err => result.errors.push(label+': '+err.message));
    page.route('**/api/v1/ai/usage-images', r=>r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({items:[]})}));
    page.route('**/api/v1/ai/usage-alerts', r=>r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({items:[]})}));
    await page.goto('http://127.0.0.1:5173/', {waitUntil:'domcontentloaded',timeout:30000});
    await page.waitForTimeout(1700);
    if(label==='mobile') {
      const btn=page.getByRole('button',{name:/Show tabs|AI Coding|Home/i}).first();
      if(await btn.count()) await btn.click().catch(()=>{});
      await page.evaluate(()=>window.dispatchEvent(new CustomEvent('synapse:navigate',{detail:{page:'usage-costs'}})));
    } else {
      await page.getByRole('button',{name:/Usage & Costs/i}).first().click({timeout:15000});
    }
    await page.getByRole('heading',{name:'AI Usage & Costs'}).waitFor({timeout:20000});
    await page.waitForTimeout(900);
    const activity=page.getByRole('button',{name:/Recent Activity/});
    result[label].initialCollapsed = await activity.getAttribute('aria-expanded') === 'false';
    await page.screenshot({path:path.join(OUT,label+'-collapsed.png'),fullPage:true});
    await activity.click();
    result[label].expanded = await activity.getAttribute('aria-expanded') === 'true';
    result[label].activityRows = await page.locator('#usage-recent-activity tbody tr').count();
    await page.screenshot({path:path.join(OUT,label+'-expanded.png'),fullPage:true});
    result[label].horizontalOverflow = await page.evaluate(()=>document.documentElement.scrollWidth > window.innerWidth);
    result[label].cards = await page.locator('.usage-metrics .usage-panel').count();
    result[label].chart = await page.locator('.usage-chart svg').count();
    await page.close();
  }
  await browser.close();
  result.passed = ['desktop','mobile'].every(k=>result[k].initialCollapsed && result[k].expanded && !result[k].horizontalOverflow && result[k].cards===4 && result[k].chart===1) && !result.errors.length;
  console.log(JSON.stringify(result,null,2));
  if(!result.passed) process.exitCode=2;
})().catch(e=>{console.error(e.stack);process.exitCode=1});
