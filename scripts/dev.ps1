# Synapse -- dev orchestration
#
# Starts the Python daemon, Vite (renderer), and Electron together.
#
# Behaviour:
#   - daemon  -> runs in the foreground console window so you see boot output.
#                Stops when this script is interrupted (Ctrl+C).
#   - Vite + Electron -> launched as background jobs; cleaned up on exit.
#
# Flags:
#   -DaemonOnly   Only start the daemon. Useful for backend work.
#   -AppOnly      Only start Vite + Electron (assumes daemon is already up).
#   -BindLan      Bind the daemon on 0.0.0.0:7878 instead of loopback so
#                 the mobile UI on your phone can reach it.
#
# NOTE: This file is intentionally pure ASCII. Windows PowerShell 5.1 reads
# .ps1 files as Windows-1252 unless they start with a UTF-8 BOM, and the Write
# tool the assistant uses does not emit a BOM. Keep arrows and box-drawing
# characters as ASCII (-> not the unicode arrow, === not the unicode bar).

param(
  [switch]$DaemonOnly,
  [switch]$AppOnly,
  [switch]$BindLan
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "======================================================="
Write-Host "  Synapse -- by The WhatIf Company"
Write-Host "  Dev mode"
Write-Host "======================================================="
Write-Host ""

$jobs = @()

function Stop-Jobs {
  foreach ($j in $script:jobs) {
    if ($j -and $j.State -eq 'Running') {
      Stop-Job -Job $j -ErrorAction SilentlyContinue
      Remove-Job -Job $j -Force -ErrorAction SilentlyContinue
    }
  }
}

trap {
  Write-Host ""
  Write-Host "-> Shutting down dev jobs..."
  Stop-Jobs
  break
}

if (-not $AppOnly) {
  # Run daemon in the foreground if it's the only thing we're starting,
  # otherwise as a background job whose stdout streams to the console.
  $daemonArgs = @('-m', 'synapse_daemon', '--port', '7878', '--data-dir', 'data')
  if ($BindLan) { $daemonArgs += '--bind-lan' }

  if ($DaemonOnly) {
    Write-Host "-> Starting daemon (foreground): python $($daemonArgs -join ' ')"
    Write-Host ""
    & python @daemonArgs
    exit $LASTEXITCODE
  }

  Write-Host "-> Starting daemon: python $($daemonArgs -join ' ')"
  $daemonJob = Start-Job -Name 'synapse-daemon' -ScriptBlock {
    param($cwd, $args_)
    Set-Location $cwd
    & python @args_
  } -ArgumentList $root, $daemonArgs
  $jobs += $daemonJob

  # Briefly poll /api/v1/health so we don't race Vite past the daemon.
  $ready = $false
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 250
    try {
      $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 -Uri 'http://127.0.0.1:7878/api/v1/health'
      if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
  }
  if ($ready) {
    Write-Host "  Daemon ready on http://127.0.0.1:7878"
  } else {
    Write-Warning "  Daemon did not respond to /api/v1/health within 10s -- see logs above"
  }
}

if (-not $DaemonOnly) {
  Write-Host "-> Starting Vite dev server on http://127.0.0.1:5173"
  $viteJob = Start-Job -Name 'synapse-vite' -ScriptBlock {
    param($cwd)
    Set-Location $cwd
    & npx vite
  } -ArgumentList $root
  $jobs += $viteJob

  Write-Host "-> Compiling Electron main -> dist-electron/"
  & npm run build:electron
  if ($LASTEXITCODE -ne 0) {
    Write-Error "build:electron failed"
    Stop-Jobs
    exit 1
  }

  Write-Host "-> Launching Electron"
  & npx electron .
  Write-Host "-> Electron exited; stopping background jobs"
}

Stop-Jobs
