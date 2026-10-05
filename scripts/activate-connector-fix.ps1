# Activate the Synapse MCP saturation/deadlock fix safely.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$dataDir = Join-Path $root 'data'
$log = Join-Path $dataDir 'connector-recovery-activation.log'
$resultPath = Join-Path $dataDir 'connector-recovery-result.json'
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

function Log([string]$Message) {
  $line = "{0} [connector-fix] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
  $line | Tee-Object -FilePath $log -Append | Write-Host
}

function Save-Result([bool]$Ok, [string]$Stage, [string]$Detail) {
  @{
    ok = $Ok
    stage = $Stage
    detail = $Detail
    completed_at = (Get-Date).ToUniversalTime().ToString('o')
  } | ConvertTo-Json | Set-Content -Path $resultPath -Encoding UTF8
}

try {
  Log 'Starting preflight; the live daemon has not been touched yet.'
  & python -m py_compile daemon\synapse_daemon\mcp_connector.py daemon\synapse_daemon\routes_system.py daemon\synapse_daemon\app.py scripts\recover_daemon.py
  if ($LASTEXITCODE -ne 0) { throw 'Python compile preflight failed.' }

  foreach ($scriptName in @('daemon-watchdog-v2.ps1', 'daemon-watchdog.ps1')) {
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
      (Join-Path $PSScriptRoot $scriptName), [ref]$tokens, [ref]$errors
    ) | Out-Null
    if ($errors.Count -gt 0) {
      throw "PowerShell parse preflight failed for $scriptName`: $($errors[0].Message)"
    }
  }

  Log 'Running focused regression tests before activation.'
  & python -m pytest daemon\tests\test_mcp_connector.py daemon\tests\test_routes_system.py -q *>&1 | Tee-Object -FilePath $log -Append
  if ($LASTEXITCODE -ne 0) { throw 'Focused regression tests failed; activation cancelled.' }

  Log 'Preflight green. Replacing legacy watchdog and recovering only the Synapse daemon.'
  $recovery = & python scripts\recover_daemon.py --port 7878 --data-dir data --stop-legacy-watchdogs 2>&1
  $recovery | Tee-Object -FilePath $log -Append | Write-Host
  if ($LASTEXITCODE -ne 0) { throw 'Targeted daemon recovery did not release port 7878.' }

  $devScript = Join-Path $PSScriptRoot 'dev.ps1'
  $startArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $devScript, '-DaemonOnly', '-BindLan')
  Start-Process -FilePath 'powershell.exe' -ArgumentList $startArgs -WorkingDirectory $root -WindowStyle Hidden | Out-Null
  Log 'Started patched daemon-only runtime; checking liveness + MCP executor health.'

  $ready = $false
  $deadline = (Get-Date).AddSeconds(90)
  do {
    try {
      $basic = Invoke-RestMethod -TimeoutSec 3 -Uri 'http://127.0.0.1:7878/api/v1/health'
      $mcp = Invoke-RestMethod -TimeoutSec 3 -Uri 'http://127.0.0.1:7878/api/v1/health/mcp'
      if ($basic.ok -and $mcp.ok) { $ready = $true; break }
    } catch {}
    Start-Sleep -Milliseconds 500
  } while ((Get-Date) -lt $deadline)
  if (-not $ready) { throw 'Patched daemon did not become MCP-healthy within 90 seconds.' }

  $token = (Get-Content -Raw -Path (Join-Path $dataDir 'auth-token')).Trim()
  if (-not $token) { throw 'Local Synapse auth token is missing.' }
  $rpcUrl = "http://127.0.0.1:7878/mcp/$token"

  $statusBody = @{
    jsonrpc = '2.0'; id = 1; method = 'tools/call';
    params = @{ name = 'synapse_mcp_executor_status'; arguments = @{} }
  } | ConvertTo-Json -Depth 8 -Compress
  $statusRpc = Invoke-RestMethod -Method Post -TimeoutSec 10 -ContentType 'application/json' -Uri $rpcUrl -Body $statusBody
  if ($statusRpc.result.isError) { throw 'MCP executor status smoke call returned an error.' }

  $commandBody = @{
    jsonrpc = '2.0'; id = 2; method = 'tools/call';
    params = @{
      name = 'synapse_run_command';
      arguments = @{ command = 'echo connector-ok'; timeout_seconds = 10; cwd = $root }
    }
  } | ConvertTo-Json -Depth 8 -Compress
  $commandRpc = Invoke-RestMethod -Method Post -TimeoutSec 20 -ContentType 'application/json' -Uri $rpcUrl -Body $commandBody
  if ($commandRpc.result.isError) { throw 'MCP command-lane smoke call returned an error.' }

  Save-Result $true 'complete' 'Focused tests passed; patched daemon, MCP health route, status tool, and command lane all verified.'
  Log 'SUCCESS: connector fix is active and verified.'
  Write-Host ''
  Write-Host 'Synapse connector fix is ACTIVE and verified.'
} catch {
  $detail = $_.Exception.Message
  Save-Result $false 'failed' $detail
  Log "FAILED: $detail"
  Write-Host ''
  Write-Host "Activation failed safely: $detail"
  exit 1
}
