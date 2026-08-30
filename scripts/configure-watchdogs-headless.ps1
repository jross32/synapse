# Configure the known Synapse/Stock Hunter watchdog tasks to run without
# visible console windows while preserving their existing triggers/principals.
#
# Safe to re-run. Missing tasks are skipped. By default, running tasks keep
# their current instance until the next natural restart/logon. Pass
# -RestartRunning to migrate long-running tasks immediately.

param(
  [switch]$RestartRunning
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Resolve-Pythonw {
  param([string]$PythonExe)

  if (-not (Test-Path $PythonExe)) {
    return $null
  }
  $pythonw = Join-Path (Split-Path -Parent $PythonExe) 'pythonw.exe'
  if (Test-Path $pythonw) {
    return $pythonw
  }
  return $null
}

function Set-HeadlessTask {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$Execute,
    [Parameter(Mandatory = $true)][string]$Arguments,
    [string]$WorkingDirectory = '',
    [switch]$RestartIfRunning
  )

  $task = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
  if (-not $task) {
    Write-Host "skip: $Name (not installed)"
    return
  }
  if (-not (Test-Path $Execute)) {
    Write-Warning "skip: $Name (missing executable: $Execute)"
    return
  }

  $wasRunning = [string]$task.State -eq 'Running'
  $actionArgs = @{
    Execute = $Execute
    Argument = $Arguments
  }
  if ($WorkingDirectory) {
    $actionArgs.WorkingDirectory = $WorkingDirectory
  }
  $action = New-ScheduledTaskAction @actionArgs

  $settings = $task.Settings
  $settings.Hidden = $true
  Set-ScheduledTask -TaskName $Name -Action $action -Settings $settings | Out-Null
  Write-Host "headless: $Name -> $Execute $Arguments"

  if ($RestartRunning -and $RestartIfRunning -and $wasRunning) {
    Stop-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 750
    Start-ScheduledTask -TaskName $Name
    Write-Host "restarted: $Name"
  }
}

$systemPython = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
$systemPythonw = if ($systemPython) { Resolve-Pythonw $systemPython } else { $null }
if (-not $systemPythonw) {
  throw 'pythonw.exe could not be resolved from the current Python installation.'
}

$stockRoot = Join-Path $env:USERPROFILE 'stock-hunter'
$stockPython = Join-Path $stockRoot '.venv\Scripts\python.exe'
$stockPythonw = Resolve-Pythonw $stockPython

Set-HeadlessTask -Name 'Synapse AI Supervisor' -Execute $systemPythonw -Arguments ('"' + (Join-Path $root 'data\ai-supervisor\supervisor.py') + '"') -RestartIfRunning

Set-HeadlessTask -Name 'Synapse Live Monitor' -Execute $systemPythonw -Arguments ('"' + (Join-Path $root 'scripts\live-monitor-headless.py') + '"') -RestartIfRunning

Set-HeadlessTask -Name 'Synapse Repair Watchdog' -Execute $systemPythonw -Arguments ('"' + (Join-Path $root 'data\system-watchdog\repair_watchdog.py') + '"')

if ($stockPythonw) {
  Set-HeadlessTask -Name 'StockHunterSupervisor' -Execute $stockPythonw -Arguments '-m stock_hunter.runtime_supervisor serve' -WorkingDirectory $stockRoot -RestartIfRunning

  Set-HeadlessTask -Name 'StockHunterSupervisorWatchdog' -Execute $stockPythonw -Arguments '-m stock_hunter.runtime_supervisor ensure' -WorkingDirectory $stockRoot

  Set-HeadlessTask -Name 'StockHunterDailyCampaign' -Execute $stockPythonw -Arguments '-m stock_hunter.research_campaign run' -WorkingDirectory $stockRoot
} else {
  Write-Warning 'Stock Hunter pythonw.exe was not found; Stock Hunter tasks were left unchanged.'
}
