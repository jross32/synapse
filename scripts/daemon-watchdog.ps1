# Synapse -- daemon watchdog
#
# Catches a failure mode process-liveness checks miss entirely: the daemon's
# event loop can wedge (hang) while the process stays alive and the listen
# socket stays open. `Get-Process` and `netstat` both say "fine" in that state;
# only an actual HTTP round-trip against /api/v1/health reveals it. This
# happened live on 2026-08-21 -- the daemon went silent for 25+ minutes before
# a human/AI noticed by chance, silently blocking every connector call in the
# meantime. See review proposal d8e50063a990 for the incident writeup.
#
# Run standalone (dev.ps1 spawns it automatically for -DaemonOnly and the
# full-stack loop) or by hand:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/daemon-watchdog.ps1
#
# Self-terminating by design: if no process is listening on -Port at all, this
# assumes the daemon was stopped on purpose (Ctrl+C, taskkill, script exit) and
# exits quietly rather than trying to resurrect an intentionally-stopped daemon.
# That means nothing needs to remember to kill the watchdog when the daemon
# stops -- it notices on its own next poll.
#
# NOTE: restarting the daemon opens a brand-new Cloudtap WAN tunnel with a new
# random hostname (this is existing, unrelated daemon behavior, not something
# this script controls). Any live MCP connector pointed at the old tunnel URL
# will need to be recreated after a watchdog-triggered restart. That is a real
# cost, but a wedged daemon is already fully unreachable to that connector --
# recovering automatically, even at that cost, beats staying wedged indefinitely.
#
# NOTE: pure ASCII, like dev.ps1 -- see the header comment in that file for why.

