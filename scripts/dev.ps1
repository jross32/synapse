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

# The daemon is an editable install (`pip install -e daemon/`) that lives ONLY in
# .venv, not in whatever `python` happens to resolve to on PATH. A bare `python`
# here is the machine's system interpreter, which has no `synapse_daemon` module
# -- the daemon then exits instantly with "No module named synapse_daemon" and
# the whole launch fails at the first stage. Always prefer the repo venv; fall
# back to PATH `python` only for a checkout that has not run the venv setup yet.
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
  $pythonExe = $venvPython
} else {
  $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
  $pythonExe = if ($pythonCmd -and $pythonCmd.Source) { $pythonCmd.Source } else { 'python' }
  Write-Warning "Repo venv not found at $venvPython -- falling back to PATH python ($pythonExe). Run 'python -m venv .venv; .venv\Scripts\pip install -e daemon' if the daemon fails to start."
}

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

function Clear-StalePort {
  param(
    [Parameter(Mandatory = $true)]
    [int]$Port,
    [Parameter(Mandatory = $true)]
    [string]$Match,
    [Parameter(Mandatory = $true)]
    [string]$Label
  )

  # Best-effort pre-flight cleanup. A crashed or force-quit run orphans its
  # child (the daemon on 7878, Vite on 5173); the orphan keeps squatting on the
  # port so the next launch cannot bind and the whole start fails -- which the
  # finally-block then reports as "Stopping daemon", looking like a crash.
  # Kill ONLY a process whose command line clearly belongs to us ($Match) so an
  # unrelated user process on the same port is never touched. Any failure here
  # is swallowed: cleanup must never abort a launch.
  try {
    $conns = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if (-not $conns) {
      return
    }
    $stalePids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $stalePids) {
      if (-not $procId -or $procId -eq 0) {
        continue
      }
      $cmd = ''
      try {
        $cimProc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
        if ($cimProc) {
          $cmd = "$($cimProc.CommandLine)"
        }
      } catch {
      }
      if ($cmd.ToLower().Contains($Match.ToLower())) {
        Write-Host "-> Clearing stale $Label (PID $procId) holding port $Port before start"
        & taskkill /PID $procId /T /F | Out-Null
        Start-Sleep -Milliseconds 400
      } else {
        Write-Warning "Port $Port is held by a non-Synapse process (PID $procId); leaving it. The launch may fail to bind."
      }
    }
  } catch {
    Write-Host "   (stale-port check for $Port skipped: $($_.Exception.Message))"
  }
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

  # Use CREATE_NO_WINDOW instead of Start-Process -WindowStyle Hidden. On Windows
  # 11 with Windows Terminal configured as the console host, "hidden" console
  # launches can still create/consolidate Terminal hosts and were correlated
  # with repeated WindowsTerminal.exe crashes. CreateNoWindow keeps the same
  # log redirection/Process object semantics without creating a console host.
  $wrapped = "$Command >> `"$LogPath`" 2>&1"
  $startInfo = New-Object System.Diagnostics.ProcessStartInfo
  $startInfo.FileName = "$env:ComSpec"
  $startInfo.Arguments = "/d /c `"$wrapped`""
  $startInfo.WorkingDirectory = $root
  $startInfo.UseShellExecute = $false
  $startInfo.CreateNoWindow = $true
  $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

  Write-Host "-> Starting $Label"
  $proc = [System.Diagnostics.Process]::Start($startInfo)
  if (-not $proc) {
    throw "Failed to start $Label."
  }
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

function Start-NoConsoleProcess {
  param(
    [Parameter(Mandatory = $true)]
    [string]$FilePath,
    [string[]]$Arguments = @(),
    [string]$WorkingDirectory = $root
  )

  $command = Get-Command $FilePath -ErrorAction SilentlyContinue
  $resolved = if ($command -and $command.Source) { $command.Source } else { $FilePath }

  $startInfo = New-Object System.Diagnostics.ProcessStartInfo
  $startInfo.FileName = $resolved
  $startInfo.Arguments = ($Arguments -join ' ')
  $startInfo.WorkingDirectory = $WorkingDirectory
  $startInfo.UseShellExecute = $false
  $startInfo.CreateNoWindow = $true
  $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

  $proc = [System.Diagnostics.Process]::Start($startInfo)
  if (-not $proc) {
    throw "Failed to start background process: $FilePath"
  }
  return $proc
}


