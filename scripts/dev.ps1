# Synapse — dev orchestration
# Starts the Python daemon and the Electron app together.
# Milestone A: prints a banner. Milestone B+: actually spawns both processes in parallel.

param(
  [switch]$DaemonOnly,
  [switch]$AppOnly
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

Write-Host "═══════════════════════════════════════════════════════"
Write-Host "  Synapse — by The WhatIf Company"
Write-Host "  Dev mode (Milestone A scaffolding)"
Write-Host "═══════════════════════════════════════════════════════"
Write-Host ""

if (-not $AppOnly) {
  Write-Host "→ Daemon will launch from: $root\daemon\synapse_daemon\"
  Write-Host "  (placeholder until Milestone B — runs 'python -m synapse_daemon' then exits)"
}

if (-not $DaemonOnly) {
  Write-Host "→ Renderer dev server will launch on http://localhost:5173"
  Write-Host "→ Electron will load that URL"
  Write-Host "  (real orchestration ships in Milestone C)"
}

Write-Host ""
Write-Host "For now, run manually:"
Write-Host "  Terminal 1:  python -m synapse_daemon"
Write-Host "  Terminal 2:  npm run build:electron && npx vite"
Write-Host "  Terminal 3:  npx electron ."
Write-Host ""
