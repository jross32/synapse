# preflight.ps1 -- run this BEFORE you start a coding session on Synapse.
#
# Any AI coder (Claude, Codex, Copilot, ...) or human should run this first so the
# shared workflow never drifts again: it prints the next-free ADR + migration
# numbers to claim, the current uncommitted footprint (a big number = commit in
# smaller complete units), and the gate commands to run before committing.
#
#   pwsh -NoProfile -File scripts/preflight.ps1
#
# Repo convention (AGENTS.md): every commit bumps a version, appends CHANGELOG,
# updates PROGRESS.md, and any architectural change adds an ADR under docs/adr/.
# Claim numbers by re-checking the max HERE (not from memory) so two coders never
# collide.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Next-Number([string]$dir, [string]$pattern) {
  $max = 0
  Get-ChildItem -Path (Join-Path $root $dir) -Filter $pattern -File -ErrorAction SilentlyContinue |
    ForEach-Object {
      if ($_.Name -match '^(\d+)') { $n = [int]$Matches[1]; if ($n -gt $max) { $max = $n } }
    }
  return $max
}

$migMax = Next-Number 'daemon/synapse_daemon/migrations' '*.sql'
$adrMax = Next-Number 'docs/adr' '0*.md'

Write-Host ''
Write-Host '=== Synapse preflight ===' -ForegroundColor Cyan
Write-Host ("  Next free migration : {0:000}_your_slug.sql  (max on disk = {1:000})" -f ($migMax + 1), $migMax)
Write-Host ("  Next free ADR       : {0:0000}-your-slug.md   (max on disk = {1:0000})" -f ($adrMax + 1), $adrMax)
Write-Host '  (These count UNTRACKED files too -- claim the next number, never reuse.)'

Write-Host ''
Write-Host '=== Uncommitted footprint ===' -ForegroundColor Cyan
Push-Location $root
try {
  $stat = git diff --shortstat 2>$null
  $untracked = (git ls-files --others --exclude-standard 2>$null | Measure-Object).Count
  if ([string]::IsNullOrWhiteSpace($stat)) { $stat = 'no tracked changes' }
  Write-Host ("  Tracked   : {0}" -f $stat.Trim())
  Write-Host ("  Untracked : {0} file(s)" -f $untracked)
  if ($stat -match '(\d+) insertion') {
    if ([int]$Matches[1] -gt 800) {
      Write-Host '  ! Large uncommitted diff -- commit it as smaller COMPLETE units before adding more.' -ForegroundColor Yellow
    }
  }
} finally { Pop-Location }

Write-Host ''
Write-Host '=== Before you commit ===' -ForegroundColor Cyan
Write-Host '  1. npx tsc --noEmit -p tsconfig.json && npx tsc --noEmit -p electron/tsconfig.json'
Write-Host '  2. (cd daemon; python -m pytest -q)'
Write-Host '  3. Bump version + append CHANGELOG + update PROGRESS.md + ADR if architectural'
Write-Host '  4. Commit ONE complete piece at a time with a Co-Authored-By trailer'
Write-Host ''
