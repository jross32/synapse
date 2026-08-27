#requires -Version 5.1
<#
.SYNOPSIS
  Multi-AI coordination preflight (ADR-0024).

.DESCRIPTION
  Run before you start editing -- and before you commit -- when more than one
  AI coder shares this working tree. It:
    1. Prints the TRUE next migration + ADR numbers from disk (including
       untracked files) so a stale hand-written note never sends you to a
       number another agent already took.
    2. Summarises the working tree.
    3. With -Staged, when the daemon is reachable, checks your staged files
       against other agents' advisory file-lanes and FAILS (exit 1) on a
       cross-owner overlap -- the one enforceable coordination gate.

  File lanes are ADVISORY: Synapse cannot block edits made by external CLI
  processes. See docs/adr/0024-native-multi-ai-coordination.md and
  docs/MULTI-AI-WORKFLOW.md.

.EXAMPLE
  pwsh scripts/coordination-preflight.ps1

.EXAMPLE
  # Pre-commit lane gate. Pass YOUR coordination session id (or set
  # $env:SYNAPSE_SESSION_ID) so your own lane is not reported as a conflict with
  # yourself -- ADR-0024 tells you to claim a lane before editing, so without this
  # the agent that followed the protocol is the one that gets blocked. Lanes held
  # by OTHER sessions are still reported and still exit 1.
  pwsh scripts/coordination-preflight.ps1 -Staged -SessionId <your-session-id>
#>
[CmdletBinding()]
param(
  [switch]$Staged,
  [string]$Port = '7878',
  [string]$Token = $env:SYNAPSE_LOCAL_TOKEN,
  [string]$ProjectId,
  # Your own coordination session id, so your own lane is not reported as a conflict with
  # yourself. ADR-0024 tells every agent to claim a lane before editing, so without this the
  # well-behaved agent is the one that gets blocked. Defaults to $env:SYNAPSE_SESSION_ID.
  [string]$SessionId = $env:SYNAPSE_SESSION_ID
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

# The documented invocation does not require callers to manually plumb the daemon token.
# Prefer an explicit -Token / SYNAPSE_LOCAL_TOKEN, then fall back to the trusted-local
# token file used by the rest of Synapse. Never print the token itself.
if ([string]::IsNullOrWhiteSpace($Token)) {
  $localTokenPath = Join-Path $repoRoot 'data/auth-token'
  if (Test-Path -LiteralPath $localTokenPath) {
    try {
      $fileToken = (Get-Content -LiteralPath $localTokenPath -Raw -ErrorAction Stop).Trim()
      if (-not [string]::IsNullOrWhiteSpace($fileToken)) { $Token = $fileToken }
    } catch {
      Write-Host ("Could not read the trusted-local Synapse token ({0}); coordination may be unavailable." -f `
        $_.Exception.Message) -ForegroundColor Yellow
    }
  }
}

function Get-NextNumber {
  param([string]$Dir, [string]$Filter, [string]$Regex)
  $max = 0
  if (Test-Path $Dir) {
    Get-ChildItem -Path $Dir -Filter $Filter -File -ErrorAction SilentlyContinue | ForEach-Object {
      if ($_.Name -match $Regex) {
        $n = [int]$Matches[1]
        if ($n -gt $max) { $max = $n }
      }
    }
  }
  return $max + 1
}

$nextMig = Get-NextNumber (Join-Path $repoRoot 'daemon/synapse_daemon/migrations') '*.sql' '^(\d+)_'
$nextAdr = Get-NextNumber (Join-Path $repoRoot 'docs/adr') '*.md' '^(\d+)-'

Write-Host ''
Write-Host '=== Multi-AI coordination preflight (ADR-0024) ===' -ForegroundColor Cyan
Write-Host ("Next free migration : {0:D3}_*.sql" -f $nextMig)
Write-Host ("Next free ADR       : {0:D4}-*.md" -f $nextAdr)

Push-Location $repoRoot
try {
  $dirty = @(git status --porcelain --untracked-files=all 2>$null)
} finally {
  Pop-Location
}
Write-Host ("Working tree        : {0} changed path(s)" -f $dirty.Count)

$exitCode = 0
if ($Staged) {
  Push-Location $repoRoot
  try {
    # NOTE: must not be named $staged -- PowerShell variable names are case-insensitive, so it
    # would collide with the [switch]$Staged parameter and throw a type-conversion error before
    # the overlap check ever ran, silently disabling -Staged mode entirely.
    $stagedPaths = @(git diff --cached --name-only 2>$null | Where-Object { $_ })
  } finally {
    Pop-Location
  }
  if ($stagedPaths.Count -eq 0) {
    Write-Host 'No staged files -- nothing to check against lanes.' -ForegroundColor Yellow
  } else {
    $base = "http://127.0.0.1:$Port/api/v1"
    $headers = @{}
    if ($Token) { $headers['X-Synapse-Token'] = $Token }
    # Only send project_id when one was actually supplied. Lanes are strictly partitioned by
    # project_id server-side (list_active_lanes: NULL matches only NULL, "x" matches only "x"),
    # so the previous unconditional send of an unset -ProjectId shipped project_id = "" -- a
    # partition no lane is ever in. That matched zero lanes on every run, meaning this gate
    # silently reported "no conflicts" no matter what. Omitting the key yields None server-side,
    # which is the partition lanes claimed without a project land in.
    $payload = @{ paths = $stagedPaths }
    if (-not [string]::IsNullOrWhiteSpace($ProjectId)) { $payload['project_id'] = $ProjectId }
    if (-not [string]::IsNullOrWhiteSpace($SessionId)) { $payload['exclude_session_id'] = $SessionId }
    $body = $payload | ConvertTo-Json -Depth 5
    try {
      $resp = Invoke-RestMethod -Uri "$base/coordination/overlap" -Method Post -Headers $headers `
        -Body $body -ContentType 'application/json' -TimeoutSec 5
      if ($resp.has_conflicts) {
        Write-Host ''
        Write-Host 'LANE CONFLICT -- staged files overlap another agent''s active lane:' -ForegroundColor Red
        foreach ($c in $resp.conflicts) {
          Write-Host ("  - lane {0} (owner: {1}) overlaps: {2}" -f `
            $c.lane_id, $c.owner_label, ($c.overlapping -join ', ')) -ForegroundColor Red
        }
        Write-Host 'Hold, coordinate in .synapse-ai-context.md, or have them commit first.' -ForegroundColor Red
        $exitCode = 1
      } else {
        Write-Host 'No lane conflicts on staged files.' -ForegroundColor Green
      }
    } catch {
      Write-Host ("Coordination endpoint unavailable ({0}) -- numbering check only." -f `
        $_.Exception.Message) -ForegroundColor Yellow
    }
  }
}

Write-Host ''
Write-Host 'Reminder: read data/projects/synapse/.synapse-ai-context.md before editing.' -ForegroundColor DarkGray
exit $exitCode
