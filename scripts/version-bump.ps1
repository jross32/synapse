# Synapse -- version bump helper
#
# Keeps package.json (Node/Electron) and pyproject.toml (Python daemon) in
# lock-step. Appends a placeholder entry to CHANGELOG.md under [Unreleased].
#
# Synapse uses two kinds of version bumps:
#
#   * Code bump   -- implements features. patch / minor / major.
#                    Examples: 0.1.0 -> 0.1.1, 0.1.1 -> 0.2.0
#
#   * Design bump -- locks a half-step before the next code milestone.
#                    Originally docs-only (design contracts); also used for
#                    small fixes/polish that don't warrant a full patch.
#                    Appends ".5" to the current code version.
#                    Examples: 0.1.0 -> 0.1.0.5, 0.1.1 -> 0.1.1.5
#                    The next code bump increments the patch (0.1.0.5 -> 0.1.1).
#
# Usage:
#   .\scripts\version-bump.ps1 -Kind design          # X.Y.Z       -> X.Y.Z.5
#   .\scripts\version-bump.ps1 -Kind patch           # X.Y.Z[.5]   -> X.Y.(Z+1)
#   .\scripts\version-bump.ps1 -Kind minor           # X.Y.*       -> X.(Y+1).0
#   .\scripts\version-bump.ps1 -Kind major           # X.*         -> (X+1).0.0
#   .\scripts\version-bump.ps1 -Kind alpha           # X.Y.Z-alpha.N -> +.1
#   .\scripts\version-bump.ps1 -Set 0.1.0            # explicit pin
#
# Both files end up with identical literal strings (both PEP 440 and npm
# tolerate 4-component versions for non-published packages).
#
# NOTE: This file is intentionally pure ASCII. Windows PowerShell 5.1 reads
# .ps1 files as Windows-1252 unless they start with a UTF-8 BOM; the Write
# tool the assistant uses does not emit a BOM. Keep arrows as "->" not the
# unicode arrow, em-dashes as "--", and bullets as "*".

param(
  [ValidateSet('patch','minor','major','alpha','design')]
  [string]$Kind = 'design',
  [string]$Set
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$packageJsonPath = Join-Path $root 'package.json'
$pyprojectPath   = Join-Path $root 'pyproject.toml'
$changelogPath   = Join-Path $root 'CHANGELOG.md'

function Get-CoreVersion([string]$v) {
  # Strip any '-alpha.N' or '.5' design tail to get X.Y.Z
  $core = ($v -split '-')[0]
  if ($core -match '^(\d+\.\d+\.\d+)\.\d+$') { return $matches[1] }
  return $core
}

$pkg = Get-Content $packageJsonPath -Raw | ConvertFrom-Json
$currentVersion = [string]$pkg.version
$coreVersion = Get-CoreVersion $currentVersion

if ($Set) {
  $newVersion = $Set
} elseif ($Kind -eq 'design') {
  # Append .5 to core version (drop any existing tail).
  $newVersion = "$coreVersion.5"
} elseif ($Kind -eq 'alpha') {
  if ($currentVersion -match '^(\d+\.\d+\.\d+)-alpha\.(\d+)$') {
    $newVersion = "$($matches[1])-alpha.$([int]$matches[2] + 1)"
  } else {
    $newVersion = "$coreVersion-alpha.1"
  }
} else {
  $parts = $coreVersion.Split('.') | ForEach-Object { [int]$_ }
  switch ($Kind) {
    'patch' { $parts[2]++ }
    'minor' { $parts[1]++; $parts[2] = 0 }
    'major' { $parts[0]++; $parts[1] = 0; $parts[2] = 0 }
  }
  $newVersion = "$($parts[0]).$($parts[1]).$($parts[2])"
}

# Update package.json
$pkg.version = $newVersion
($pkg | ConvertTo-Json -Depth 50) | Set-Content -Path $packageJsonPath -Encoding UTF8

# Update pyproject.toml (only the [project] version line)
$pyContent = Get-Content $pyprojectPath -Raw
$pyContent = [regex]::Replace($pyContent, '(?m)^version = ".*"$', "version = `"$newVersion`"")
Set-Content -Path $pyprojectPath -Value $pyContent -Encoding UTF8

# Update __version__ in the package __init__.py (Contract #8: single source of truth).
$initPath = Join-Path $root 'daemon\synapse_daemon\__init__.py'
$initContent = Get-Content $initPath -Raw
$initContent = [regex]::Replace($initContent, '(?m)^__version__ = ".*"$', "__version__ = `"$newVersion`"")
Set-Content -Path $initPath -Value $initContent -Encoding UTF8

# Append CHANGELOG stub
$changelog = Get-Content $changelogPath -Raw
$entry = @"

## [$newVersion] -- $(Get-Date -Format 'yyyy-MM-dd')

### Added
- _Describe additions here_

### Fixed
- _Describe fixes here_

"@
$changelog = $changelog -replace '## \[Unreleased\]', "## [Unreleased]`r`n$entry"
Set-Content -Path $changelogPath -Value $changelog -Encoding UTF8

Write-Host "Synapse bumped: $currentVersion  ->  $newVersion  (kind: $Kind)"
Write-Host "Updated:"
Write-Host "  - package.json"
Write-Host "  - pyproject.toml"
Write-Host "  - daemon/synapse_daemon/__init__.py"
Write-Host "  - CHANGELOG.md (stub entry under [Unreleased])"
