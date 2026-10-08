# Compatibility wrapper. The connector-aware implementation lives in daemon-watchdog-v2.ps1.
param(
  [int]$Port = 7878,
  [string]$DataDir = 'data',
  [switch]$BindLan,
  [int]$IntervalSeconds = 30,
  [int]$FailureThreshold = 3,
  [int]$HealthTimeoutSeconds = 5,
  [int]$McpFailureThreshold = 6,
  [int]$McpHealthTimeoutSeconds = 5,
  [int]$LowDiskFreeMB = 512,
  [int]$GraceSeconds = 120
)
$impl = Join-Path $PSScriptRoot 'daemon-watchdog-v2.ps1'
$argsList = @(
  '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $impl,
  '-Port', "$Port", '-DataDir', $DataDir,
  '-IntervalSeconds', "$IntervalSeconds",
  '-FailureThreshold', "$FailureThreshold",
  '-HealthTimeoutSeconds', "$HealthTimeoutSeconds",
  '-McpFailureThreshold', "$McpFailureThreshold",
  '-McpHealthTimeoutSeconds', "$McpHealthTimeoutSeconds",
  '-LowDiskFreeMB', "$LowDiskFreeMB",
  '-GraceSeconds', "$GraceSeconds"
)
if ($BindLan) { $argsList += '-BindLan' }
& powershell.exe @argsList
exit $LASTEXITCODE
