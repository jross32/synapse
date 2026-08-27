# Synapse -- persistent tunnel watchdog
#
# Companion to daemon-watchdog.ps1, watching the OTHER thing that can quietly
# die: the persistent Cloudflare Tunnel process (`cloudflared tunnel run
# synapse`) that makes synapse.whatapc.com reachable from the outside. Nothing
# previously restarted this if it crashed, and unlike the daemon's own quick-
# tunnel fallback, this one has no automatic self-heal at all -- if cloudflared
# dies, the daemon can be perfectly healthy locally and still be completely
# unreachable to any MCP connector until a human notices and reruns it by hand.
# Built 2026-08-22 as part of making Synapse safe to leave running unattended
# for multiple days (checked in on from a phone, not a desk).
#
# Two distinct failure modes, checked separately:
#   1. The cloudflared process itself is gone (crashed, killed, machine hiccup)
#      -- detected by process presence, same pattern as daemon-watchdog.ps1's
#      Get-DaemonProcessId.
#   2. The process is still alive, but the tunnel itself has gone stale/stuck
#      -- detected the same way the daemon's own wedge was: an external HTTP
#      round-trip through the tunnel actually succeeding, not just the process
#      existing. A hung tunnel with a live process would otherwise look fine
#      forever.
# Either one triggers the same recovery: kill cloudflared (if still present)
# and relaunch `cloudflared tunnel run synapse` from C:\Users\justi\.cloudflared
# \config.yml, which routes synapse.whatapc.com -> http://localhost:7878. The
# hostname never changes across a restart of *this* watchdog's own logic --
# that is the whole point of the named tunnel over the old quick-tunnel.
#
# Self-terminating by design, same rule as daemon-watchdog.ps1, WITH the same
# one-extra-window patience added 2026-08-27: if the daemon isn't listening,
# this could be Synapse stopped on purpose, or it could be daemon-watchdog.ps1
# mid its own (now automatic) recovery from an unexplained daemon exit -- the
# two look identical from here. So on first reaching the absence threshold,
# this resets and keeps watching for one more full threshold window rather than
# exiting immediately; only a SECOND consecutive threshold-crossing with no
# daemon sighting in between is treated as a real, sustained stop. Running a
# tunnel with nothing behind it to proxy to would still be pointless, but it's
# cheap to wait one more cycle before concluding that's actually the situation.
#
# Run standalone or let dev.ps1 spawn it automatically alongside the daemon:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tunnel-watchdog.ps1
#
# NOTE: pure ASCII, like dev.ps1 and daemon-watchdog.ps1.

