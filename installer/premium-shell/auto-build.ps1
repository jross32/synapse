param([switch]$AllowDirty,[switch]$SkipDaemon,[switch]$DryRun)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$lockPath=Join-Path $root 'release-premium-shell\.auto-build.lock'
$reportPath=Join-Path $root 'release-premium-shell\auto-build-result.json'
New-Item -ItemType Directory -Force (Split-Path $lockPath) | Out-Null
$lock=$null
try {
  $lock=[System.IO.File]::Open($lockPath,[System.IO.FileMode]::OpenOrCreate,[System.IO.FileAccess]::ReadWrite,[System.IO.FileShare]::None)
} catch { throw 'Another Synapse release build is already running. Wait for it to finish.' }
$start=(Get-Date).ToUniversalTime().ToString('o')
$report=[ordered]@{started_at=$start;status='running';version=$null;commit=$null;dirty=$null;steps=@();artifact=$null;sha256=$null;error=$null;production_approved=$false}
function Save-Report { [System.IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 10)) }
function Invoke-Step([string]$name,[scriptblock]$action) {
  Write-Host "[Synapse auto-build] $name"
  & $action
  if ($LASTEXITCODE -ne 0) { throw "$name failed with exit code $LASTEXITCODE" }
  $report.steps+=@{name=$name;status='passed'};Save-Report
}
try {
  Set-Location $root
  $report.commit=(& git rev-parse HEAD).Trim()
  $changes=@(& git status --porcelain --untracked-files=normal)
  $report.dirty=($changes.Count -gt 0)
  $report.version=(& node -p "require('./package.json').version").Trim()
  $lockVersion=(& node -p "require('./package-lock.json').version").Trim()
  if ($report.version -ne $lockVersion) { throw 'Root package.json and package-lock.json versions differ.' }
  if ($report.version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid package version.' }
  if ($report.dirty -and -not $AllowDirty) { throw 'Working tree is dirty. Preserve concurrent agent edits; use -AllowDirty only for a nonproduction candidate.' }
  Save-Report
  if ($DryRun) { $report.status='dry-run-passed';return }
  Invoke-Step 'Typecheck' { npm run typecheck }
  Invoke-Step 'Build UI and Electron' { npm run build }
  if (-not $SkipDaemon) { Invoke-Step 'Build daemon' { npm run build:daemon } }
  if (-not (Test-Path 'installer/daemon-dist/synapse-daemon.exe')) { throw 'Daemon executable missing.' }
  Invoke-Step 'Package native NSIS' { npx electron-builder --win nsis --publish never --config.win.signAndEditExecutable=false }
  $v=$report.version
  $payload=Join-Path $root "release\Synapse Setup $v.exe"
  if (-not (Test-Path $payload)) { throw 'New NSIS payload missing.' }
  $target=Join-Path $PSScriptRoot "payload\Synapse Setup $v.exe"
  New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
  Copy-Item $payload $target -Force
  $hash=(Get-FileHash $target -Algorithm SHA256).Hash.ToLowerInvariant()
  $manifest=[ordered]@{filename="Synapse Setup $v.exe";version=$v;sha256=$hash}|ConvertTo-Json
  [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'payload-manifest.json'),$manifest)
  $pkgPath=Join-Path $PSScriptRoot 'package.json'
  $pkg=Get-Content $pkgPath -Raw|ConvertFrom-Json
  $pkg.version=$v
  $pkg.build.extraResources=@([pscustomobject]@{from="payload/Synapse Setup $v.exe";to="synapse-payload/Synapse Setup $v.exe"})
  [System.IO.File]::WriteAllText($pkgPath,($pkg|ConvertTo-Json -Depth 40))
  Push-Location $PSScriptRoot
  try { Invoke-Step 'Bundle premium installer' { npx electron-builder --win portable --publish never } }
  finally { Pop-Location }
  Invoke-Step 'Packaging gate' { node installer/premium-shell/release-gate.cjs }
  Invoke-Step 'Native failure-state gate' { node installer/premium-shell/test-native-gate.cjs }
  Invoke-Step 'Eight-screen UI gate' { node installer/premium-shell/test-chatgpt.cjs }
  Invoke-Step 'Responsive UI gate' { node installer/premium-shell/scripts/responsive-proof.cjs }
  $artifact=Join-Path $root "release-premium-shell\Synapse Premium Setup $v.exe"
  if (-not (Test-Path $artifact)) { throw 'Premium installer missing after build.' }
  $report.artifact=$artifact
  $report.sha256=(Get-FileHash $artifact -Algorithm SHA256).Hash.ToLowerInvariant()
  $report.status='candidate-built'
  Write-Warning 'Candidate only: signing, clean-install, upgrade and account/device E2E are required before production release.'
} catch {
  $report.status='blocked';$report.error=$_.Exception.Message
  Write-Error $report.error -ErrorAction Continue
  exit 1
} finally {
  $report.finished_at=(Get-Date).ToUniversalTime().ToString('o')
  Save-Report
  if ($lock) { $lock.Dispose() }
}
