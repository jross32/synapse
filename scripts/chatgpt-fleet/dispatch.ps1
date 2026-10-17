# Start one ChatGPT UI worker in the shared Playwright browser: new owned tab in the
# Synapse2GPT Workers project, attach the Synapse plugin, send the prompt, return the chat URL.
# Usage: dispatch.ps1 -PromptFile prompts\x.txt [-ReuseCurrentTab]
param([Parameter(Mandatory = $true)][string]$PromptFile, [switch]$ReuseCurrentTab, [string]$Config = (Join-Path $PSScriptRoot 'config.json'))
$cfg = Get-Content $Config -Raw | ConvertFrom-Json
$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot
$prompt = [System.IO.File]::ReadAllText($PromptFile)
$promptJson = $prompt | ConvertTo-Json -Compress
$projectJson = [string]$cfg.projectUrl | ConvertTo-Json -Compress
$reuse = if ($ReuseCurrentTab) { 'true' } else { 'false' }
$js = @"
async (page) => {
  const PROJECT = $projectJson;
  const prompt = $promptJson;
  const out = {};
  const p = $reuse ? page : await page.context().newPage();
  await p.keyboard.press('Escape').catch(() => {});
  await p.goto(PROJECT);
  await p.waitForSelector('div.ProseMirror[contenteditable=true]', { timeout: 45000 });
  await p.getByRole('button', { name: 'Add files and more' }).first().click();
  await p.waitForTimeout(900);
  const syn = p.getByText('Connect To Synapse', { exact: true }).first();
  if (!(await syn.count())) { out.error = 'Synapse plugin not in + menu'; return out; }
  await syn.click();
  await p.waitForTimeout(900);
  out.synapseAttached = await p.evaluate(() => { const c = document.querySelector('div.ProseMirror[contenteditable=true]'); const f = c && c.closest('form'); return f ? /Synapse/.test(f.innerText) : null; });
  if (out.synapseAttached === false) { out.error = 'Synapse chip not visible after selecting plugin; prompt NOT sent'; return out; }
  const box = p.locator('div.ProseMirror[contenteditable=true]');
  await box.click();
  await box.fill(prompt);
  await p.waitForTimeout(400);
  const send = p.locator('[data-testid="send-button"]');
  if (await send.count()) { await send.click(); } else { await p.keyboard.press('Enter'); }
  for (let i = 0; i < 80 && !/\/c\//.test(p.url()); i++) await p.waitForTimeout(500);
  out.url = p.url();
  out.title = await p.title();
  out.generating = await p.locator('[data-testid="stop-button"]').count();
  return out;
}
"@
$tmp = Join-Path $dir 'last-dispatch.js'
[System.IO.File]::WriteAllText($tmp, $js)
& (Join-Path $dir 'pw.ps1') -CodeFile $tmp -Config $Config
