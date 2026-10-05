#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import net from 'node:net';
import zlib from 'node:zlib';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { chromium } from 'playwright';

import uiForgeSourceTags from '../../templates/skills/ui-forge/scripts/babel_source_tags.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '../..');
const TOOL = path.join(REPO, 'templates/skills/ui-forge/scripts/asset_slot.mjs');
const PREVIEW = path.join(REPO, 'templates/skills/ui-forge/scripts/asset_preview_bridge.js');
const AUDIT = path.join(REPO, 'templates/skills/ui-forge/scripts/browser_audit.js');
const RESULTS = path.join(HERE, 'results');

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let i=0;i<8;i++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return (crc ^ 0xffffffff) >>> 0;
}
function pngChunk(type, data) {
  const t = Buffer.from(type, 'ascii');
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(Buffer.concat([t, data])));
  return Buffer.concat([len, t, data, crc]);
}
function png(width, height, rgb) {
  const signature = Buffer.from([137,80,78,71,13,10,26,10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width,0); ihdr.writeUInt32BE(height,4); ihdr[8]=8; ihdr[9]=2;
  const rows=[];
  const pixels=Buffer.alloc(width*3);
  for(let x=0;x<width;x++){ pixels[x*3]=rgb[0]; pixels[x*3+1]=rgb[1]; pixels[x*3+2]=rgb[2]; }
  for(let y=0;y<height;y++) rows.push(Buffer.concat([Buffer.from([0]), pixels]));
  return Buffer.concat([signature,pngChunk('IHDR',ihdr),pngChunk('IDAT',zlib.deflateSync(Buffer.concat(rows))),pngChunk('IEND',Buffer.alloc(0))]);
}
async function freePort(){return await new Promise((resolve,reject)=>{const s=net.createServer();s.unref();s.on('error',reject);s.listen(0,'127.0.0.1',()=>{const a=s.address();const p=typeof a==='object'&&a?a.port:0;s.close(e=>e?reject(e):resolve(p));});});}
function runTool(args, root) {
  const cp=spawnSync(process.execPath,[TOOL,...args],{cwd:REPO,encoding:'utf8',timeout:30_000});
  let payload; try{payload=JSON.parse(cp.stdout);}catch{payload={ok:false,stdout:cp.stdout,stderr:cp.stderr};}
  if(cp.status!==0) throw Object.assign(new Error(payload.error||'asset slot command failed'),{detail:payload});
  return payload;
}
function blocking(violations){const out=[];for(const key of ['horizontal_overflow','missing_interactive_name_count','unlabeled_form_control_count','missing_image_alt_count','heading_level_jump_count']){const v=violations?.[key];if(v===true||(typeof v==='number'&&v>0))out.push({key,value:v});}return out;}
async function main(){
  await fs.mkdir(RESULTS,{recursive:true});
  const root=await fs.mkdtemp(path.join(REPO,'.tmp-ui-forge-asset-e2e-'));
  let server,browser; const started=performance.now(); let stage='setup';
  try{
    stage='fixture';
    await fs.mkdir(path.join(root,'src'),{recursive:true}); await fs.mkdir(path.join(root,'public'),{recursive:true});
    await fs.writeFile(path.join(root,'public','old.png'),png(20,12,[50,90,180]));
    await fs.writeFile(path.join(root,'candidate.png'),png(42,24,[220,90,40]));
    await fs.writeFile(path.join(root,'index.html'),'<!doctype html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>Asset Slot E2E</title></head><body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>','utf8');
    await fs.writeFile(path.join(root,'src','main.jsx'),`import React from 'react';\nimport {createRoot} from 'react-dom/client';\nimport App from './App.jsx';\nimport './styles.css';\ncreateRoot(document.getElementById('root')).render(<App/>);\n`,'utf8');
    await fs.writeFile(path.join(root,'src','App.jsx'),`import React from 'react';\nexport default function App(){return <main className="shell"><h1>Asset slot</h1><img id="hero" className="hero" src="/old.png" alt="Old hero" /></main>}\n`,'utf8');
    await fs.writeFile(path.join(root,'src','styles.css'),`body{margin:0;font-family:system-ui}.shell{min-height:100vh;display:grid;place-content:center;gap:20px;padding:24px}.hero{display:block;border-radius:12px;max-width:100%;height:auto}h1{margin:0}\n`,'utf8');

    stage='stage-asset';
    const staged=runTool(['stage',root,path.join(root,'candidate.png')],root);
    if(!staged.ok||!staged.receipt) throw new Error('asset stage did not return receipt');

    stage='vite'; const port=await freePort();
    server=await createServer({root,logLevel:'silent',plugins:[react({babel:{plugins:[[uiForgeSourceTags,{root}]]}})],server:{host:'127.0.0.1',port,strictPort:true}});
    await server.listen(); const url=`http://127.0.0.1:${port}`;
    browser=await chromium.launch({headless:true,timeout:45_000}); const page=await browser.newPage({viewport:{width:900,height:700}});
    const consoleErrors=[],pageErrors=[]; page.on('console',m=>{if(m.type()==='error')consoleErrors.push({text:m.text(),location:m.location()});});page.on('pageerror',e=>pageErrors.push(e.message));
    await page.goto(url,{waitUntil:'domcontentloaded',timeout:20_000}); await page.locator('#hero').waitFor({state:'visible',timeout:10_000});
    const initial=await page.locator('#hero').evaluate(el=>({src:el.getAttribute('src'),alt:el.getAttribute('alt'),source:el.getAttribute('data-ui-forge-source'),id:el.getAttribute('data-ui-forge-id'),naturalWidth:el.naturalWidth,naturalHeight:el.naturalHeight}));
    if(initial.src!=='/old.png'||initial.naturalWidth!==20||initial.naturalHeight!==12||!initial.source||!initial.id) throw new Error('initial tagged image proof failed');

    stage='preview'; await page.addScriptTag({path:PREVIEW});
    const selected=await page.evaluate(()=>window.UIForgeAssetPreview.select('#hero'));
    if(!selected.ok) throw new Error('asset preview selection failed');
    const preview=await page.evaluate(async publicUrl=>await window.UIForgeAssetPreview.preview(publicUrl),staged.public_url);
    if(!preview.ok||preview.selection.natural_width!==42||preview.selection.natural_height!==24) throw new Error('staged asset did not decode in browser preview');
    const commitSpec=await page.evaluate(()=>window.UIForgeAssetPreview.commitSpec('Generated hero'));
    if(!commitSpec.ok||commitSpec.source!==initial.source) throw new Error('asset preview was not exact-source commit ready');
    const reverted=await page.evaluate(()=>window.UIForgeAssetPreview.revert());
    if(!reverted.reverted) throw new Error('asset preview did not revert');
    await page.waitForFunction(()=>{const el=document.querySelector('#hero');return el?.getAttribute('src')==='/old.png'&&el.naturalWidth===20&&el.naturalHeight===12;},null,{timeout:5000});

    stage='source-commit';
    const requestPath=path.join(root,'asset-request.json');
    await fs.writeFile(requestPath,`${JSON.stringify({source:commitSpec.source,receipt:staged.receipt,alt:commitSpec.alt},null,2)}\n`,'utf8');
    const dry=runTool(['commit',root,requestPath,'--dry-run'],root); if(!dry.ok||!dry.syntax_reparse_passed)throw new Error('asset dry-run failed');
    const committed=runTool(['commit',root,requestPath],root); if(!committed.ok)throw new Error('asset commit failed');

    stage='hmr';
    await page.waitForFunction(expected=>{const el=document.querySelector('#hero');return el?.getAttribute('src')===expected&&el.getAttribute('alt')==='Generated hero'&&el.naturalWidth===42&&el.naturalHeight===24;},staged.public_url,{timeout:10_000});
    const after=await page.locator('#hero').evaluate(el=>({src:el.getAttribute('src'),alt:el.getAttribute('alt'),source:el.getAttribute('data-ui-forge-source'),id:el.getAttribute('data-ui-forge-id'),naturalWidth:el.naturalWidth,naturalHeight:el.naturalHeight}));
    if(after.source!==initial.source||after.id!==initial.id)throw new Error('asset commit changed UI Forge source identity');

    stage='audit'; await page.addScriptTag({path:AUDIT}); const desktop=await page.evaluate(()=>window.UIForgeAudit.run()); await page.setViewportSize({width:390,height:844}); const mobile=await page.evaluate(()=>window.UIForgeAudit.run());
    if(blocking(desktop.violations).length||blocking(mobile.violations).length)throw Object.assign(new Error('objective browser audit failed'),{detail:{desktop:desktop.violations,mobile:mobile.violations}});
    if(consoleErrors.length||pageErrors.length)throw Object.assign(new Error('browser emitted runtime errors'),{detail:{consoleErrors,pageErrors}});
    const source=await fs.readFile(path.join(root,'src','App.jsx'),'utf8');
    if(!source.includes(staged.public_url)||!source.includes('alt="Generated hero"'))throw new Error('committed JSX does not contain staged asset and alt');
    const committedReceipt=path.join(root,'.synapse/ui-forge/assets/committed',`${staged.sha256}.json`); try{await fs.access(committedReceipt);}catch{throw new Error('committed provenance receipt missing');}

    const result={schema:'ui-forge-asset-slot-visual-e2e-v1',generated_at:new Date().toISOString(),overall_pass:true,duration_ms:Math.round((performance.now()-started)*1000)/1000,initial,stage_asset:{sha256:staged.sha256,bytes:staged.bytes,width:staged.width,height:staged.height,public_url:staged.public_url},preview:{decoded:true,natural_width:preview.selection.natural_width,natural_height:preview.selection.natural_height,reverted:true,source_commit_ready:true},source_commit:committed,committed:after,identity_stable:true,provenance_receipt:true,browser:{console_errors:consoleErrors,page_errors:pageErrors,desktop_violations:desktop.violations,mobile_violations:mobile.violations},claims:{generated_or_imported_raster_can_flow_preview_to_exact_source:true,asset_integrity_and_provenance_proven:true,not_a_provider_generation_quality_claim:true,not_a_full_ui_forge_or_lovable_claim:true}};
    await fs.writeFile(path.join(RESULTS,'asset-slot-visual-e2e-latest.json'),`${JSON.stringify(result,null,2)}\n`,'utf8'); console.log(JSON.stringify(result,null,2)); return 0;
  }catch(error){const result={schema:'ui-forge-asset-slot-visual-e2e-v1',generated_at:new Date().toISOString(),overall_pass:false,duration_ms:Math.round((performance.now()-started)*1000)/1000,stage,error:error.message,detail:error.detail||{}};await fs.writeFile(path.join(RESULTS,'asset-slot-visual-e2e-latest.json'),`${JSON.stringify(result,null,2)}\n`,'utf8');console.error(JSON.stringify(result,null,2));return 1;}
  finally{
    const bounded=async(promise,ms)=>await Promise.race([promise,new Promise(resolve=>setTimeout(()=>resolve('timeout'),ms))]);
    if(browser) await bounded(browser.close().catch(()=>{}),5000);
    if(server){
      await bounded(server.close().catch(()=>{}),5000);
      try{server.httpServer?.closeAllConnections?.();}catch{}
    }
    await bounded(fs.rm(root,{recursive:true,force:true}).catch(()=>{}),5000);
  }
}
const exitCode=await main();
process.exit(exitCode);
