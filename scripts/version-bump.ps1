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

# -- explicit-encoding file IO ------------------------------------------------
#
# Both directions must name the encoding, because Windows PowerShell 5.1 and
# PowerShell 7 disagree about the default and this script rewrites whole files.
#
# Reading: 5.1's Get-Content decodes a BOM-less file as Windows-1252, so every
# non-ASCII character came back as mojibake and was re-encoded as UTF-8 on write.
# Since each bump rewrites the ENTIRE changelog, that compounded ~2.2x per release:
# 220 KB at 0.1.95, 90 MB by 0.1.108, 201 MB by 0.1.109 -- at which point GitHub
# refused the push for exceeding its 100 MB file limit.
#
# Writing: `Set-Content -Encoding UTF8` means "with BOM" on 5.1 and "without" on 7+,
# which previously prepended EF BB BF and crashed scripts/docs_sync_check.py.
function Read-Utf8 {
  param([Parameter(Mandatory = $true)][string]$Path)
  [System.IO.File]::ReadAllText($Path, [System.Text.UTF8Encoding]::new($false))
}

function Write-Utf8NoBom {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value
  )
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  # The trailing newline replicates what Set-Content appended, so diffs stay clean.
  [System.IO.File]::WriteAllText($Path, $Value + [Environment]::NewLine, $utf8NoBom)
}

$pkg = Read-Utf8 $packageJsonPath | ConvertFrom-Json
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
Write-Utf8NoBom -Path $packageJsonPath -Value ($pkg | ConvertTo-Json -Depth 50)

# Update pyproject.toml (only the [project] version line)
$pyContent = Read-Utf8 $pyprojectPath
$pyContent = [regex]::Replace($pyContent, '(?m)^version = "[^"\r\n]*"', "version = `"$newVersion`"")
Write-Utf8NoBom -Path $pyprojectPath -Value $pyContent

# Update __version__ in the package __init__.py (Contract #8: single source of truth).
$initPath = Join-Path $root 'daemon\synapse_daemon\__init__.py'
$initContent = Read-Utf8 $initPath
$initContent = [regex]::Replace($initContent, '(?m)^__version__ = "[^"\r\n]*"', "__version__ = `"$newVersion`"")
Write-Utf8NoBom -Path $initPath -Value $initContent

# Append CHANGELOG stub
$changelog = Read-Utf8 $changelogPath
$entry = @"

## [$newVersion] -- $(Get-Date -Format 'yyyy-MM-dd')

### Added
- _Describe additions here_

### Fixed
- _Describe fixes here_

"@
$changelog = $changelog -replace '## \[Unreleased\]', "## [Unreleased]`r`n$entry"
Write-Utf8NoBom -Path $changelogPath -Value $changelog

# Refuse to report success if Windows line endings or a future format change caused
# one version source to miss the rewrite. This caught a real CRLF bug where only
# package.json changed while the daemon still reported the previous version.
$verifyPkg = [string](Read-Utf8 $packageJsonPath | ConvertFrom-Json).version
$verifyPy = [regex]::Match((Read-Utf8 $pyprojectPath), '(?m)^version = "([^"\r\n]+)"').Groups[1].Value
$verifyInit = [regex]::Match((Read-Utf8 $initPath), '(?m)^__version__ = "([^"\r\n]+)"').Groups[1].Value
if ($verifyPkg -ne $newVersion -or $verifyPy -ne $newVersion -or $verifyInit -ne $newVersion) {
  throw "Version bump verification failed: package=$verifyPkg pyproject=$verifyPy daemon=$verifyInit expected=$newVersion"
}

Write-Host "Synapse bumped: $currentVersion  ->  $newVersion  (kind: $Kind)"
Write-Host "Updated:"
Write-Host "  - package.json"
Write-Host "  - pyproject.toml"
Write-Host "  - daemon/synapse_daemon/__init__.py"
Write-Host "  - CHANGELOG.md (stub entry under [Unreleased])"
