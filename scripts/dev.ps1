# Synapse -- dev orchestration
#
# Starts the Python daemon, Vite, and Electron together with PID ownership,
# log tails, and a full restart loop when the app asks for one.
#
# NOTE: This file is intentionally pure ASCII. Windows PowerShell 5.1 reads
# .ps1 files as Windows-1252 unless they start with a UTF-8 BOM, and the tool
# used for edits here does not emit a BOM.

param(
  [switch]$DaemonOnly,
  [switch]$AppOnly,
  [switch]$BindLan,
  [switch]$ShortcutMode,
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$ElectronArgs
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$dataDir = Join-Path $root 'data'
$daemonLog = Join-Path $dataDir 'daemon-runtime.log'
$viteLog = Join-Path $dataDir 'vite-runtime.log'
$restartExitCode = 75

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

Write-Host "======================================================="
Write-Host "  Synapse -- by The WhatIf Company"
Write-Host "  Dev mode"
Write-Host "======================================================="
Write-Host ""

function Get-LogTail {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [int]$Lines = 40
  )

  if (-not (Test-Path $Path)) {
    return '(no log output yet)'
  }
  $content = Get-Content -Path $Path -Tail $Lines -ErrorAction SilentlyContinue
  if (-not $content) {
    return '(log file is empty)'
  }
  return ($content -join [Environment]::NewLine)
}

function Stop-ProcessTree {
  param(
    [System.Diagnostics.Process]$Process,
    [string]$Label
  )

  if (-not $Process) {
    return
  }
  try {
    if ($Process.HasExited) {
      return
    }
  } catch {
    return
  }

  Write-Host "-> Stopping $Label (PID $($Process.Id))"
  & taskkill /PID $Process.Id /T /F | Out-Null
  Start-Sleep -Milliseconds 250
}

function Start-LoggedCmdProcess {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Label,
    [Parameter(Mandatory = $true)]
    [string]$Command,
    [Parameter(Mandatory = $true)]
    [string]$LogPath
  )

  if (Test-Path $LogPath) {
    Remove-Item -Path $LogPath -Force -ErrorAction SilentlyContinue
  }

  $wrapped = "$Command >> `"$LogPath`" 2>&1"
  Write-Host "-> Starting $Label"
  $proc = Start-Process `
    -FilePath 'cmd.exe' `
    -ArgumentList @('/d', '/c', $wrapped) `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -PassThru
  Write-Host "   PID $($proc.Id) | log: $LogPath"
  return $proc
}

function Wait-HttpReady {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Label,
    [Parameter(Mandatory = $true)]
    [string[]]$Urls,
    [Parameter(Mandatory = $true)]
    [int]$TimeoutSeconds,
    [System.Diagnostics.Process]$Process,
    [Parameter(Mandatory = $true)]
    [string]$LogPath,
    [string]$ReadyPattern
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    if ($Process) {
      try {
        $Process.Refresh()
        if ($Process.HasExited) {
          $tail = Get-LogTail -Path $LogPath
          throw "$Label exited early with code $($Process.ExitCode).`n$tail"
        }
      } catch [System.Management.Automation.RuntimeException] {
        throw
      } catch {
      }
    }

    $patternReady = $true
    if ($ReadyPattern) {
      $patternReady = Test-Path $LogPath
      if ($patternReady) {
        $patternReady = Select-String -Path $LogPath -Pattern $ReadyPattern -Quiet -ErrorAction SilentlyContinue
      }
    }

    foreach ($url in $Urls) {
      try {
        $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 -Uri $url
        if ($response.StatusCode -eq 200 -and $patternReady) {
          Write-Host "   $Label ready at $url"
          return
        }
      } catch {
      }
    }

    Start-Sleep -Milliseconds 250
  } while ((Get-Date) -lt $deadline)

  $tail = Get-LogTail -Path $LogPath
  throw "$Label did not become ready within ${TimeoutSeconds}s.`n$tail"
}

function Start-DaemonOnly {
  $daemonArgs = @('-m', 'synapse_daemon', '--port', '7878', '--data-dir', 'data')
  if ($BindLan) {
    $daemonArgs += '--bind-lan'
  }
  Write-Host "-> Starting daemon (foreground): python $($daemonArgs -join ' ')"
  Write-Host ""
  & python @daemonArgs
  exit $LASTEXITCODE
}

if ($DaemonOnly) {
  Start-DaemonOnly
}

$env:SYNAPSE_DEV_WRAPPER = '1'
$restartRequested = $false
$electronExitCode = 0

do {
  $restartRequested = $false
  $daemonProc = $null
  $viteProc = $null

  try {
    if (-not $AppOnly) {
      $daemonCommand = 'python -m synapse_daemon --port 7878 --data-dir data'
      if ($BindLan) {
        $daemonCommand += ' --bind-lan'
      }
      $daemonProc = Start-LoggedCmdProcess -Label 'daemon' -Command $daemonCommand -LogPath $daemonLog
      Wait-HttpReady `
        -Label 'Daemon' `
        -Urls @('http://127.0.0.1:7878/api/v1/health') `
        -TimeoutSeconds 30 `
        -Process $daemonProc `
        -LogPath $daemonLog
    }

    Write-Host "-> Compiling Electron main -> dist-electron/"
    & npm run build:electron
    if ($LASTEXITCODE -ne 0) {
      throw 'build:electron failed'
    }

    $viteProc = Start-LoggedCmdProcess `
      -Label 'Vite dev server' `
      -Command 'node node_modules\vite\bin\vite.js' `
      -LogPath $viteLog
    Wait-HttpReady `
      -Label 'Vite' `
      -Urls @('http://127.0.0.1:5173', 'http://localhost:5173') `
      -TimeoutSeconds 60 `
      -Process $viteProc `
      -LogPath $viteLog `
      -ReadyPattern 'ready in'

    Write-Host "-> Launching Electron"
    Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
    $electronCli = Join-Path $root 'node_modules\electron\cli.js'
    if (-not (Test-Path $electronCli)) {
      throw "Electron CLI not found at $electronCli. Run npm install first."
    }
    & node $electronCli . @ElectronArgs
    $electronExitCode = $LASTEXITCODE

    if ($electronExitCode -eq $restartExitCode) {
      Write-Host "-> Electron requested a full Synapse restart"
      $restartRequested = $true
    } elseif ($electronExitCode -ne 0) {
      Write-Warning "Electron exited with code $electronExitCode"
    }
  } finally {
    Stop-ProcessTree -Process $viteProc -Label 'Vite'
    Stop-ProcessTree -Process $daemonProc -Label 'daemon'
  }

  if ($restartRequested) {
    Start-Sleep -Milliseconds 500
  }
} while ($restartRequested)

exit $electronExitCode
