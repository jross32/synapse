param(
  [ValidateSet('Check','Close')][string]$Action = 'Check',
  [string]$InstallDir = ''
)
# Only target the visible Synapse Electron desktop executable installed
# in the selected Synapse install directory. Never terminate the daemon,
# other applications, or unrelated Synapse development processes.
$ErrorActionPreference='Stop'
if (-not $InstallDir) { exit 3 }
try {
  $installRoot = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
  $target = [IO.Path]::GetFullPath((Join-Path $installRoot 'Synapse.exe'))
  $matches = @(Get-CimInstance Win32_Process -Filter "Name = 'Synapse.exe'" -ErrorAction Stop |
    Where-Object { $_.ExecutablePath -and [string]::Equals(
      [IO.Path]::GetFullPath($_.ExecutablePath), $target,
      [StringComparison]::OrdinalIgnoreCase
    ) })
  if ($Action -eq 'Check') {
    if ($matches.Count -gt 0) { exit 10 }
    exit 0
  }
  foreach ($instance in $matches) {
    try {
      $process = Get-Process -Id $instance.ProcessId -ErrorAction Stop
      [void]$process.CloseMainWindow()
    } catch { }
  }
  for ($attempt=0; $attempt -lt 12; $attempt++) {
    Start-Sleep -Milliseconds 500
    $remaining = @(Get-CimInstance Win32_Process -Filter "Name = 'Synapse.exe'" -ErrorAction SilentlyContinue |
      Where-Object { $_.ExecutablePath -and [string]::Equals($_.ExecutablePath, $target, [StringComparison]::OrdinalIgnoreCase) })
    if ($remaining.Count -eq 0) { exit 0 }
  }
  # Owner agreed in the installer dialog to close the still-running desktop.
  # Revalidate executable path before each force-termination.
  foreach ($instance in $remaining) {
    $live = Get-CimInstance Win32_Process -Filter ("ProcessId = " + $instance.ProcessId) -ErrorAction SilentlyContinue
    if ($live -and [string]::Equals($live.ExecutablePath,$target,[StringComparison]::OrdinalIgnoreCase)) {
      Stop-Process -Id $instance.ProcessId -Force -ErrorAction Stop
    }
  }
  Start-Sleep -Seconds 2
  $still = @(Get-CimInstance Win32_Process -Filter "Name = 'Synapse.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -and [string]::Equals($_.ExecutablePath,$target,[StringComparison]::OrdinalIgnoreCase) })
  if ($still.Count -gt 0) { exit 10 }
  exit 0
} catch { exit 3 }
