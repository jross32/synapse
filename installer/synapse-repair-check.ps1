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
  Add-Check 'Account endpoint override' 'warn' 'A custom account endpoint exists. Current installers ignore localhost endpoints unless SYNAPSE_ALLOW_LOCAL_ACCOUNTS=1. Check any other custom URL if sign-in fails'
} else {
  Add-Check 'Account endpoint override' 'pass' 'Default cloud account service is not overridden'
}
try {
  $data = Join-Path $env:LOCALAPPDATA 'Synapse'
  $dbs = @(Get-ChildItem -LiteralPath $data -Filter '*.sqlite' -File -ErrorAction SilentlyContinue)
  Add-Check 'User data preservation' 'pass' ('No user or project databases modified; local database files detected: '+$dbs.Count)
} catch { Add-Check 'User data preservation' 'warn' 'Could not list local user data; no files changed' }
# Writable application-data locations are essential for login sessions, device
# credentials, downloads, settings and diagnostics. Never alter their contents.
foreach ($entry in @(
  @{name='Roaming settings access';path=(Join-Path $env:APPDATA 'Synapse')},
  @{name='Local settings access';path=(Join-Path $env:LOCALAPPDATA 'Synapse')},
  @{name='Temporary file access';path=$env:TEMP}
)) {
  try {
    if (-not (Test-Path $entry.path -PathType Container)) {
      if ($Repair) { New-Item -ItemType Directory -Path $entry.path -Force -ErrorAction Stop | Out-Null }
      else { Add-Check $entry.name 'warn' 'Directory absent; rerun Setup with repair selected'; continue }
    }
    $probe=Join-Path $entry.path ('.synapse-repair-probe-'+[guid]::NewGuid().ToString('N'))
    try { [IO.File]::WriteAllText($probe,'ok'); if ([IO.File]::ReadAllText($probe) -ne 'ok') {throw 'Readback mismatch'} }
    finally { Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue }
    Add-Check $entry.name 'pass' 'Create/read/delete test succeeded'
  } catch { Add-Check $entry.name 'warn' 'Directory is not writable. Check permissions and security software' }
}

try {
  $cfg=Join-Path $env:APPDATA 'Synapse\bootstrap-ai-bundles.json'
  if (Test-Path $cfg -PathType Leaf) {
    $bundleConfig=Get-Content -LiteralPath $cfg -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    if ($null -ne $bundleConfig.bundle_ids -and $bundleConfig.bundle_ids -is [array]) {
      Add-Check 'Bundle preferences JSON' 'pass' 'Existing selections are valid and preserved'
    } else { Add-Check 'Bundle preferences JSON' 'warn' 'Configuration structure is invalid; repair does not overwrite user preferences' }
  } else { Add-Check 'Bundle preferences JSON' 'pass' 'No existing preferences to preserve' }
} catch { Add-Check 'Bundle preferences JSON' 'warn' 'User configuration is not valid JSON; back up before correcting manually' }

try {
  $source=Join-Path $InstallDir 'resources\app\package.json'
  $config=Get-Content -LiteralPath $source -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
  if ($config.name -and $config.version) { Add-Check 'Package metadata integrity' 'pass' 'Package configuration parses correctly' }
  else { Add-Check 'Package metadata integrity' 'fail' 'Invalid application metadata; installer repair is required' }
} catch { Add-Check 'Package metadata integrity' 'fail' 'Corrupt application metadata; run installer repair' }

try {
  $uri=[uri]'https://accounts-api-production-f84a.up.railway.app/v1/health'
  if ($uri.Scheme -ne 'https') {throw 'TLS required'}
  $net=[System.Net.WebRequest]::Create($uri)
  $net.Timeout=8000
  $reply=$net.GetResponse()
  try { Add-Check 'TLS certificate trust' 'pass' 'HTTPS handshake and certificate validation succeeded' }
  finally { $reply.Close() }
} catch { if (-not $SkipNetwork) {Add-Check 'TLS certificate trust' 'warn' 'HTTPS validation failed; check date/time, certificates, VPN or proxy'} }

try {
  $drive=Get-PSDrive -Name ([IO.Path]::GetPathRoot($InstallDir).Substring(0,1)) -ErrorAction Stop
  if ($drive.Free -lt 2GB) {Add-Check 'Update working space' 'warn' 'Less than 2 GB available; a future update may fail during extraction'}
  else {Add-Check 'Update working space' 'pass' 'Enough free disk space for typical upgrades'}
} catch {Add-Check 'Update working space' 'warn' 'Could not verify space for update extraction'}

try {
  $dbPaths=@((Join-Path $env:LOCALAPPDATA 'Synapse\synapse.sqlite'),(Join-Path $env:APPDATA 'Synapse\synapse.sqlite'))
  $found=@($dbPaths | Where-Object {Test-Path $_ -PathType Leaf})
  if ($found.Count -gt 0) {Add-Check 'Database preservation' 'pass' ('Detected '+$found.Count+' databases; no migrations or modifications performed')}
  else {Add-Check 'Database preservation' 'pass' 'No standard database files to modify; data may be in a custom Synapse workspace'}
} catch {Add-Check 'Database preservation' 'warn' 'Could not inspect local database paths' }
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
