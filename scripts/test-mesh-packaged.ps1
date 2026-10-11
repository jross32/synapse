param(
  [Parameter(Mandatory=$true)][string]$Executable,
  [int]$StartupSeconds = 40
)
$ErrorActionPreference = 'Stop'
$exe = (Resolve-Path $Executable).Path
if (-not ($exe.EndsWith('synapse-daemon.exe', [System.StringComparison]::OrdinalIgnoreCase))) { throw 'Expected Synapse daemon executable' }
$smokeRoot = Join-Path $env:TEMP ('synapse-mesh-smoke-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force $smokeRoot | Out-Null
$dataDir = Join-Path $smokeRoot 'data'
New-Item -ItemType Directory $dataDir | Out-Null
$listener = [System.Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0)
$listener.Start()
$port = ([Net.IPEndPoint]$listener.LocalEndpoint).Port
$listener.Stop()
$stdout = Join-Path $smokeRoot 'stdout.log'
$stderr = Join-Path $smokeRoot 'stderr.log'
$started = $null
$success = $false
try {
  $started = Start-Process -FilePath $exe -ArgumentList @('--port',"$port",'--data-dir',$dataDir,'--log-level','warning') -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
  $url = "http://127.0.0.1:$port/api/v1"
  for ($i=0; $i -lt $StartupSeconds; $i++) {
    Start-Sleep -Seconds 1
    try { $health = Invoke-RestMethod "$url/health" -TimeoutSec 2; if ($health.ok) { break } } catch {}
    if (-not (Get-Process -Id $started.Id -ErrorAction SilentlyContinue)) { throw 'Packaged daemon exited before healthy' }
  }
  if (-not $health.ok) { throw 'Packaged daemon failed health check' }
  $tokenFile = Join-Path $dataDir 'auth-token'
  if (-not (Test-Path $tokenFile)) { throw 'Packaged daemon did not create local auth token' }
  $token = (Get-Content $tokenFile -Raw).Trim()
  $headers = @{ 'X-Synapse-Token' = $token }
  $inventory = Invoke-RestMethod "$url/machines/local/inventory" -Headers $headers -TimeoutSec 10
  if (-not $inventory.inventory.hostname) { throw 'Machine inventory missing hostname' }
  $profile = Invoke-RestMethod "$url/profile" -Headers $headers -TimeoutSec 10
  Write-Output "PACKAGED_SMOKE_PASS version=$($health.version) host=$($inventory.inventory.hostname) port=$port signed_in=$($profile.signed_in)"
  $success = $true
}
finally {
  # PyInstaller onefile spawns a child with the same executable. Limit cleanup
  # to the exact executable and the unique test-only data directory.
  $matches = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'synapse-daemon.exe' -and
    $_.ExecutablePath -ieq $exe -and
    $_.CommandLine -like "*$dataDir*"
  })
  foreach ($process in $matches) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
  }
  if ($started) { Stop-Process -Id $started.Id -Force -ErrorAction SilentlyContinue }
  Write-Output "CLEANUP_MATCHED=$($matches.Count)"
  Write-Output "SMOKE_LOGS=$smokeRoot"
}
if (-not $success) { exit 1 }
