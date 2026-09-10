# Synapse daemon watchdog v2 -- connector-aware, preservation-safe recovery.
param(
  [int]$Port = 7878,
  [string]$DataDir = 'data',
  [switch]$BindLan,
  [int]$IntervalSeconds = 30,
  [int]$FailureThreshold = 3,
  [int]$HealthTimeoutSeconds = 5,
  [int]$GraceSeconds = 60
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$logPath = Join-Path $root (Join-Path $DataDir 'daemon-runtime.log')
$watchdogLogPath = Join-Path $root (Join-Path $DataDir 'daemon-watchdog.log')
$recoveryScript = Join-Path $PSScriptRoot 'recover_daemon.py'

# The daemon (`synapse_daemon`) is an editable install that exists only in the
# repo venv, never in PATH `python`. Using bare `python` here makes every restart
# this watchdog attempts fail with "No module named synapse_daemon". Prefer the
# venv; fall back to PATH only for a checkout without a venv yet.
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
  $pythonExe = $venvPython
} else {
  $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
  $pythonExe = if ($pythonCmd -and $pythonCmd.Source) { $pythonCmd.Source } else { 'python' }
}

# One v2 watchdog per machine. This is independent from the legacy script so the
# migration can replace a still-running legacy instance without creating two v2s.
$createdNew = $false
$mutex = New-Object System.Threading.Mutex($true, 'Global\SynapseDaemonWatchdogV2', [ref]$createdNew)
if (-not $createdNew) { exit 0 }

function Write-WatchdogLog {
  param([string]$Message)
  $line = "{0} [watchdog-v2] {1}" -f (Get-Date -Format 'HH:mm:ss'), $Message
  Add-Content -Path $watchdogLogPath -Value $line
}

function Get-DaemonProcessId {
  param([int]$Port)
  try {
    $conns = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
  } catch { return $null }
  foreach ($procId in ($conns | Select-Object -ExpandProperty OwningProcess -Unique)) {
    if (-not $procId -or $procId -eq 0) { continue }
    try {
      $cimProc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
      if ($cimProc -and "$($cimProc.CommandLine)".ToLower().Contains('synapse_daemon')) {
        return $procId
      }
    } catch {}
  }
  return $null
}

function Test-DaemonHealthy {
  param([int]$Port, [int]$TimeoutSeconds)
  try {
    $basic = Invoke-RestMethod -TimeoutSec $TimeoutSeconds -Uri "http://127.0.0.1:$Port/api/v1/health"
    if (-not $basic.ok) { return $false }
    # The connector-specific endpoint detects executor deadlock/saturation that
    # the basic event-loop liveness endpoint cannot see.
    $mcp = Invoke-RestMethod -TimeoutSec $TimeoutSeconds -Uri "http://127.0.0.1:$Port/api/v1/health/mcp"
    return [bool]$mcp.ok
  } catch {
    return $false
  }
}

function Start-Daemon {
  # Match dev.ps1's connector policy when this watchdog performs the restart.
  $env:SYNAPSE_MCP_ALLOW_WRITES = '1'
  $daemonArgs = @('-m', 'synapse_daemon', '--port', "$Port", '--data-dir', $DataDir)
  if ($BindLan) { $daemonArgs += '--bind-lan' }
  $argsJoined = $daemonArgs -join ' '
  $wrapped = "`"$pythonExe`" $argsJoined >> `"$logPath`" 2>&1"
  try {
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $env:ComSpec
    $startInfo.Arguments = "/d /c `"$wrapped`""
    $startInfo.WorkingDirectory = $root
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $proc = [System.Diagnostics.Process]::Start($startInfo)
    if (-not $proc) { throw 'daemon process did not start' }
    Write-WatchdogLog "relaunched daemon wrapper as PID $($proc.Id)"
    return $proc.Id
  } catch {
    Write-WatchdogLog "relaunch failed: $($_.Exception.Message)"
    return $null
  }
}

function Recover-Daemon {
  param([int]$Port)
  try {
    $output = & $pythonExe $recoveryScript --port $Port --data-dir (Join-Path $root $DataDir) 2>&1
    if ($LASTEXITCODE -ne 0) {
      Write-WatchdogLog "targeted recovery failed: $($output -join ' ')"
      return $false
    }
    Write-WatchdogLog "targeted recovery completed: $($output -join ' ')"
    return $true
  } catch {
    Write-WatchdogLog "targeted recovery exception: $($_.Exception.Message)"
    return $false
  }
}

Write-WatchdogLog "started -- checking basic + MCP health every ${IntervalSeconds}s"
$consecutiveFailures = 0
$consecutiveAbsent = 0
$graceDeadline = [DateTime]::MinValue
$graceOwnerPid = $null

try {
  while ($true) {
    Start-Sleep -Seconds $IntervalSeconds
    $ownerPid = Get-DaemonProcessId -Port $Port
    if (-not $ownerPid) {
      $consecutiveFailures = 0
      if ($graceOwnerPid -and (Get-Date) -lt $graceDeadline) { continue }
      $consecutiveAbsent += 1
      Write-WatchdogLog "no verified daemon on port $Port ($consecutiveAbsent/$FailureThreshold)"
      if ($consecutiveAbsent -ge $FailureThreshold) {
        $graceOwnerPid = Start-Daemon
        $graceDeadline = (Get-Date).AddSeconds($GraceSeconds)
        $consecutiveAbsent = 0
      }
      continue
    }

    $graceOwnerPid = $null
    $consecutiveAbsent = 0
    if (Test-DaemonHealthy -Port $Port -TimeoutSeconds $HealthTimeoutSeconds) {
      if ($consecutiveFailures -gt 0) {
        Write-WatchdogLog "daemon + MCP connector healthy again (PID $ownerPid)"
      }
      $consecutiveFailures = 0
      continue
    }

    $consecutiveFailures += 1
    Write-WatchdogLog "daemon/MCP health failed ($consecutiveFailures/$FailureThreshold) for PID $ownerPid"
    if ($consecutiveFailures -lt $FailureThreshold) { continue }

    Write-WatchdogLog "recovering wedged daemon PID $ownerPid with managed-project preservation"
    if (Recover-Daemon -Port $Port) {
      $graceOwnerPid = Start-Daemon
      $graceDeadline = (Get-Date).AddSeconds($GraceSeconds)
    }
    $consecutiveFailures = 0
  }
} finally {
  try { $mutex.ReleaseMutex() } catch {}
  $mutex.Dispose()
}