function Get-RunningWatchdogPid {
  # Neither watchdog self-registers a lock file or checks for a sibling before
  # launching, and both are detached (Start-Process -WindowStyle Hidden) so
  # they survive independently of whatever process tree spawned them -- every
  # restart of *this* script, across a whole session, silently added another
  # one on top of any still running from an earlier restart rather than
  # replacing it. Confirmed live 2026-08-26: after a normal night of restarts
  # plus a real internet outage that repeatedly knocked the tunnel down, SEVEN
  # separate tunnel-watchdog.ps1 processes (and seven daemon-watchdog.ps1
  # processes) were all running at once, independently racing each other to
  # "fix" the same tunnel -- which is exactly what produced the double-PID
  # "relaunched as PID X" / "relaunched as PID Y" log lines within the same
  # second: two watchdogs both saw the process missing and both relaunched it.
  # A process-presence check here, matching how the watchdogs themselves
  # detect their own targets, is the fix: don't start a second one if one is
  # already alive.
  param([string]$ScriptName)
  try {
    $procs = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue
  } catch {
    return $null
  }
  foreach ($p in $procs) {
    if ("$($p.CommandLine)".ToLower().Contains($ScriptName.ToLower())) {
      return $p.ProcessId
    }
  }
  return $null
}

function Start-DaemonWatchdog {
  param([int]$Port = 7878)

  $existing = Get-RunningWatchdogPid -ScriptName 'daemon-watchdog-v2.ps1'
  if ($existing) {
    Write-Host "-> Daemon watchdog already running (PID $existing) -- not starting a duplicate"
    return
  }

  # Detached, hidden, non-blocking. Self-terminates once this daemon process
  # is gone (see the header comment in daemon-watchdog.ps1) -- nothing here
  # needs to remember to stop it.
  $watchdogScript = Join-Path $PSScriptRoot 'daemon-watchdog-v2.ps1'
  $watchdogArgs = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $watchdogScript,
    '-Port', "$Port", '-DataDir', 'data'
  )
  if ($BindLan) {
    $watchdogArgs += '-BindLan'
  }
  $watchdogProc = Start-NoConsoleProcess -FilePath 'powershell.exe' -Arguments $watchdogArgs
  Write-Host "-> Daemon watchdog armed as PID $($watchdogProc.Id) (polls basic + MCP health, preserves managed projects, auto-recovers after 3 consecutive failures)"
}

function Start-PersistentTunnel {
  # Named Cloudflare Tunnel (synapse.whatapc.com) -- replaces the daemon's own
  # Cloudtap quick-tunnel, which gets a brand-new random hostname every restart
  # (real cost paid repeatedly: every restart broke any live MCP connector,
  # requiring it to be manually recreated, sometimes with a real propagation
  # delay before external consumers could reach the new hostname). This tunnel
  # keeps the same hostname across restarts, so a connector pointed at it never
  # needs to change. wan_auto_start was turned off via PATCH /api/v1/system/network
  # once this was set up, so the daemon no longer opens a redundant quick tunnel.
  # Setup (one-time, already done): `cloudflared tunnel login`, `cloudflared
  # tunnel create synapse`, `cloudflared tunnel route dns synapse
  # synapse.whatapc.com`, and C:\Users\justi\.cloudflared\config.yml routing
  # that hostname to http://localhost:7878.
  #
  # Idempotent: skips starting a second tunnel process if one is already running.
  $existing = Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains('tunnel run synapse') }
  if ($existing) {
    Write-Host "-> Persistent Cloudflare tunnel already running (PID $(($existing | Select-Object -First 1).ProcessId))"
    return
  }
  if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "-> cloudflared not found on PATH; skipping persistent tunnel"
    return
  }
  $cloudflaredProc = Start-NoConsoleProcess -FilePath 'cloudflared.exe' -Arguments @('tunnel', 'run', 'synapse')
  Write-Host "-> Persistent Cloudflare tunnel started as PID $($cloudflaredProc.Id) (synapse.whatapc.com)"
}

