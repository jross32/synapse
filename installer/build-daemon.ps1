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
$venvPython = Join-Path $root '.venv\\Scripts\\python.exe'
$pythonExe = if (Test-Path $venvPython) { $venvPython } else { 'python' }

Remove-Item -LiteralPath $distDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $specFile -Force -ErrorAction SilentlyContinue

# Pin Python imports to this release tree even when the venv is an editable shared install.
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = $pythonPath
& $pythonExe -c "import pathlib,synapse_daemon; actual=pathlib.Path(synapse_daemon.__file__).resolve(); expected=pathlib.Path(r'$pythonPath').resolve(); assert actual.is_relative_to(expected), str(actual); print('Building daemon source:',actual)"
if ($LASTEXITCODE -ne 0) { throw 'Python resolved a different source tree.' }
# WinPTY requires a native helper executable at <PyInstaller extract>/winpty/winpty-agent.exe.
# PyInstaller does not reliably discover this .exe from the Python import alone.
$winptyAgentPath = & $pythonExe -c "import pathlib,winpty; p=pathlib.Path(winpty.__file__).resolve().parent / 'winpty-agent.exe'; assert p.is_file(), 'winpty-agent.exe missing from Python environment'; print(p)"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $winptyAgentPath)) {
  throw 'The Windows worker PTY helper is missing; refusing to build an agent-broken installer.'
}
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
  --add-binary "$winptyAgentPath;winpty" `
  --collect-submodules uvicorn `
  --collect-data uvicorn `
  --hidden-import uvicorn.protocols.http.h11_impl `
  --hidden-import uvicorn.protocols.websockets.websockets_impl `
  --hidden-import uvicorn.lifespan.on `
  --hidden-import uvicorn.loops.asyncio `
  --hidden-import anyio._backends._asyncio `
  $entrypoint

$daemonBuildExitCode = $LASTEXITCODE
$env:PYTHONPATH = $previousPythonPath
if ($daemonBuildExitCode -ne 0) {
  throw "PyInstaller build failed with exit code $LASTEXITCODE."
}

# Verify the built ONEFILE archive, not only the build inputs.
& $pythonExe -c "import pathlib,sys; from PyInstaller.archive.readers import CArchiveReader; names=CArchiveReader(sys.argv[1]).toc; assert any(str(n).replace(chr(92),'/').lower().endswith('winpty/winpty-agent.exe') for n in names), 'winpty helper missing from frozen daemon'; print('PASS bundled WinPTY agent present')" (Join-Path $distDir 'synapse-daemon.exe')
if ($LASTEXITCODE -ne 0) { throw 'Bundled daemon missing WinPTY worker helper' }
Write-Host "-> Bundled daemon ready at $distDir"
