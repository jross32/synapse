param(
  [string]$InstallDir = '',
  [string]$ReportDir = '',
  [switch]$Repair,
  [switch]$SkipNetwork
)
# Safe post-install diagnostics. Never erase, migrate, rewrite, or unlock the
# project database; never kill processes or change firewall/proxy settings.
$ErrorActionPreference = 'Continue'
if (-not $InstallDir) { $InstallDir = Split-Path -Parent $PSScriptRoot }
if (-not $ReportDir) { $ReportDir = Join-Path $env:LOCALAPPDATA 'Synapse\repair-reports' }
New-Item -Path $ReportDir -ItemType Directory -Force -ErrorAction Stop | Out-Null
$ReportPath = Join-Path $ReportDir ("repair-{0}.json" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
$items = New-Object System.Collections.Generic.List[object]
function Add-Check([string]$name, [string]$status, [string]$detail) {
  $items.Add([pscustomobject]@{name=$name;status=$status;detail=$detail})
}
function Check-File([string]$name,[string]$relative,[long]$minBytes) {
  $path = Join-Path $InstallDir $relative
  try {
    $item = Get-Item -LiteralPath $path -ErrorAction Stop
    if (-not $item.PSIsContainer -and $item.Length -ge $minBytes) {
      Add-Check $name 'pass' 'Present and nonempty'
    } else {
      Add-Check $name 'fail' 'Missing required size or wrong file type; rerun installer'
    }
  } catch { Add-Check $name 'fail' 'Missing; rerun installer to restore' }
}
Check-File 'Desktop executable' 'Synapse.exe' 10000000
Check-File 'Bundled daemon' 'resources\daemon\synapse-daemon.exe' 10000000
Check-File 'Electron package' 'resources\app\package.json' 100
Check-File 'Electron UI bundle' 'resources\app\dist\index.html' 100
try {
  $package = Get-Content (Join-Path $InstallDir 'resources\app\package.json') -Raw -ErrorAction Stop | ConvertFrom-Json
  if ($package.version -match '^\d+\.\d+\.\d+$') {Add-Check 'Installed version' 'pass' $package.version}
  else {Add-Check 'Installed version' 'warn' 'Application version could not be verified'}
} catch { Add-Check 'Installed version' 'warn' 'Application package metadata unavailable' }

try {
  $drive = (Get-Item -LiteralPath $InstallDir -ErrorAction Stop).PSDrive
  if (-not $drive -or $null -eq $drive.Free) { Add-Check 'Free disk space' 'warn' 'Drive usage unavailable' }
  elseif ($drive.Free -lt 536870912) { Add-Check 'Free disk space' 'warn' 'Less than 512 MB free; make space before updating' }
  else { Add-Check 'Free disk space' 'pass' ('{0:N1} GB free' -f ($drive.Free / 1GB)) }
} catch { Add-Check 'Free disk space' 'warn' 'Could not read available disk space' }

foreach ($folder in @((Join-Path $env:APPDATA 'Synapse'),(Join-Path $env:LOCALAPPDATA 'Synapse'))) {
  try {
    if (-not (Test-Path -LiteralPath $folder -PathType Container)) {
      if ($Repair) {
        New-Item -Path $folder -ItemType Directory -Force -ErrorAction Stop | Out-Null
        Add-Check 'App folder' 'fixed' 'Created missing Synapse application directory'
      } else { Add-Check 'App folder' 'warn' 'Missing application directory; repair can create it' }
    } else { Add-Check 'App folder' 'pass' 'User application directory available' }
  } catch { Add-Check 'App folder' 'warn' 'Application data directory is not writable' }
}

# No connection health check may require sign-in or expose tokens in a report.
if (-not $SkipNetwork) {
  try {
    $web = Invoke-WebRequest -UseBasicParsing -Uri 'https://accounts-api-production-f84a.up.railway.app/v1/health' -TimeoutSec 8 -ErrorAction Stop
    if ($web.StatusCode -eq 200) { Add-Check 'Cloud account HTTPS' 'pass' 'Synapse account service reachable' }
    else { Add-Check 'Cloud account HTTPS' 'warn' ('Unexpected HTTP status ' + $web.StatusCode) }
  } catch {
    Add-Check 'Cloud account HTTPS' 'warn' 'Account service unreachable from this PC. Check browser, VPN, DNS, proxy and firewall. Do not reset credentials.'
  }
  try {
    $hostName='accounts-api-production-f84a.up.railway.app'
    $null=[System.Net.Dns]::GetHostAddresses($hostName)
    Add-Check 'Account DNS' 'pass' 'DNS resolved'
  } catch { Add-Check 'Account DNS' 'warn' 'DNS resolution failed; check network DNS settings' }
}
try {
  $connection = New-Object System.Net.Sockets.TcpClient
  try {
    $task=$connection.ConnectAsync('127.0.0.1',7878)
    if ($task.Wait(750) -and $connection.Connected) {
      try {
        $response=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:7878/api/v1/health' -TimeoutSec 3 -ErrorAction Stop
        $body=$response.Content|ConvertFrom-Json
        if ($body.version -and $package.version -and $body.version -ne $package.version) {
          Add-Check 'Background daemon version' 'warn' ('An older Synapse daemon is running ('+$body.version+'). Close old dev sessions and restart Synapse safely.')
        } else {Add-Check 'Background daemon version' 'pass' 'Synapse daemon responds to health checks'}
      } catch { Add-Check 'Local port 7878' 'warn' 'Another process may occupy the Synapse port. Installer will not terminate it.' }
    } else { Add-Check 'Local port 7878' 'pass' 'Port not occupied; Synapse can start its daemon' }
  } finally { $connection.Dispose() }
} catch { Add-Check 'Local port 7878' 'warn' 'Cannot probe localhost port; check local network restrictions' }

if ($env:SYNAPSE_ACCOUNTS_BASE_URL -and $env:SYNAPSE_ACCOUNTS_BASE_URL -notlike 'https://accounts-api-production-f84a.up.railway.app*') {
  Add-Check 'Account endpoint override' 'warn' 'A custom SYNAPSE_ACCOUNTS_BASE_URL overrides the shared cloud; remove it manually if unintended'
} else {
  Add-Check 'Account endpoint override' 'pass' 'Default cloud account service is not overridden'
}
try {
  $data = Join-Path $env:LOCALAPPDATA 'Synapse'
  $dbs = @(Get-ChildItem -LiteralPath $data -Filter '*.sqlite' -File -ErrorAction SilentlyContinue)
  Add-Check 'User data preservation' 'pass' ('No user or project databases modified; local database files detected: '+$dbs.Count)
} catch { Add-Check 'User data preservation' 'warn' 'Could not list local user data; no files changed' }
$result=[pscustomobject]@{
  schema_version=1
  repair_requested=[bool]$Repair
  created_at=(Get-Date).ToUniversalTime().ToString('o')
  install_directory=$InstallDir
  checks=@($items.ToArray())
}
$result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
Write-Output ('Synapse repair report: ' + $ReportPath)
if (@($items|Where-Object status -eq 'fail').Count) { exit 2 }
exit 0