function Start-TunnelWatchdog {
  # Companion to Start-DaemonWatchdog: watches the cloudflared process itself,
  # not the daemon. Nothing previously restarted the tunnel if it crashed or
  # went stale while the daemon stayed perfectly healthy locally -- meaning
  # every MCP connector could go dark with no automatic recovery at all. See
  # scripts/tunnel-watchdog.ps1 for the detection/recovery details.
  $existing = Get-RunningWatchdogPid -ScriptName 'tunnel-watchdog.ps1'
  if ($existing) {
    Write-Host "-> Tunnel watchdog already running (PID $existing) -- not starting a duplicate"
    return
  }

  $watchdogScript = Join-Path $PSScriptRoot 'tunnel-watchdog.ps1'
  $watchdogArgs = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $watchdogScript,
    '-Port', '7878'
  )
  $watchdogProc = Start-NoConsoleProcess -FilePath 'powershell.exe' -Arguments $watchdogArgs
  Write-Host "-> Tunnel watchdog armed as PID $($watchdogProc.Id) (checks synapse.whatapc.com, auto-restarts cloudflared after 3 consecutive failures)"
}

function Start-TerminalCloak {
  # Prefer the persistent Scheduled Task when installed. It runs pythonw.exe,
  # has restart-on-failure settings, and is also surfaced in Synapse -> Watchdogs.
  $task = Get-ScheduledTask -TaskName 'Synapse Terminal Cloak' -ErrorAction SilentlyContinue
  if ($task) {
    if ([string]$task.State -ne 'Running') {
      Start-ScheduledTask -TaskName 'Synapse Terminal Cloak'
      Write-Host "-> Terminal cloak scheduled task started"
    } else {
      Write-Host "-> Terminal cloak scheduled task already running"
    }
    return
  }

  # Portable fallback for a source checkout where the task has not been installed.
  $pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
  if (-not (Test-Path $pythonw)) {
    $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if ($python) {
      $pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
    }
  }
  if (-not $pythonw -or -not (Test-Path $pythonw)) {
    Write-Warning "pythonw.exe not found; terminal cloak not started"
    return
  }

  $cloakScript = Join-Path $PSScriptRoot 'terminal_cloak.py'
  $cloakProc = Start-NoConsoleProcess -FilePath $pythonw -Arguments @(
    "`"$cloakScript`"", '--poll-ms', '75'
  )
  Write-Host "-> Terminal cloak armed as PID $($cloakProc.Id) (Python/Win32, no WMI polling)"
}

function Start-DaemonOnly {
  $daemonArgs = @('-m', 'synapse_daemon', '--port', '7878', '--data-dir', 'data')
  if ($BindLan) {
    $daemonArgs += '--bind-lan'
  }
# Let MCP clients (the ChatGPT / claude.ai connectors) dispatch real work, not just read.
# Without this the connector advertises read-only tools, so a remote chat can look at
# projects and can do nothing with them. Gated by an env var rather than always-on, and the
# connector still requires the auth token on every call.
$env:SYNAPSE_MCP_ALLOW_WRITES = '1'

  Write-Host "-> Starting daemon (foreground): `"$pythonExe`" $($daemonArgs -join ' ')"
  Write-Host ""
  Start-DaemonWatchdog -Port 7878
  Start-PersistentTunnel
  Start-TunnelWatchdog
  Start-TerminalCloak
  & $pythonExe @daemonArgs
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
      Clear-StalePort -Port 7878 -Match 'synapse_daemon' -Label 'daemon'
      $daemonCommand = '"' + $pythonExe + '" -m synapse_daemon --port 7878 --data-dir data'
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
      Start-DaemonWatchdog -Port 7878
      Start-PersistentTunnel
      Start-TunnelWatchdog
      Start-TerminalCloak
    }

    Write-Host "-> Compiling Electron main -> dist-electron/"
    & npm run build:electron
    if ($LASTEXITCODE -ne 0) {
      throw 'build:electron failed'
    }

    Clear-StalePort -Port 5173 -Match 'vite' -Label 'Vite dev server'
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


