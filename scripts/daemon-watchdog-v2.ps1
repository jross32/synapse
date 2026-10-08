# Synapse daemon watchdog v2 -- connector-aware, preservation-safe recovery.
param(
  [int]$Port = 7878,
  [string]$DataDir = 'data',
  [switch]$BindLan,
  [int]$IntervalSeconds = 30,
  [int]$FailureThreshold = 3,
  [int]$HealthTimeoutSeconds = 5,
  [int]$McpFailureThreshold = 6,
  [int]$McpHealthTimeoutSeconds = 5,
  [int]$LowDiskFreeMB = 512,
  [int]$GraceSeconds = 120
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
  try {
    Add-Content -Path $watchdogLogPath -Value $line
  } catch {
    # Disk pressure must never kill the process that is supposed to recover Synapse.
    # If logging cannot persist, keep supervising and let later healthy ticks resume logging.
  }
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

function Get-DaemonHealth {
  param(
    [int]$Port,
    [int]$BasicTimeoutSeconds,
    [int]$McpTimeoutSeconds
  )

  $basicOk = $false
  $basicReason = ''
  try {
    $basic = Invoke-RestMethod -TimeoutSec $BasicTimeoutSeconds -Uri "http://127.0.0.1:$Port/api/v1/health"
    $basicOk = [bool]$basic.ok
    if (-not $basicOk) { $basicReason = 'basic health returned ok=false' }
  } catch {
    $basicReason = $_.Exception.Message
  }

  if (-not $basicOk) {
    return [pscustomobject]@{
      BasicOk = $false
      McpOk = $false
      BasicReason = $basicReason
      McpReason = 'not checked because basic health failed'
    }
  }

  $mcpOk = $false
  $mcpReason = ''
  try {
    # This endpoint is a lock-only snapshot, but MCP lane degradation is not the
    # same failure class as a dead daemon. Keep the result separate so a slow or
    # saturated executor cannot immediately gain process-kill authority.
    $mcp = Invoke-RestMethod -TimeoutSec $McpTimeoutSeconds -Uri "http://127.0.0.1:$Port/api/v1/health/mcp"
    $mcpOk = [bool]$mcp.ok
    if (-not $mcpOk) {
      $stalled = @($mcp.stalled_lanes) -join ','
      $mcpReason = if ($stalled) { "stalled lanes: $stalled" } else { 'MCP health returned ok=false' }
    }
  } catch {
    $mcpReason = $_.Exception.Message
  }

  return [pscustomobject]@{
    BasicOk = $true
    McpOk = $mcpOk
    BasicReason = ''
    McpReason = $mcpReason
  }
}

function Get-FreeDiskMB {
  try {
    $driveRoot = [System.IO.Path]::GetPathRoot($root)
    $driveName = $driveRoot.TrimEnd('\').TrimEnd(':')
    $drive = Get-PSDrive -Name $driveName -ErrorAction Stop
    return [math]::Floor($drive.Free / 1MB)
  } catch {
    # Unknown disk state must not itself block recovery.
    return [double]::PositiveInfinity
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

Write-WatchdogLog "started -- basic threshold=$FailureThreshold, MCP threshold=$McpFailureThreshold, interval=${IntervalSeconds}s, startup grace=${GraceSeconds}s, low-disk floor=${LowDiskFreeMB}MB"
$consecutiveFailures = 0
$consecutiveMcpFailures = 0
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

    $consecutiveAbsent = 0
    $withinGrace = $graceOwnerPid -and (Get-Date) -lt $graceDeadline
    $health = Get-DaemonHealth -Port $Port -BasicTimeoutSeconds $HealthTimeoutSeconds -McpTimeoutSeconds $McpHealthTimeoutSeconds

    if (-not $health.BasicOk) {
      $consecutiveMcpFailures = 0
      if ($withinGrace) {
        Write-WatchdogLog "basic health not ready during startup grace for PID $ownerPid -- no recovery ($($health.BasicReason))"
        continue
      }

      $consecutiveFailures += 1
      Write-WatchdogLog "basic daemon health failed ($consecutiveFailures/$FailureThreshold) for PID $ownerPid -- $($health.BasicReason)"
      if ($consecutiveFailures -lt $FailureThreshold) { continue }

      $freeMB = Get-FreeDiskMB
      if ($freeMB -lt $LowDiskFreeMB) {
        Write-WatchdogLog "basic health is failing but free disk is only ${freeMB}MB (<${LowDiskFreeMB}MB); suppressing restart because restart cannot repair disk exhaustion"
        $consecutiveFailures = [Math]::Max(0, $FailureThreshold - 1)
        continue
      }

      Write-WatchdogLog "recovering unresponsive daemon PID $ownerPid with managed-project preservation"
      if (Recover-Daemon -Port $Port) {
        $graceOwnerPid = Start-Daemon
        $graceDeadline = (Get-Date).AddSeconds($GraceSeconds)
      }
      $consecutiveFailures = 0
      continue
    }

    # Basic health is authoritative for process liveness.
    $consecutiveFailures = 0

    if ($health.McpOk) {
      if ($consecutiveMcpFailures -gt 0) {
        Write-WatchdogLog "MCP connector healthy again while daemon stayed live (PID $ownerPid)"
      }
      $consecutiveMcpFailures = 0
      if ($withinGrace) {
        # Both layers are healthy, so startup completed successfully.
        $graceOwnerPid = $null
        $graceDeadline = [DateTime]::MinValue
      }
      continue
    }

    if ($withinGrace) {
      Write-WatchdogLog "daemon is live but MCP is not ready during startup grace for PID $ownerPid -- no recovery ($($health.McpReason))"
      continue
    }

    $graceOwnerPid = $null
    $consecutiveMcpFailures += 1
    Write-WatchdogLog "daemon is live; MCP degraded ($consecutiveMcpFailures/$McpFailureThreshold) for PID $ownerPid -- $($health.McpReason)"
    if ($consecutiveMcpFailures -lt $McpFailureThreshold) { continue }

    # Require one final independent confirmation before killing a live daemon.
    $verify = Get-DaemonHealth -Port $Port -BasicTimeoutSeconds $HealthTimeoutSeconds -McpTimeoutSeconds $McpHealthTimeoutSeconds
    if ($verify.BasicOk -and $verify.McpOk) {
      Write-WatchdogLog "MCP recovered on final confirmation; cancelling daemon recovery for PID $ownerPid"
      $consecutiveMcpFailures = 0
      continue
    }

    $freeMB = Get-FreeDiskMB
    if ($freeMB -lt $LowDiskFreeMB) {
      Write-WatchdogLog "MCP remains degraded but free disk is only ${freeMB}MB (<${LowDiskFreeMB}MB); suppressing daemon restart until disk pressure is relieved"
      $consecutiveMcpFailures = [Math]::Max(0, $McpFailureThreshold - 1)
      continue
    }

    Write-WatchdogLog "MCP degradation persisted for $McpFailureThreshold checks while daemon stayed live; recovering PID $ownerPid"
    if (Recover-Daemon -Port $Port) {
      $graceOwnerPid = Start-Daemon
      $graceDeadline = (Get-Date).AddSeconds($GraceSeconds)
    }
    $consecutiveMcpFailures = 0
  }
} finally {
  try { $mutex.ReleaseMutex() } catch {}
  $mutex.Dispose()
}
