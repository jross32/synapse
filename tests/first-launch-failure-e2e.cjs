const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
const browser=await chromium.launch({headless:true});
try{
const page=await browser.newPage({viewport:{width:1280,height:800}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.route('**/health',route=>route.abort('failed'));
await page.goto('http://127.0.0.1:5198/qa-first-launch.html');
await page.getByRole('button',{name:/Get started/i}).first().click();
await page.getByRole('button',{name:/Continue locally without an account/i}).click();
await page.getByRole('heading',{name:'This computer'}).waitFor();
await page.getByText('Local daemon not reachable').waitFor({timeout:10000});
await page.getByRole('button',{name:/Retry checks/i}).click();
await page.getByText('Local daemon not reachable').waitFor({timeout:10000});
await page.reload();
await page.getByRole('heading',{name:'This computer'}).waitFor();
const saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('synapse:first-launch:v1')));
assert.equal(saved.step,'computer');assert.equal(saved.mode,'guest');assert.deepEqual(errors,[]);
console.log(JSON.stringify({passed:true,offline:true,step:saved.step,errors}));
}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
