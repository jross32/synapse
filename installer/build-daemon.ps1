# Synapse packaged-daemon build helper.
#
# Builds a self-contained Windows executable for the Python daemon so
# electron-builder can ship it under resources/daemon/.

param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$distDir = Join-Path $root 'installer\daemon-dist'
$workDir = Join-Path $root 'installer\build-temp'
$specDir = Join-Path $root 'installer'
$specFile = Join-Path $specDir 'synapse-daemon.spec'
$entrypoint = Join-Path $root 'daemon\packaged_daemon_main.py'
$pythonPath = Join-Path $root 'daemon'

Remove-Item -LiteralPath $distDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $specFile -Force -ErrorAction SilentlyContinue

Write-Host "-> Building bundled daemon executable"
& python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name synapse-daemon `
  --distpath $distDir `
  --workpath $workDir `
  --specpath $specDir `
  --paths $pythonPath `
  $entrypoint

if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller build failed with exit code $LASTEXITCODE."
}

Write-Host "-> Bundled daemon ready at $distDir"
