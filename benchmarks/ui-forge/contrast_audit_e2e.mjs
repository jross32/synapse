import { chromium } from "playwright";
import fs from "node:fs"; import path from "node:path";
const ROOT=path.resolve(import.meta.dirname,"../.."); const script=fs.readFileSync(path.join(ROOT,"templates/skills/ui-forge/scripts/contrast_audit.js"),"utf8");
const browser=await chromium.launch({headless:true}); const page=await browser.newPage({viewport:{width:900,height:700}});
await page.setContent('<main style="background:rgb(255,255,255);padding:20px"><p id="good" style="color:rgb(0,0,0);font-size:16px">Readable text</p><p id="bad" style="color:rgb(190,190,190);font-size:16px">Low contrast</p><p id="large" style="color:rgb(118,118,118);font-size:24px">Large text</p></main>');
const result=await page.evaluate(script); await browser.close();
const checks={detects_low_contrast:result.failures.some(x=>x.text==="Low contrast"),passes_black_text:result.rows.some(x=>x.text==="Readable text"&&x.pass),large_text_uses_three_to_one:result.rows.some(x=>x.text==="Large text"&&x.required===3),reports_ratios:result.rows.every(x=>typeof x.ratio==="number")};
const out={schema:"ui-forge-contrast-audit-e2e-v1",checks,passed:Object.values(checks).filter(Boolean).length,total:Object.keys(checks).length,overall_pass:Object.values(checks).every(Boolean),audit:result,claims:{browser_computed_contrast_math:true,not_a_full_accessibility_certification:true}};
console.log(JSON.stringify(out,null,2)); process.exit(out.overall_pass?0:1);