param(
  [int]$Port = 7878,
  [string]$DataDir = 'data',
  [switch]$BindLan,
  [int]$IntervalSeconds = 30,
  [int]$FailureThreshold = 3,
  [int]$HealthTimeoutSeconds = 5,
  [int]$GraceSeconds = 25
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$logPath = Join-Path $root (Join-Path $DataDir 'daemon-runtime.log')
$watchdogLogPath = Join-Path $root (Join-Path $DataDir 'daemon-watchdog.log')

function Write-WatchdogLog {
  param([string]$Message)
  $line = "{0} [watchdog] {1}" -f (Get-Date -Format 'HH:mm:ss'), $Message
  Add-Content -Path $watchdogLogPath -Value $line
}

function Get-DaemonProcessId {
  param([int]$Port)
  # Same identification pattern as dev.ps1's Clear-StalePort: find who owns the
  # listen socket, then confirm via command line that it is really our daemon.
  # Matching on the port avoids ever touching an unrelated python process.
  try {
    $conns = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
  } catch {
    return $null
  }
  if (-not $conns) {
    return $null
  }
  foreach ($procId in ($conns | Select-Object -ExpandProperty OwningProcess -Unique)) {
    if (-not $procId -or $procId -eq 0) {
      continue
    }
    try {
      $cimProc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
    } catch {
      continue
    }
    if ($cimProc -and "$($cimProc.CommandLine)".ToLower().Contains('synapse_daemon')) {
      return $procId
    }
  }
  return $null
}

function Test-DaemonHealthy {
  param([int]$Port, [int]$TimeoutSeconds)
  try {
    $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec $TimeoutSeconds `
      -Uri "http://127.0.0.1:$Port/api/v1/health"
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

function Restart-WedgedDaemon {
  param([int]$Port, [int]$OwnerPid)

  Write-WatchdogLog "daemon on port $Port (PID $OwnerPid) failed $FailureThreshold consecutive health checks -- restarting"
  Add-Content -Path $logPath -Value ""
  Add-Content -Path $logPath -Value "=== WATCHDOG RESTART: PID $OwnerPid stopped responding to /api/v1/health, killed and relaunched ==="

  # Each step gets its own try/catch, not just the caller's. A restart attempt is
  # already the exceptional path; a failure *inside* it must not also take down
  # the watchdog itself -- that happened for real on 2026-08-21: taskkill failed
  # (this machine's native-command exit codes get promoted to terminating errors
  # under $ErrorActionPreference = 'Stop' on newer PowerShell), the uncaught
  # exception propagated past this function with no catch anywhere above it, and
  # the whole watchdog process silently exited -- leaving the daemon not just
  # un-restarted but with NOTHING watching it afterward. The daemon happened to
  # recover on its own that time; it would not have if it had been a real wedge.
  try {
    & taskkill /PID $OwnerPid /T /F 2>&1 | Out-Null
  } catch {
    Write-WatchdogLog "taskkill against PID $OwnerPid failed: $($_.Exception.Message) -- attempting relaunch anyway"
  }
  Start-Sleep -Milliseconds 500

  $daemonArgs = @('-m', 'synapse_daemon', '--port', "$Port", '--data-dir', $DataDir)
  if ($BindLan) {
    $daemonArgs += '--bind-lan'
  }
  $argsJoined = $daemonArgs -join ' '
  $wrapped = "python $argsJoined >> `"$logPath`" 2>&1"
  try {
    $proc = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/d', '/c', $wrapped) `
      -WorkingDirectory $root -WindowStyle Hidden -PassThru
    Write-WatchdogLog "relaunched daemon as PID $($proc.Id)"
    return $proc.Id
  } catch {
    Write-WatchdogLog "relaunch failed: $($_.Exception.Message) -- will retry from the next health check"
    return $null
  }
}

Write-WatchdogLog "started -- watching port $Port every ${IntervalSeconds}s (threshold: $FailureThreshold consecutive failures, ${HealthTimeoutSeconds}s timeout per check)"

$consecutiveFailures = 0
$wasHealthy = $true
# After our own restart, the fresh process needs time to actually bind the port
# (schema migration etc. can take several seconds). Until $graceDeadline, "nothing
# listening yet" means "still booting", not "intentionally stopped" -- checked by
# process liveness (PID in the process table) rather than port state, since the
# port genuinely isn't bound yet during that window. Skipping this distinction
# caused a real bug caught in testing: the watchdog would restart a wedged daemon
# correctly, then see no listener on its very next poll (process still starting
# up) and immediately self-terminate, leaving the fresh daemon completely
# unprotected. Confirmed fixed against a real relaunch before this shipped.
$graceDeadline = [DateTime]::MinValue
$graceOwnerPid = $null

while ($true) {
  Start-Sleep -Seconds $IntervalSeconds

  # Defense in depth on top of Restart-WedgedDaemon's own try/catch: nothing in
  # this loop should ever be able to take the whole watchdog down silently.
  # $exitRequested distinguishes a deliberate `exit 0` (daemon stopped on
  # purpose) from just falling through after an unexpected error -- only the
  # former should actually stop the loop.
  $exitRequested = $false
  try {
    $inGrace = $graceOwnerPid -and ((Get-Date) -lt $graceDeadline)
    $ownerPid = Get-DaemonProcessId -Port $Port

    if (-not $ownerPid) {
      if ($inGrace) {
        $stillBooting = Get-Process -Id $graceOwnerPid -ErrorAction SilentlyContinue
        if ($stillBooting) {
          continue
        }
        Write-WatchdogLog "relaunched process (PID $graceOwnerPid) exited during startup and never bound port $Port -- treating as intentional stop, watchdog exiting"
        $exitRequested = $true
      } else {
        Write-WatchdogLog "no process listening on port $Port -- daemon appears intentionally stopped, watchdog exiting"
        $exitRequested = $true
      }
    } else {
      $graceOwnerPid = $null

      if (Test-DaemonHealthy -Port $Port -TimeoutSeconds $HealthTimeoutSeconds) {
        if (-not $wasHealthy) {
          Write-WatchdogLog "daemon healthy again (PID $ownerPid)"
        }
        $consecutiveFailures = 0
        $wasHealthy = $true
      } else {
        $wasHealthy = $false
        $consecutiveFailures += 1
        Write-WatchdogLog "health check failed ($consecutiveFailures/$FailureThreshold) for PID $ownerPid"

        if ($consecutiveFailures -ge $FailureThreshold) {
          $graceOwnerPid = Restart-WedgedDaemon -Port $Port -OwnerPid $ownerPid
          $graceDeadline = (Get-Date).AddSeconds($GraceSeconds)
          $consecutiveFailures = 0
        }
      }
    }
  } catch {
    Write-WatchdogLog "unexpected error in watch loop, continuing: $($_.Exception.Message)"
  }

  if ($exitRequested) {
    exit 0
  }
}
