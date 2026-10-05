# Compatibility launcher for the event-driven Synapse Terminal Cloak.
# The actual guard lives in terminal_cloak.py and runs under pythonw.exe so it
# does not create a console host. This wrapper remains for older callers that
# still reference terminal-cloak.ps1.

param(
  [int]$PollMilliseconds = 75
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $pythonw)) {
  $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
  if ($python) {
    $pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
  }
}
if (-not $pythonw -or -not (Test-Path $pythonw)) {
  throw 'pythonw.exe could not be resolved for Synapse Terminal Cloak.'
}

$script = Join-Path $PSScriptRoot 'terminal_cloak.py'
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $pythonw
$startInfo.Arguments = '"' + $script + '" --poll-ms ' + [Math]::Max(50, [Math]::Min(1000, $PollMilliseconds))
$startInfo.WorkingDirectory = $root
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

$proc = [System.Diagnostics.Process]::Start($startInfo)
if (-not $proc) {
  throw 'Failed to start Synapse Terminal Cloak.'
}
$proc.WaitForExit()
exit $proc.ExitCode
