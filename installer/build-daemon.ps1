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
# Prefer an explicitly selected build interpreter; otherwise choose one with PyInstaller.
# Validate by running PyInstaller itself, rather than relying on the default PATH Python.
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$candidates = @()
if ($env:SYNAPSE_BUILD_PYTHON) { $candidates += $env:SYNAPSE_BUILD_PYTHON }
if (Test-Path $venvPython) { $candidates += $venvPython }
foreach ($version in @('Python312','Python313','Python311')) {
  $installed = Join-Path $env:USERPROFILE "AppData\Local\Programs\Python\$version\python.exe"
  if (Test-Path $installed) { $candidates += $installed }
}
foreach ($command in @(Get-Command python -All -ErrorAction SilentlyContinue)) { $candidates += $command.Source }
$pythonExe = $null
foreach ($candidate in ($candidates | Select-Object -Unique)) {
  if (-not (Test-Path $candidate)) { continue }
  try {
    $versionOutput = & $candidate -m PyInstaller --version 2>&1
    if ($LASTEXITCODE -eq 0) { $pythonExe = $candidate; break }
  } catch { continue }
}
if (-not $pythonExe) { throw 'PyInstaller is unavailable. Set SYNAPSE_BUILD_PYTHON to an interpreter with PyInstaller installed.' }
Write-Host "-> Using Python with PyInstaller: $pythonExe"

Remove-Item -LiteralPath $distDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $specFile -Force -ErrorAction SilentlyContinue

Write-Host "-> Building bundled daemon executable"
# --collect-all synapse_daemon bundles the numbered .sql migrations (loaded via
# importlib.resources) -- without it the frozen daemon can't migrate a fresh DB.
# uvicorn loads its protocol/loop impls dynamically, so PyInstaller can't see
# them statically; collect + hidden-import them or the server won't start.
& $pythonExe -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name synapse-daemon `
  --distpath $distDir `
  --workpath $workDir `
  --specpath $specDir `
  --paths $pythonPath `
  --collect-all synapse_daemon `
  --collect-submodules uvicorn `
  --collect-data uvicorn `
  --hidden-import uvicorn.protocols.http.h11_impl `
  --hidden-import uvicorn.protocols.websockets.websockets_impl `
  --hidden-import uvicorn.lifespan.on `
  --hidden-import uvicorn.loops.asyncio `
  --hidden-import anyio._backends._asyncio `
  $entrypoint

if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller build failed with exit code $LASTEXITCODE."
}

Write-Host "-> Bundled daemon ready at $distDir"
