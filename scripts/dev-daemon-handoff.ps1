# Controlled development daemon handoff.
# No implicit interruption of Synapse MCP or user workloads.
param(
  [ValidateSet('Inspect','Stage')] [string]$Action = 'Inspect',
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [string]$StageRoot = (Join-Path $env:LOCALAPPDATA 'Synapse\handoff-staging')
)
$ErrorActionPreference = 'Stop'
$preflightPath = Join-Path $RepoRoot 'scripts\dev-daemon-preflight.ps1'
if (-not (Test-Path $preflightPath)) { throw 'Missing daemon startup preflight' }
$diagnosis = & $preflightPath -RepoRoot $RepoRoot -CheckOnly | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect development daemon state' }
$source = Join-Path $RepoRoot 'daemon\synapse_daemon'
$python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$state = [ordered]@{
  action = $Action
  current_state = 'blocked'
  reason = $diagnosis.blocked_reason
  source_frontend_version = $diagnosis.frontend_version
  source_daemon_version = $diagnosis.source_daemon_version
  listeners = @($diagnosis.listeners)
  module_exists = Test-Path $source
  python_exists = Test-Path $python
  can_stage = $false
  staged_path = $null
  manual_switch_required = $true
}
# Never stage a candidate whose source version disagrees with the UI.
# This cannot be repaired simply by renaming __version__.
$pyprojectText = Get-Content (Join-Path $RepoRoot 'pyproject.toml') -Raw
$match = [regex]::Match($pyprojectText,'(?m)^version\s*=\s*"([^"]+)"')
$state.pyproject_version = if ($match.Success) { $match.Groups[1].Value } else { $null }
$state.lock_version = [string](& node -p "require(process.argv[1]).version" (Join-Path $RepoRoot 'package-lock.json'))
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect package-lock version' }
$state.can_stage = $diagnosis.source_versions_match -and
   $state.pyproject_version -eq $diagnosis.frontend_version -and
   $state.lock_version -eq $diagnosis.frontend_version -and
   $state.python_exists -and $state.module_exists
if ($Action -eq 'Stage' -and $state.can_stage) {
  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $target = Join-Path $StageRoot ("synapse-" + $diagnosis.frontend_version + "-" + $stamp)
  New-Item -ItemType Directory -Path $target -Force | Out-Null
  # A copy of source is informational; no DB is copied or mutated.
  Copy-Item $source (Join-Path $target 'synapse_daemon') -Recurse -Force
  $state.staged_path = $target
  $state.current_state = 'staged_only'
  $state.reason = 'Candidate source staged. Switching was NOT attempted. Live MCP clients, scheduled jobs and device registration remain untouched.'
} elseif ($Action -eq 'Stage') {
  $state.reason = 'Cannot stage: source package, Python daemon and lockfile versions are inconsistent or Python is unavailable. Fix the versioned build before switching.'
} elseif ($state.can_stage) {
  $state.current_state = 'ready_to_stage'
}
[pscustomobject]$state | ConvertTo-Json -Depth 6
if ($Action -eq 'Stage' -and -not $state.can_stage) { exit 4 }
