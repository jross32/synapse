param(
  [switch]$Push,
  [string]$Remote = 'origin',
  [string]$Branch = ''
)
$ErrorActionPreference = 'Stop'
$root = (git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Not a Git repository.' }
Push-Location $root
try {
  $current = (git symbolic-ref --quiet --short HEAD).Trim()
  if ($LASTEXITCODE -ne 0 -or -not $current) { throw 'Detached HEAD is not eligible for automatic publishing.' }
  if ($Branch -and $Branch -ne $current) { throw 'Requested branch does not match checked-out branch.' }
  $branchName = $current
  if ($branchName -eq 'main' -or $branchName -eq 'master') { throw 'Direct publishing from the default branch is disabled.' }
  $origin = (git remote get-url $Remote).Trim()
  if ($LASTEXITCODE -ne 0 -or $origin -notmatch '(?i)(github\.com[:/])jross32/synapse(\.git)?$') { throw 'Remote is not the approved Synapse GitHub repository.' }
  $head = (git rev-parse HEAD).Trim()
  if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-f]{40}$') { throw 'Cannot resolve local commit.' }
  if ($Push) {
    $dirty = @(git status --porcelain --untracked-files=no)
    if ($dirty.Count -gt 0) { throw 'Tracked worktree is dirty; commit and verify changes before pushing.' }
    git push $Remote ('HEAD:refs/heads/' + $branchName)
    if ($LASTEXITCODE -ne 0) { throw 'Git push failed.' }
  }
  $line = @(git ls-remote --heads $Remote ('refs/heads/' + $branchName))
  if ($LASTEXITCODE -ne 0 -or $line.Count -ne 1) { throw 'Remote branch is missing or cannot be verified.' }
  $remoteHead = ($line[0] -split '\s+')[0]
  if ($remoteHead -ne $head) { throw "Remote SHA mismatch. Local=$head Remote=$remoteHead" }
  [pscustomobject]@{ verified=$true; repository=$origin; branch=$branchName; commit=$head; pushed=[bool]$Push } | ConvertTo-Json
} finally { Pop-Location }
