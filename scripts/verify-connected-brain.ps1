# Connected Brain implementation checks. Writes a durable completion receipt.
# Run from the repo root. -From renderer skips already completed TypeScript gates.
param([ValidateSet("all", "renderer", "backend")][string]$From = "all")

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo
$log = Join-Path $repo "installer\connected-brain-verification.log"
$receipt = Join-Path $repo "installer\connected-brain-verification.result"
Remove-Item $receipt -ErrorAction SilentlyContinue
"Connected Brain verification starting at $From $(Get-Date -Format o)" | Add-Content -Encoding UTF8 $log

function Invoke-Checked {
  param([string]$Label, [scriptblock]$Command)
  "BEGIN $Label $(Get-Date -Format o)" | Add-Content -Encoding UTF8 $log
  # Windows PowerShell promotes redirected native stderr into ErrorRecords when
  # ErrorActionPreference=Stop. Vite prints a known nonfatal CJS warning to
  # stderr, so check the *process exit code* rather than treating any stderr as
  # a failed build.
  $before = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & $Command *>> $log
    $code = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $before
  }
  if ($code -ne 0) { throw "$Label failed: exit code $code" }
  "PASS $Label $(Get-Date -Format o)" | Add-Content -Encoding UTF8 $log
}

try {
  if ($From -eq "all") {
    Invoke-Checked "Python syntax" {
      & .\.venv\Scripts\python.exe -m py_compile daemon\synapse_daemon\release_manifest.py daemon\synapse_daemon\routes_about.py daemon\tests\test_release_manifest.py
    }
    Invoke-Checked "Frontend TypeScript" { & .\node_modules\.bin\tsc.cmd --noEmit -p tsconfig.json }
    Invoke-Checked "Electron TypeScript" { & .\node_modules\.bin\tsc.cmd --noEmit -p electron\tsconfig.json }
  }
  if ($From -ne "backend") {
    Invoke-Checked "Renderer production build" { & npm.cmd run build:renderer }
  }
  Invoke-Checked "Release route tests" { & .\.venv\Scripts\python.exe -m pytest daemon\tests\test_release_manifest.py -q }
  Invoke-Checked "Machine API tests" { & .\.venv\Scripts\python.exe -m pytest daemon\tests\test_machine_routes.py -q }
  Invoke-Checked "Machine identity tests" { & .\.venv\Scripts\python.exe -m pytest daemon\tests\test_machine_fleet.py -q }
  "PASS $From" | Set-Content -Encoding Ascii $receipt
} catch {
  "FAIL $_" | Add-Content -Encoding UTF8 $log
  "FAIL $_" | Set-Content -Encoding Ascii $receipt
  exit 1
}
