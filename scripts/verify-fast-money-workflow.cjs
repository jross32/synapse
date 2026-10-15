const { chromium } = require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});const outcomes=[];
 for(const viewport of [JSON.parse(process.env.VIEWPORT)]){
 const page=await browser.newPage({viewport});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(process.env.DEMO_URL+'/signin');await page.locator('[data-local-role="customer"]').click();await page.waitForURL('**/portal');
 await page.locator('.approve-quote').first().click({timeout:8000});
 await page.waitForTimeout(300);
 const quote=await page.locator('#portal-quotes').innerText();
 if(!quote.includes('Approved'))throw new Error('quote approval not reflected: '+quote);
 await page.goto(process.env.DEMO_URL+'/signin');await page.locator('[data-local-role="operator"]').click();await page.waitForURL('**/ops');
 const job=page.locator('.schedule-job').first();const targetJobId=await job.getAttribute('data-job-id');await job.locator('input[name="owner"]').fill('Demo Operator');await job.locator('input[name="scheduled_for"]').fill('2026-11-01T10:00');await job.locator('button[type="submit"]').click();
 await page.locator('.complete-job[data-job-id='+JSON.stringify(targetJobId)+']').waitFor({timeout:5000});await page.locator('.complete-job[data-job-id='+JSON.stringify(targetJobId)+']').click();
 const beforeInvoice=await page.evaluate(async()=>await (await fetch('/api/workspace-state')).json());
 const draftInvoice=beforeInvoice.data?.invoices?.find(x=>x.job_id===targetJobId);
 if(!draftInvoice||draftInvoice.status!=='draft')throw new Error('target job did not create draft invoice');
 const sendInvoice=page.locator('.invoice-action[data-action=send][data-invoice-id='+JSON.stringify(draftInvoice.id)+']');
 await sendInvoice.waitFor({timeout:5000});await sendInvoice.click();
 await page.waitForTimeout(300);
 const state=await page.evaluate(async()=>{const r=await fetch('/api/workspace-state');return r.json()});
 const statuses={quotes:state.data?.quotes?.map(x=>x.status),jobs:state.data?.jobs?.map(x=>x.status),invoices:state.data?.invoices?.map(x=>x.status)};
 const completed=state.data?.jobs?.find(x=>x.id===targetJobId);if(!completed||completed.status!=='completed')throw new Error('target job not completed');const generated=state.data?.invoices?.find(x=>x.job_id===targetJobId);
 if(!generated||generated.status!=='sent')throw new Error('generated invoice not sent');
 const followups=await page.evaluate(async()=>{let r=await fetch('/api/follow-up/drafts');return {status:r.status,body:await r.json()}});
 if(followups.status!==200||followups.body.outbound_enabled!==false)throw new Error('follow-up review gate failed');
 if(!(await page.locator('#follow-up-drafts').innerText()).includes('approval-required'))throw new Error('drafts not displayed in operator dashboard');
 if(errors.length)throw new Error(errors.join(';'));
 outcomes.push({viewport,statuses,errors});await page.close();
 }
 await browser.close();console.log(JSON.stringify(outcomes));
})().catch(e=>{console.error(e.stack);process.exit(1)})
