# Reproducible unsigned NSIS diagnostic installer build.
# Uses a unique output directory; never removes existing user files or releases.
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo
$receipt = Join-Path $repo "installer\build-windows-dev.result"
$stdout = Join-Path $repo "installer\build-windows-dev.log"
$stderr = Join-Path $repo "installer\build-windows-dev.err.log"
$output = Join-Path $repo "release-branded-unsigned-v2"
Remove-Item $receipt,$stdout,$stderr -ErrorAction SilentlyContinue

try {
  if (Test-Path $output) { throw "Isolated output already exists; choose a new directory rather than deleting other builds." }
  if (!(Test-Path "dist\index.html")) { throw "Renderer build is missing." }
  if (!(Test-Path "dist-electron\main.js")) { throw "Electron build is missing." }
  if (!(Test-Path "installer\daemon-dist\synapse-daemon.exe")) { throw "Bundled daemon is missing." }
  if ((Get-PSDrive C).Free -lt 2GB) { throw "Fewer than 2 GiB free on C:; packaging could fill disk." }

  # ASAR disabled for diagnostics only, to isolate prior app.asar ENOENT.
  # Production packaging, signing, and updates need separate proof.
  $args = "/c node_modules\.bin\electron-builder.cmd --win nsis --publish never --config.directories.output=release-branded-unsigned-v2 --config.asar=false --config.win.signAndEditExecutable=false"
  $build = Start-Process -FilePath "cmd.exe" -ArgumentList $args -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -Wait
  if ($build.ExitCode -ne 0) { throw "Electron Builder exited $($build.ExitCode)." }

  $setup = Get-ChildItem $output -File -Filter "*.exe" | Where-Object { $_.Name -like "*Setup*" } | Select-Object -First 1
  if (!$setup) { throw "Electron Builder returned 0 but no NSIS setup executable appeared." }
  $hash = (Get-FileHash -LiteralPath $setup.FullName -Algorithm SHA256).Hash
  if ($setup.Length -lt 1MB) { throw "Installer unexpectedly small." }
  $lines = @("PASS", "File=$($setup.FullName)", "Bytes=$($setup.Length)", "SHA256=$hash")
  $lines | Set-Content -Encoding Ascii $receipt
} catch {
  "FAIL $($_.Exception.Message)" | Set-Content -Encoding Ascii $receipt
  exit 1
}
