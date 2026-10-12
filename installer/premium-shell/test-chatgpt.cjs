const { chromium } = require('playwright');
(async () => {
 const browser = await chromium.launch({headless:true});
 const page = await browser.newPage({ viewport:{width:1100,height:760} });
 await page.goto('file:///C:/Users/justi/synapse/installer/premium-shell/preview-chatgpt.html');
 const names=[];
 for(let i=0;i<8;i++){
  const active=page.locator('.screen.active');
  if(await active.count()!==1)throw Error('bad active count '+i);
  names.push(await active.getAttribute('data-title'));
  if(i<7)await page.locator('#next').click();
 }
 if(names.length!==8)throw Error('screens missing');
 await page.locator('#back').click();
 if(await page.locator('.screen.active').getAttribute('data-title')!=='What\'s New') throw Error('back failed');
 console.log('PASS 8 screens:',names.join(', '));
 await browser.close();
})().catch(err=>{console.error(err);process.exit(1)});