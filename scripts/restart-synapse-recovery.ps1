param(
  [string]$SynapseRoot = "C:\Users\justi\synapse"
)

$ErrorActionPreference = "Stop"
$dataDir = Join-Path $SynapseRoot "data"
$tokenPath = Join-Path $dataDir "auth-token"

if (-not (Test-Path -LiteralPath $tokenPath)) {
  throw "Synapse auth token not found at $tokenPath"
}

$token = (Get-Content -LiteralPath $tokenPath -Raw).Trim()
if (-not $token) {
  throw "Synapse auth token is empty."
}

$operationId = "recovery-" + (Get-Date -Format "yyyyMMdd-HHmmss")
$headers = @{ "X-Synapse-Token" = $token }
$body = @{
  operation_id = $operationId
  source = "desktop"
} | ConvertTo-Json -Compress

Write-Host "Requesting a clean Synapse restart..." -ForegroundColor Cyan

try {
  $response = Invoke-RestMethod -Uri "http://127.0.0.1:7878/api/v1/system/restart" -Method Post -Headers $headers -ContentType "application/json" -Body $body -TimeoutSec 10
  Write-Host "Restart request accepted: $operationId" -ForegroundColor Green
  Write-Host "Synapse's Electron recovery poller will perform the normal graceful restart."
  $response | ConvertTo-Json -Depth 8
}
catch {
  Write-Host "Restart request failed." -ForegroundColor Red
  Write-Host $_.Exception.Message
  exit 1
}
