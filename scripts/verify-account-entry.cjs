'use strict';
const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const {chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true});const results=[];const out=path.resolve(__dirname,'../.tmp/release-qa');fs.mkdirSync(out,{recursive:true});
try{for(const scenario of ['signin','signup','offline-signed-in']){let signed=scenario==='offline-signed-in',posts=[];const page=await browser.newPage({viewport:{width:1280,height:800},reducedMotion:'reduce'});const errors=[];page.on('pageerror',e=>errors.push(e.message));
const host={id:'qa-current',name:'QA current computer',current_host:true,last_seen_at:new Date().toISOString()};const profile=()=>({signed_in:signed,user_id:signed?'qa-account':null,username:'qauser',email:'qa@example.test',display_name:'QA',email_verified:false,sync_enabled:true,sync_status:scenario==='offline-signed-in'?'error':'synced',sync_backend:'synapse-account',account_backend_reachable:scenario!=='offline-signed-in',available_auth_providers:[],current_host:host,linked_identities:[],portable_connection_count:0,local_connection_count:0,last_sync_at:new Date().toISOString(),last_sync_error:scenario==='offline-signed-in'?'Network unavailable':null,preferences:{theme:'dark',sidebar_layout:null,discover_recent_keys:[]}});
await page.route('**/api/v1/**',async route=>{const request=route.request(),p=new URL(request.url()).pathname;let body={},status=200;
if(p.endsWith('/auth/local-token'))body={token:'qa-local-only'};
else if(p.endsWith('/profile/signin')||p.endsWith('/profile/signup')){const payload=request.postDataJSON();posts.push({path:p,payload});if(payload.password==='wrongpass'){status=403;body={code:'auth.invalid_credentials',message:'Invalid login or password',details:null,retryable:false};}else{signed=true;body=p.endsWith('/signup')?{profile:profile(),account:profile()}:profile();}}
else if(p.endsWith('/profile'))body=profile();
else if(p.endsWith('/profile/hosts'))body={hosts:[]};
else if(p.endsWith('/profile/preferences'))body=profile().preferences;
else if(p.endsWith('/health'))body={ok:true,version:'0.2.219',contracts:[]};
else if(p.endsWith('/projects'))body={projects:[]};
else if(p.endsWith('/tools'))body={tools:[]};
else if(p.includes('installed-pages'))body={pages:[]};
else if(p.includes('agent-squads'))body={squads:[]};
else if(p.includes('active-tasks'))body={tasks:[],summary:{enabled:0,running_or_dispatched:0}};
else if(p.includes('/review/'))body={items:[],count:0};
else body={};
await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});});
await page.goto(process.env.ACCOUNT_QA_URL||'http://127.0.0.1:5181');
if(!signed){await page.getByRole('heading',{name:'Welcome back'}).waitFor();assert.equal(await page.locator('.syn-dash').count(),0,'Dashboard hidden before account auth');
if(scenario==='signup'){await page.getByRole('button',{name:'Create account',exact:true}).first().click();await page.getByLabel('Username',{exact:true}).fill('qauser');await page.getByLabel('Display name (optional)').fill('QA User');await page.getByLabel('Email',{exact:true}).fill('qa@example.test');await page.getByLabel('Password',{exact:true}).fill('qa-password-123');await page.getByLabel('Confirm password').fill('qa-password-123');await page.locator('button[type=submit]').click();assert.equal(posts[0].payload.username,'qauser');}
else{await page.getByLabel('Email or username').fill('qa@example.test');await page.getByLabel('Password',{exact:true}).fill('wrongpass');await page.locator('button[type=submit]').click();await page.getByRole('alert').filter({hasText:'Invalid login'}).waitFor();assert.equal(await page.locator('.syn-dash').count(),0);await page.getByLabel('Password',{exact:true}).fill('qa-password-123');await page.locator('button[type=submit]').click();}
}
await page.locator('.syn-dash').waitFor({timeout:8000}).catch(async e=>{await page.screenshot({path:path.join(out,'account-failure.png')});console.error(JSON.stringify({scenario,signed,errors,posts:posts.map(p=>p.path),text:(await page.locator('body').innerText()).slice(0,1200)}));throw e;});assert(!errors.length,errors.join('\n'));await page.screenshot({path:path.join(out,'account-'+scenario+'.png')});results.push({scenario,passed:true,authRequests:posts.length});
if(scenario==='signup'){await page.setViewportSize({width:390,height:844});signed=false;await page.reload();await page.getByRole('heading',{name:'Welcome back'}).waitFor();assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile account entry horizontal overflow');await page.screenshot({path:path.join(out,'account-mobile.png')});}
await page.close();}
console.log(JSON.stringify({passed:true,scope:'Intercepted UI tests; no real account created or changed',results,output:out}));}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
