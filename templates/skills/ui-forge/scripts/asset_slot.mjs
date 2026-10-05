#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const parser = require('@babel/parser');
const traverseModule = require('@babel/traverse');
const t = require('@babel/types');
const traverse = traverseModule.default || traverseModule;

const SOURCE_RE = /^(.*):(\d+):(\d+)$/;
const MAX_BYTES = 25 * 1024 * 1024;
const PUBLIC_PREFIX = '/ui-forge-assets/';
const PUBLIC_DIR = 'public/ui-forge-assets';
const RECEIPT_DIR = '.synapse/ui-forge/assets';

function emit(payload, code = 0) { process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`); process.exitCode = code; }
function fail(message, details = {}, code = 2) { emit({ ok: false, error: message, ...details }, code); throw new Error('__UI_FORGE_EMITTED__'); }
function sha256(buffer) { return crypto.createHash('sha256').update(buffer).digest('hex'); }
function safeBase(name) {
  const parsed = path.parse(name);
  const stem = parsed.name.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'asset';
  return stem;
}
function detectRaster(buffer) {
  if (buffer.length >= 24 && buffer.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10]))) {
    return { type: 'png', ext: '.png', width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
  }
  if (buffer.length >= 3 && buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff) {
    let offset = 2;
    while (offset + 9 < buffer.length) {
      if (buffer[offset] !== 0xff) { offset += 1; continue; }
      const marker = buffer[offset + 1];
      if (marker === 0xd8 || marker === 0xd9) { offset += 2; continue; }
      const len = buffer.readUInt16BE(offset + 2);
      if (len < 2 || offset + 2 + len > buffer.length) break;
      if ([0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf].includes(marker) && len >= 7) {
        return { type: 'jpeg', ext: '.jpg', height: buffer.readUInt16BE(offset + 5), width: buffer.readUInt16BE(offset + 7) };
      }
      offset += 2 + len;
    }
    return { type: 'jpeg', ext: '.jpg', width: null, height: null };
  }
  if (buffer.length >= 16 && buffer.toString('ascii',0,4) === 'RIFF' && buffer.toString('ascii',8,12) === 'WEBP') {
    return { type: 'webp', ext: '.webp', width: null, height: null };
  }
  return null;
}
function readAsset(file) {
  const absolute = path.resolve(file);
  if (!fs.existsSync(absolute) || !fs.statSync(absolute).isFile()) fail('asset file does not exist', { asset_path: absolute });
  const size = fs.statSync(absolute).size;
  if (size <= 0 || size > MAX_BYTES) fail('asset size is outside the safe 1B..25MB range', { bytes: size });
  const buffer = fs.readFileSync(absolute);
  const image = detectRaster(buffer);
  if (!image) fail('asset is not a supported raster image (PNG/JPEG/WebP)');
  if (image.width != null && image.height != null && (image.width < 1 || image.height < 1 || image.width > 12000 || image.height > 12000)) fail('asset dimensions are outside the safe range', image);
  return { absolute, buffer, size, image, hash: sha256(buffer) };
}
function projectRoot(raw) {
  const root = path.resolve(raw);
  if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) fail('project root does not exist', { project_root: root });
  return root;
}
function writeJsonAtomic(file, payload) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = `${file}.tmp-${process.pid}-${Date.now()}`;
  fs.writeFileSync(temp, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
  fs.renameSync(temp, file);
}
function stage(root, assetPath) {
  const asset = readAsset(assetPath);
  const filename = `${asset.hash.slice(0, 16)}-${safeBase(asset.absolute)}${asset.image.ext}`;
  const rel = `${PUBLIC_DIR}/${filename}`.replace(/\\/g,'/');
  const target = path.join(root, ...rel.split('/'));
  const publicUrl = `${PUBLIC_PREFIX}${filename}`;
  fs.mkdirSync(path.dirname(target), { recursive: true });
  let createdNew = false;
  if (fs.existsSync(target)) {
    const existing = fs.readFileSync(target);
    if (sha256(existing) !== asset.hash) fail('existing project asset path has unexpected bytes; refusing overwrite', { target: rel });
  } else {
    const temp = `${target}.tmp-${process.pid}-${Date.now()}`;
    fs.writeFileSync(temp, asset.buffer);
    fs.renameSync(temp, target);
    createdNew = true;
  }
  const receipt = {
    schema: 'ui-forge-asset-stage-v1', staged_at: new Date().toISOString(), project_root: root,
    source_asset: asset.absolute, sha256: asset.hash, bytes: asset.size, media_type: asset.image.type,
    width: asset.image.width, height: asset.image.height, project_asset: rel, public_url: publicUrl, created_new: createdNew,
  };
  const receiptPath = path.join(root, RECEIPT_DIR, 'staged', `${asset.hash}.json`);
  writeJsonAtomic(receiptPath, receipt);
  return { ...receipt, receipt: path.relative(root, receiptPath).replace(/\\/g,'/') };
}
function parseSourcePointer(root, raw) {
  const match = SOURCE_RE.exec(String(raw || '').replace(/\\/g,'/'));
  if (!match) fail('source must be relative/file.jsx:line:column');
  const rel = match[1].replace(/^\/+/, '');
  const target = path.resolve(root, rel);
  const check = path.relative(root, target);
  if (check.startsWith('..') || path.isAbsolute(check)) fail('source pointer escapes project root');
  if (!fs.existsSync(target) || !fs.statSync(target).isFile()) fail('source file does not exist', { file: rel });
  return { rel: rel.replace(/\\/g,'/'), target, line: Number(match[2]), column: Number(match[3]) };
}
function parseJsx(source, filename) {
  const ext = path.extname(filename).toLowerCase();
  const plugins = ['jsx']; if (ext === '.ts' || ext === '.tsx') plugins.push('typescript');
  return parser.parse(source, { sourceType: 'unambiguous', sourceFilename: filename, plugins, errorRecovery: false });
}
function jsxName(node) { return t.isJSXIdentifier(node) ? node.name : ''; }
function attrName(attr) { return t.isJSXAttribute(attr) && t.isJSXIdentifier(attr.name) ? attr.name.name : ''; }
function findAttr(opening, name) { return opening.attributes.find(a => attrName(a) === name) || null; }
function staticAttr(attr) {
  if (!attr) return { ok:false, reason:'missing' };
  if (t.isStringLiteral(attr.value)) return { ok:true, value:attr.value.value, start:attr.value.start, end:attr.value.end };
  if (t.isJSXExpressionContainer(attr.value) && t.isStringLiteral(attr.value.expression)) return { ok:true, value:attr.value.expression.value, start:attr.value.start, end:attr.value.end };
  return { ok:false, reason:'dynamic' };
}
function quoted(v) { return JSON.stringify(String(v)); }
function attrPatch(opening, name, value) {
  const existing=findAttr(opening,name);
  if (existing) {
    const current=staticAttr(existing); if (!current.ok) fail(`refusing dynamic ${name} attribute`);
    return { start:current.start,end:current.end,replacement:quoted(value), before:current.value, after:String(value) };
  }
  const closeWidth=opening.selfClosing?2:1; const at=opening.end-closeWidth;
  return { start:at,end:at,replacement:` ${name}=${quoted(value)}`,before:null,after:String(value) };
}
function applyPatches(original, patches) {
  let out=original;
  for (const patch of [...patches].sort((a,b)=>b.start-a.start)) out=`${out.slice(0,patch.start)}${patch.replacement}${out.slice(patch.end)}`;
  return out;
}
function loadReceipt(root, request) {
  const rel = String(request.receipt || '');
  if (!rel) fail('commit request requires staged receipt');
  const receiptPath = path.resolve(root, rel);
  const check=path.relative(root,receiptPath); if (check.startsWith('..')||path.isAbsolute(check)) fail('receipt escapes project root');
  const receipt=JSON.parse(fs.readFileSync(receiptPath,'utf8'));
  if (receipt.schema!=='ui-forge-asset-stage-v1' || path.resolve(receipt.project_root)!==root) fail('invalid or wrong-project staged receipt');
  const assetPath=path.resolve(root,receipt.project_asset); const asset=readAsset(assetPath);
  if (asset.hash!==receipt.sha256) fail('staged asset integrity check failed');
  return { receipt, receiptPath, assetPath };
}
function commit(root, request, dryRun) {
  const { receipt, receiptPath }=loadReceipt(root,request);
  if (!String(receipt.public_url).startsWith(PUBLIC_PREFIX)) fail('receipt public URL is outside UI Forge asset namespace');
  const source=parseSourcePointer(root,request.source);
  const original=fs.readFileSync(source.target,'utf8');
  let ast; try { ast=parseJsx(original,source.rel); } catch(e){ fail('Babel parse failed',{detail:e.message}); }
  let match=null;
  traverse(ast,{ JSXElement(p){ if(match)return; const opening=p.node.openingElement; const loc=opening.loc?.start; if(!loc||loc.line!==source.line||loc.column+1!==source.column)return; const tag=jsxName(opening.name); if(tag!=='img') fail('asset slot source pointer must target intrinsic <img>',{tag:tag||'<unknown>'}); match=opening; p.stop(); }});
  if(!match) fail('no <img> matched exact source pointer; regenerate source tags before commit', { source: request.source }, 1);
  const srcCurrent=findAttr(match,'src'); const srcStatic=staticAttr(srcCurrent); if(!srcStatic.ok) fail('refusing asset commit: img src is missing or dynamic');
  const patches=[attrPatch(match,'src',receipt.public_url)];
  if(request.alt!=null) patches.push(attrPatch(match,'alt',String(request.alt)));
  const modified=applyPatches(original,patches); if(modified===original) fail('asset commit produced no source change',{},1);
  try{parseJsx(modified,source.rel);}catch(e){fail('edited JSX failed syntax reparse; nothing written',{detail:e.message},1);}
  if(!dryRun) {
    fs.writeFileSync(source.target,modified,'utf8');
    const committed={...receipt,schema:'ui-forge-asset-commit-v1',committed_at:new Date().toISOString(),source:request.source,previous_src:srcStatic.value,alt:request.alt??null};
    writeJsonAtomic(path.join(root,RECEIPT_DIR,'committed',`${receipt.sha256}.json`),committed);
    if(fs.existsSync(receiptPath)) fs.unlinkSync(receiptPath);
  }
  return { ok:true,schema:'ui-forge-asset-slot-v1',dry_run:dryRun,atomic:true,file:source.rel,source:request.source,asset:{sha256:receipt.sha256,bytes:receipt.bytes,width:receipt.width,height:receipt.height,public_url:receipt.public_url,project_asset:receipt.project_asset},changes:patches.map(p=>({before:p.before,after:p.after})),syntax_reparse_passed:true,verification_required:['rerender application','verify image decodes and natural dimensions are non-zero','verify alt text and surrounding layout','run desktop/mobile browser proof','check console/runtime errors'] };
}
function discard(root, receiptRel) {
  const request={receipt:receiptRel}; const {receipt,receiptPath,assetPath}=loadReceipt(root,request);
  const needles=[receipt.public_url,receipt.project_asset];
  const roots=['src','app','pages','components','index.html'];
  for(const entry of roots){const candidate=path.join(root,entry); if(!fs.existsSync(candidate))continue; const files=[]; const walk=(p)=>{const st=fs.statSync(p); if(st.isDirectory()){for(const n of fs.readdirSync(p))walk(path.join(p,n));}else if(st.isFile()&&st.size<2_000_000)files.push(p);}; walk(candidate); for(const file of files){let text=''; try{text=fs.readFileSync(file,'utf8');}catch{} if(needles.some(n=>text.includes(n))) fail('staged asset is referenced by project source; refusing discard',{file:path.relative(root,file)});}}
  if(receipt.created_new && fs.existsSync(assetPath)) fs.unlinkSync(assetPath);
  if(fs.existsSync(receiptPath)) fs.unlinkSync(receiptPath);
  return {ok:true,schema:'ui-forge-asset-discard-v1',discarded:true,asset_removed:Boolean(receipt.created_new),public_url:receipt.public_url};
}

async function main(){
  const args=process.argv.slice(2); const command=args[0];
  if(!['stage','commit','discard'].includes(command)){emit({ok:false,error:'usage: asset_slot.mjs stage <project-root> <asset-file> | commit <project-root> <request.json> [--dry-run] | discard <project-root> <receipt>'},2);return;}
  try{
    const root=projectRoot(args[1]);
    if(command==='stage') emit({ok:true,command,...stage(root,args[2])});
    else if(command==='commit'){const request=JSON.parse(fs.readFileSync(path.resolve(args[2]),'utf8')); emit(commit(root,request,args.includes('--dry-run')));}
    else emit(discard(root,args[2]));
  }catch(e){if(e.message!=='__UI_FORGE_EMITTED__')emit({ok:false,error:e.message},1);}
}
await main();
