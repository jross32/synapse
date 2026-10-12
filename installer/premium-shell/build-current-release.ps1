param([string]$Version,[switch]$SkipDaemon)
$ErrorActionPreference='Stop'
$root=Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $root
if (-not $Version) { $Version=(Get-Content package.json -Raw|ConvertFrom-Json).version }
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Version must be semver major.minor.patch' }
$app=(Get-Content package.json -Raw|ConvertFrom-Json)
if ($app.version -ne $Version) { throw "Root package version $($app.version) differs from requested $Version; synchronize version and lockfile before building." }
$lockVersion=(& node -p "require('./package-lock.json').version")
if ($lockVersion -ne $Version) { throw 'package-lock version does not match package.json' }
Write-Host 'Typechecking Synapse source...'
& npm run typecheck; if ($LASTEXITCODE -ne 0) { throw 'Typecheck failed' }
Write-Host 'Building Synapse UI and Electron...'
& npm run build; if ($LASTEXITCODE -ne 0) { throw 'Source build failed' }
if (-not $SkipDaemon) { Write-Host 'Building daemon...'; & npm run build:daemon; if ($LASTEXITCODE -ne 0) { throw 'Daemon build failed' } }
if (-not (Test-Path installer/daemon-dist/synapse-daemon.exe)) { throw 'Packaged daemon missing' }
Write-Host 'Building native NSIS installer...'
& npx electron-builder --win nsis --publish never --config.win.signAndEditExecutable=false; if ($LASTEXITCODE -ne 0) { throw 'NSIS build failed' }
$payload=Join-Path $root "release\Synapse Setup $Version.exe"
if (-not (Test-Path $payload)) { throw "NSIS payload not found: $payload" }
$target=Join-Path $PSScriptRoot "payload\Synapse Setup $Version.exe"
New-Item -ItemType Directory -Force (Split-Path $target)|Out-Null
Copy-Item $payload $target -Force
$sha=(Get-FileHash $target -Algorithm SHA256).Hash.ToLowerInvariant()
$manifest=@{filename="Synapse Setup $Version.exe";version=$Version;sha256=$sha}|ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'payload-manifest.json'),$manifest)
$pkgPath=Join-Path $PSScriptRoot 'package.json'
$pkg=Get-Content $pkgPath -Raw|ConvertFrom-Json
$pkg.version=$Version
$pkg.build.extraResources=@([pscustomobject]@{from="payload/Synapse Setup $Version.exe";to="synapse-payload/Synapse Setup $Version.exe"})
[System.IO.File]::WriteAllText($pkgPath,($pkg|ConvertTo-Json -Depth 40))
Push-Location $PSScriptRoot
try { & npx electron-builder --win portable --publish never; if ($LASTEXITCODE -ne 0) { throw 'Premium wrapper build failed' } }
finally { Pop-Location }
& node installer/premium-shell/release-gate.cjs; if ($LASTEXITCODE -ne 0) { throw 'Premium packaging gate failed' }
Write-Host "PREMIUM CANDIDATE BUILT: release-premium-shell\Synapse Premium Setup $Version.exe"
Write-Warning 'Not production approved until clean-install, upgrade, daemon/account E2E, and signing are verified.'
