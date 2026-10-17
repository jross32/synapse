# Send a follow-up prompt into an existing ChatGPT worker chat (by conversation id) in the shared browser.
param([Parameter(Mandatory = $true)][string]$ChatId, [Parameter(Mandatory = $true)][string]$PromptFile, [string]$Config = (Join-Path $PSScriptRoot 'config.json'))
$cfg = Get-Content $Config -Raw | ConvertFrom-Json
$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot
$idJson = $ChatId | ConvertTo-Json -Compress
$baseJson = [string]$cfg.chatBaseUrl | ConvertTo-Json -Compress
$promptJson = [System.IO.File]::ReadAllText($PromptFile) | ConvertTo-Json -Compress
$js = @"
async (page) => {
  const id = $idJson;
  const prompt = $promptJson;
  const out = {};
  let p = page.context().pages().find(x => x.url().includes('/c/' + id));
  if (!p) { p = await page.context().newPage(); await p.goto($baseJson + '/c/' + id); }
  const box = p.locator('div.ProseMirror[contenteditable=true]');
  await box.waitFor({ timeout: 45000 });
  if (await p.locator('[data-testid="stop-button"], button[aria-label*="Stop" i]').count()) { out.error = 'worker still generating; not sent'; return out; }
  out.synapseAttached = await p.evaluate(() => { const c = document.querySelector('div.ProseMirror[contenteditable=true]'); const f = c && c.closest('form'); return f ? /Synapse/.test(f.innerText) : null; });
  if (out.synapseAttached === false) {
    await p.getByRole('button', { name: 'Add files and more' }).first().click();
    await p.waitForTimeout(900);
    const syn = p.getByText('Connect To Synapse', { exact: true }).first();
    if (!(await syn.count())) { out.error = 'Synapse connector unavailable'; return out; }
    await syn.click(); await p.waitForTimeout(900); out.reattached = true;
  }
  await box.click();
  await box.fill(prompt);
  await p.waitForTimeout(400);
  const send = p.locator('[data-testid="send-button"]');
  if (await send.count()) { await send.click(); } else { await p.keyboard.press('Enter'); }
  await p.waitForTimeout(3000);
  out.sent = true;
  out.generating = await p.locator('[data-testid="stop-button"], button[aria-label*="Stop" i]').count();
  return out;
}
"@
$tmp = Join-Path $dir 'last-followup.js'
[System.IO.File]::WriteAllText($tmp, $js)
& (Join-Path $dir 'pw.ps1') -CodeFile $tmp -Config $Config