param(
  [int]$Port = 7878,
  [string]$TunnelName = 'synapse',
  [string]$PublicUrl = 'https://synapse.whatapc.com/api/v1/health',
  [int]$IntervalSeconds = 45,
  [int]$FailureThreshold = 3,
  [int]$CheckTimeoutSeconds = 8
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$watchdogLogPath = Join-Path $root 'data\tunnel-watchdog.log'

function Write-TunnelWatchdogLog {
  param([string]$Message)
  $line = "{0} [tunnel-watchdog] {1}" -f (Get-Date -Format 'HH:mm:ss'), $Message
  try {
    Add-Content -Path $watchdogLogPath -Value $line
  } catch {
    # Never let a logging failure take the watchdog down -- same lesson as
    # daemon-watchdog.ps1's restart-marker bug, applied preemptively here.
  }
}

function Get-DaemonListening {
  param([int]$Port)
  try {
    $conns = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    return [bool]$conns
  } catch {
    return $false
  }
}

function Get-TunnelProcessId {
  param([string]$TunnelName)
  try {
    $procs = Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue
  } catch {
    return $null
  }
  foreach ($p in $procs) {
    if ("$($p.CommandLine)".ToLower().Contains("tunnel run $($TunnelName.ToLower())")) {
      return $p.ProcessId
    }
  }
  return $null
}

function Test-TunnelReachable {
  param([string]$Url, [int]$TimeoutSeconds)
  try {
    $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec $TimeoutSeconds -Uri $Url
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

function Restart-Tunnel {
  param([int]$ExistingPid, [string]$TunnelName)

  Write-TunnelWatchdogLog "restarting tunnel '$TunnelName' (existing PID: $(if ($ExistingPid) { $ExistingPid } else { 'none' }))"

  if ($ExistingPid) {
    try {
      & taskkill /PID $ExistingPid /F 2>&1 | Out-Null
    } catch {
      Write-TunnelWatchdogLog "taskkill against PID $ExistingPid failed: $($_.Exception.Message) -- attempting relaunch anyway"
    }
    Start-Sleep -Milliseconds 500
  }

  try {
    $proc = Start-Process -FilePath 'cloudflared' -ArgumentList @('tunnel', 'run', $TunnelName) `
      -WindowStyle Hidden -PassThru
    Write-TunnelWatchdogLog "relaunched cloudflared as PID $($proc.Id)"
  } catch {
    Write-TunnelWatchdogLog "relaunch failed: $($_.Exception.Message) -- will retry from the next check"
  }
}

Write-TunnelWatchdogLog "started -- watching tunnel '$TunnelName' every ${IntervalSeconds}s (threshold: $FailureThreshold consecutive unreachable checks, ${CheckTimeoutSeconds}s timeout per check)"

$consecutiveFailures = 0
$wasReachable = $true
$consecutiveAbsent = 0
# Mirrors daemon-watchdog.ps1's $autoRestartOnAbsenceUsed: reset to $false the
# moment the daemon is seen listening again, so a recurring mystery-death still
# gets a full extra window of patience every time it happens.
$extendedGraceUsed = $false

while ($true) {
  Start-Sleep -Seconds $IntervalSeconds

  $exitRequested = $false
  try {
    if (-not (Get-DaemonListening -Port $Port)) {
      # A single missed check here is NOT reliable evidence of an intentional shutdown --
      # confirmed live 2026-08-24: the daemon can be mid-restart-cycle (daemon-watchdog killing
      # and relaunching a wedged process, a 1-2s gap) at the exact moment this check lands, and
      # exiting on that false signal orphans the tunnel with nothing watching it afterward. Require
      # the same consecutive-failure discipline as the reachability check below before concluding
      # this is real, not a one-off restart-window coincidence.
      $consecutiveAbsent += 1
      Write-TunnelWatchdogLog "no daemon listening on port $Port ($consecutiveAbsent/$FailureThreshold) -- may just be mid-restart"
      if ($consecutiveAbsent -ge $FailureThreshold) {
        if (-not $extendedGraceUsed) {
          $extendedGraceUsed = $true
          $consecutiveAbsent = 0
          Write-TunnelWatchdogLog "daemon absent for $FailureThreshold consecutive checks -- giving it one more full window in case daemon-watchdog is mid its own auto-recovery, not exiting yet"
        } else {
          Write-TunnelWatchdogLog "daemon absent again with no sighting in between -- already used this cycle's extra patience, treating as a real intentional stop, tunnel watchdog exiting"
          $exitRequested = $true
        }
      }
    } else {
      $consecutiveAbsent = 0
      $extendedGraceUsed = $false
      $tunnelPid = Get-TunnelProcessId -TunnelName $TunnelName
      $reachable = Test-TunnelReachable -Url $PublicUrl -TimeoutSeconds $CheckTimeoutSeconds

      if (-not $tunnelPid) {
        Write-TunnelWatchdogLog "cloudflared process for tunnel '$TunnelName' not found -- restarting immediately"
        Restart-Tunnel -ExistingPid $null -TunnelName $TunnelName
        $consecutiveFailures = 0
        $wasReachable = $true
      } elseif ($reachable) {
        if (-not $wasReachable) {
          Write-TunnelWatchdogLog "tunnel reachable again (PID $tunnelPid)"
        }
        $consecutiveFailures = 0
        $wasReachable = $true
      } else {
        $wasReachable = $false
        $consecutiveFailures += 1
        Write-TunnelWatchdogLog "public URL check failed ($consecutiveFailures/$FailureThreshold) for PID $tunnelPid"

        if ($consecutiveFailures -ge $FailureThreshold) {
          Restart-Tunnel -ExistingPid $tunnelPid -TunnelName $TunnelName
          $consecutiveFailures = 0
        }
      }
    }
  } catch {
    Write-TunnelWatchdogLog "unexpected error in watch loop, continuing: $($_.Exception.Message)"
  }

  if ($exitRequested) {
    exit 0
  }
}
