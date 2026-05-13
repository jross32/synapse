# Synapse — version bump helper
#
# Keeps package.json (Node/Electron) and pyproject.toml (Python daemon) in lock-step.
# Appends a placeholder entry to CHANGELOG.md under [Unreleased].
#
# Usage:
#   .\scripts\version-bump.ps1 -Kind patch          # 0.1.0 -> 0.1.1
#   .\scripts\version-bump.ps1 -Kind minor          # 0.1.0 -> 0.2.0
#   .\scripts\version-bump.ps1 -Kind major          # 0.1.0 -> 1.0.0
#   .\scripts\version-bump.ps1 -Kind alpha          # 0.1.0-alpha.N -> 0.1.0-alpha.(N+1)
#   .\scripts\version-bump.ps1 -Set 0.1.0           # explicit pin (both files)
#
# Notes:
#   - package.json uses npm semver style:    0.1.0-alpha.1
#   - pyproject.toml uses PEP 440 style:     0.1.0a1
#   The script converts between them.

param(
  [ValidateSet('patch','minor','major','alpha')]
  [string]$Kind = 'alpha',
  [string]$Set
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$packageJsonPath = Join-Path $root 'package.json'
$pyprojectPath   = Join-Path $root 'pyproject.toml'
$changelogPath   = Join-Path $root 'CHANGELOG.md'

function Convert-NpmToPep440([string]$v) {
  # 0.1.0-alpha.3 -> 0.1.0a3
  return ($v -replace '-alpha\.', 'a' -replace '-beta\.', 'b' -replace '-rc\.', 'rc')
}

function Convert-Pep440ToNpm([string]$v) {
  # 0.1.0a3 -> 0.1.0-alpha.3
  if ($v -match '^(\d+\.\d+\.\d+)a(\d+)$')  { return "$($matches[1])-alpha.$($matches[2])" }
  if ($v -match '^(\d+\.\d+\.\d+)b(\d+)$')  { return "$($matches[1])-beta.$($matches[2])"  }
  if ($v -match '^(\d+\.\d+\.\d+)rc(\d+)$') { return "$($matches[1])-rc.$($matches[2])"    }
  return $v
}

$pkg = Get-Content $packageJsonPath -Raw | ConvertFrom-Json
$currentNpm = [string]$pkg.version

if ($Set) {
  $newNpm = $Set
} elseif ($Kind -eq 'alpha') {
  if ($currentNpm -match '^(\d+\.\d+\.\d+)-alpha\.(\d+)$') {
    $newNpm = "$($matches[1])-alpha.$([int]$matches[2] + 1)"
  } else {
    $newNpm = "$currentNpm-alpha.1"
  }
} else {
  $coreOnly = ($currentNpm -split '-')[0]
  $parts = $coreOnly.Split('.') | ForEach-Object { [int]$_ }
  switch ($Kind) {
    'patch' { $parts[2]++ }
    'minor' { $parts[1]++; $parts[2] = 0 }
    'major' { $parts[0]++; $parts[1] = 0; $parts[2] = 0 }
  }
  $newNpm = "$($parts[0]).$($parts[1]).$($parts[2])"
}

$newPep = Convert-NpmToPep440 $newNpm

# Update package.json
$pkg.version = $newNpm
($pkg | ConvertTo-Json -Depth 50) | Set-Content -Path $packageJsonPath -Encoding UTF8

# Update pyproject.toml (only the [project] version line)
$pyContent = Get-Content $pyprojectPath -Raw
$pyContent = [regex]::Replace($pyContent, '(?m)^version = ".*"$', "version = `"$newPep`"")
Set-Content -Path $pyprojectPath -Value $pyContent -Encoding UTF8

# Append CHANGELOG stub
$changelog = Get-Content $changelogPath -Raw
$entry = @"

## [$newNpm] — $(Get-Date -Format 'yyyy-MM-dd')

### Added
- _Describe additions here_

### Fixed
- _Describe fixes here_

"@
$changelog = $changelog -replace '## \[Unreleased\]', "## [Unreleased]`r`n$entry"
Set-Content -Path $changelogPath -Value $changelog -Encoding UTF8

Write-Host "Synapse bumped: $currentNpm  →  $newNpm  (PEP 440: $newPep)"
Write-Host "Updated:"
Write-Host "  - package.json"
Write-Host "  - pyproject.toml"
Write-Host "  - CHANGELOG.md (stub entry under [Unreleased])"
