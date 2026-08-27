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
# Self-terminating by design, WITH one automatic recovery attempt first: if no
# process is listening on -Port, this could be an intentional stop (Ctrl+C,
# taskkill, script exit) -- but it could also be the daemon dying on its own for
# an unknown reason, which happened for real and repeatedly on 2026-08-27 (five
# times in one session, ~15-45 minutes apart, the daemon serving fine each time
# right up until it silently exited). A genuine intentional stop and a mystery
# self-exit look identical from here: "port absent, no explanation". So on first
# detecting absence, this now attempts ONE automatic relaunch (same as a wedged-
# daemon restart) rather than assuming intent immediately. That retry budget
# resets the moment the daemon is next seen healthy -- so a real recurring
# mystery-death gets relaunched every time it happens, but if the daemon dies
# again without ever coming back healthy in between (a real crash-loop, or a
# human stopping it right after this watchdog's own restart), THAT second
# disappearance is treated as intentional and this exits for good. That means
# nothing needs to remember to kill the watchdog after a genuine, sustained stop
# -- it still notices and steps aside on its own within one extra restart cycle.
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
  [int]$GraceSeconds = 60
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

function Start-Daemon {
  # Shared launch step for both recovery paths (kill-and-relaunch a wedged
  # daemon, and relaunch-with-nothing-to-kill after an unexplained disappearance).
  # Isolated in its own try/catch for the same reason as the rest of this script:
  # a launch failure must never propagate up and silently kill the watchdog loop.
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

function Restart-WedgedDaemon {
  param([int]$Port, [int]$OwnerPid)

  Write-WatchdogLog "daemon on port $Port (PID $OwnerPid) failed $FailureThreshold consecutive health checks -- restarting"

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

  # Logged here, after the kill, not before: the old process holds an open write
  # handle on this same log file (its own >> redirect), and Add-Content can lose
  # the race for that handle while the old process is still alive -- confirmed
  # live 2026-08-21, throwing *before* taskkill ever ran meant the actual kill +
  # relaunch below never executed at all, even though the outer try/catch kept
  # the watchdog loop itself alive. Best-effort now: a failure to write this
  # marker must never skip the relaunch that follows.
  try {
    Add-Content -Path $logPath -Value ""
    Add-Content -Path $logPath -Value "=== WATCHDOG RESTART: PID $OwnerPid stopped responding to /api/v1/health, killed and relaunched ==="
  } catch {
    Write-WatchdogLog "could not write restart marker to $logPath (non-fatal): $($_.Exception.Message)"
  }

  return Start-Daemon
}

function Restart-AbsentDaemon {
  # Nothing to kill here -- the port is already unowned. Just relaunch and log a
  # marker distinct from the wedged-daemon path so the log honestly reflects
  # which recovery path fired.
  Write-WatchdogLog "no process on port $Port after $consecutiveAbsent consecutive checks -- attempting one automatic relaunch before assuming this was intentional"
  try {
    Add-Content -Path $logPath -Value ""
    Add-Content -Path $logPath -Value "=== WATCHDOG RESTART: port $Port unexpectedly unowned, relaunching (auto-recovery attempt) ==="
  } catch {
    Write-WatchdogLog "could not write restart marker to $logPath (non-fatal): $($_.Exception.Message)"
  }
  return Start-Daemon
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
# Second layer of the same protection: even outside grace, a single "nothing
# listening" observation is NOT reliable proof of an intentional stop -- confirmed
# live 2026-08-24 on the sibling tunnel-watchdog.ps1 bug, then found here too. The
# relaunch wrapper is `cmd.exe /d /c "python ... >> log"`, so $graceOwnerPid tracks
# the cmd.exe PID, not python's -- and since $GraceSeconds could still expire before
# Python finishes binding under load (worse, the old default of 25s was even LESS
# than $IntervalSeconds=30s, so grace covered zero check cycles in practice), a slow
# startup would immediately read as "intentionally stopped" and the watchdog would
# exit for good, leaving the daemon completely unprotected afterward. Require the
# same consecutive-check threshold already used for health-check failures before
# concluding this is real.
$consecutiveAbsent = 0
# Tracks whether this watchdog has already used its one auto-relaunch-on-absence
# attempt since the daemon was last confirmed healthy. Reset to $false the moment
# a health check succeeds, so a recurring mystery-death (the 2026-08-27 pattern)
# gets a fresh retry every time -- only two disappearances IN A ROW with no
# healthy check in between reads as a real, sustained stop.
$autoRestartOnAbsenceUsed = $false

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
        $consecutiveAbsent += 1
        Write-WatchdogLog "no process listening on port $Port ($consecutiveAbsent/$FailureThreshold) -- may just be a slow restart"
        if ($consecutiveAbsent -ge $FailureThreshold) {
          if (-not $autoRestartOnAbsenceUsed) {
            $autoRestartOnAbsenceUsed = $true
            $graceOwnerPid = Restart-AbsentDaemon
            $graceDeadline = (Get-Date).AddSeconds($GraceSeconds)
            $consecutiveAbsent = 0
          } else {
            Write-WatchdogLog "port $Port absent again with no healthy check in between -- already used this cycle's auto-relaunch, treating as a real intentional stop, watchdog exiting"
            $exitRequested = $true
          }
        }
      }
    } else {
      $graceOwnerPid = $null
      $consecutiveAbsent = 0

      if (Test-DaemonHealthy -Port $Port -TimeoutSeconds $HealthTimeoutSeconds) {
        if (-not $wasHealthy) {
          Write-WatchdogLog "daemon healthy again (PID $ownerPid)"
        }
        $consecutiveFailures = 0
        $wasHealthy = $true
        $autoRestartOnAbsenceUsed = $false
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
