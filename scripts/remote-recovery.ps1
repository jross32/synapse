# Synapse WAN recovery helper.
#
# Use this when the desktop UI is unreachable but this Windows machine is still
# reachable through Codex or another local automation surface. It starts or
# reuses the Synapse daemon, opens a Cloudtap tunnel for port 7878, and prints
# the phone URL plus a fresh pairing code.

param(
  [int]$Port = 7878,
  [string]$DataDir = '',
  [int]$TimeoutSeconds = 120,
  [switch]$InstallCloudflared,
  [switch]$Json
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
$baseUrl = "http://127.0.0.1:$Port"
$apiBase = "$baseUrl/api/v1"
$logDir = if (Test-Path (Join-Path $root 'package.json')) {
  Join-Path $root 'data'
} else {
  Join-Path $env:APPDATA 'Synapse'
}
$logPath = Join-Path $logDir 'remote-recovery-daemon.log'

function Write-Step {
  param([string]$Message)
  if (-not $Json) {
    Write-Host "-> $Message"
  }
}

function ConvertTo-CmdArgument {
  param([string]$Value)
  return '"' + ($Value -replace '"', '\"') + '"'
}

function Join-CmdArguments {
  param([string[]]$Values)
  $quoted = @()
  foreach ($value in $Values) {
    $quoted += ConvertTo-CmdArgument $value
  }
  return [string]::Join(' ', $quoted)
}

function Get-DefaultDataDir {
  if ($DataDir) {
    return $DataDir
  }
  if (Test-Path (Join-Path $root 'package.json')) {
    return (Join-Path $root 'data')
  }
  return (Join-Path (Join-Path $env:APPDATA 'Synapse') 'data')
}

function Test-DaemonReady {
  try {
    $health = Invoke-RestMethod -Method GET -Uri "$apiBase/health" -TimeoutSec 3
    return $null -ne $health -and $health.ok -eq $true
  } catch {
    return $false
  }
}

function Wait-DaemonReady {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    if (Test-DaemonReady) {
      return
    }
    Start-Sleep -Milliseconds 500
  } while ((Get-Date) -lt $deadline)

  throw "Synapse daemon did not become ready at $baseUrl within ${TimeoutSeconds}s."
}

function Start-SynapseDaemon {
  if (Test-DaemonReady) {
    Write-Step "Synapse daemon is already running at $baseUrl"
    return
  }

  $resolvedDataDir = Get-DefaultDataDir
  New-Item -ItemType Directory -Force -Path $resolvedDataDir | Out-Null
  New-Item -ItemType Directory -Force -Path $logDir | Out-Null

  $packagedDaemon = Join-Path $root 'daemon\synapse-daemon.exe'
  $sourceDaemonPackage = Join-Path $root 'daemon\synapse_daemon'
  $toolsDir = Join-Path $root 'tools'

  if (Test-Path $packagedDaemon) {
    Write-Step "Starting packaged daemon"
    $daemonArgs = @(
      '--port', [string]$Port,
      '--data-dir', $resolvedDataDir,
      '--tools-dir', $toolsDir,
      '--bind-lan'
    )
    $command = "$(ConvertTo-CmdArgument $packagedDaemon) $(Join-CmdArguments $daemonArgs) >> $(ConvertTo-CmdArgument $logPath) 2>&1"
    Start-Process -FilePath 'cmd.exe' -ArgumentList @('/d', '/c', $command) -WorkingDirectory $root -WindowStyle Hidden | Out-Null
  } elseif (Test-Path $sourceDaemonPackage) {
    Write-Step "Starting source daemon"
    $pythonPath = Join-Path $root 'daemon'
    $daemonArgs = @(
      '-m', 'synapse_daemon',
      '--port', [string]$Port,
      '--data-dir', $resolvedDataDir,
      '--tools-dir', $toolsDir,
      '--bind-lan'
    )
    $command = "set `"PYTHONPATH=$pythonPath`"&& python $(Join-CmdArguments $daemonArgs) >> $(ConvertTo-CmdArgument $logPath) 2>&1"
    Start-Process -FilePath 'cmd.exe' -ArgumentList @('/d', '/c', $command) -WorkingDirectory $root -WindowStyle Hidden | Out-Null
  } else {
    throw "Could not find a Synapse daemon next to this script. Checked packaged and source layouts under $root."
  }

  Wait-DaemonReady
}

function Ensure-Cloudflared {
  if (Get-Command cloudflared -ErrorAction SilentlyContinue) {
    return
  }
  if (-not $InstallCloudflared) {
    throw "cloudflared is not on PATH. Re-run with -InstallCloudflared, or install Cloudflare.cloudflared with winget."
  }
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "cloudflared is missing and winget is not available to install it."
  }

  Write-Step "Installing cloudflared with winget"
  $wingetArgs = @(
    'install',
    '--id', 'Cloudflare.cloudflared',
    '--exact',
    '--source', 'winget',
    '--accept-package-agreements',
    '--accept-source-agreements',
    '--silent'
  )
  $proc = Start-Process -FilePath 'winget' -ArgumentList $wingetArgs -Wait -PassThru -WindowStyle Hidden
  if ($proc.ExitCode -ne 0) {
    throw "winget install Cloudflare.cloudflared failed with exit code $($proc.ExitCode)."
  }
  if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    throw "cloudflared installed, but it is not visible on PATH in this shell yet. Open a fresh shell and retry."
  }
}

function Invoke-SynapseJson {
  param(
    [Parameter(Mandatory = $true)][string]$Method,
    [Parameter(Mandatory = $true)][string]$Path,
    [object]$Body = $null,
    [string]$Token = ''
  )

  $headers = @{ Accept = 'application/json' }
  if ($Token) {
    $headers['X-Synapse-Token'] = $Token
  }

  $params = @{
    Method = $Method
    Uri = "$apiBase$Path"
    Headers = $headers
    TimeoutSec = 30
  }
  if ($null -ne $Body) {
    $params['ContentType'] = 'application/json'
    $params['Body'] = ($Body | ConvertTo-Json -Depth 8)
  }

  return Invoke-RestMethod @params
}

function Get-LocalToken {
  $result = Invoke-SynapseJson -Method GET -Path '/auth/local-token'
  if (-not $result.token) {
    throw 'The daemon did not return a local auth token.'
  }
  return $result.token
}

function Get-MobileUrl {
  param([object]$RemoteAccess)
  if ($RemoteAccess.wan.verification.mobile_url) {
    return [string]$RemoteAccess.wan.verification.mobile_url
  }
  if ($RemoteAccess.wan.public_url) {
    return ([string]$RemoteAccess.wan.public_url).TrimEnd('/') + '/mobile'
  }
  return $null
}

function Wait-WanReady {
  param([string]$Token)

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  $last = $null
  $bestActive = $null
  do {
    $last = Invoke-SynapseJson -Method GET -Path '/remote-access' -Token $Token
    $mobileUrl = Get-MobileUrl -RemoteAccess $last
    $status = [string]$last.wan.verification.status
    if ($last.wan.active -and $mobileUrl) {
      $bestActive = $last
    }
    if ($last.wan.active -and $mobileUrl -and $status -eq 'ready') {
      return $last
    }
    Start-Sleep -Seconds 2
  } while ((Get-Date) -lt $deadline)

  if ($null -ne $bestActive) {
    return $bestActive
  }
  return $last
}

Start-SynapseDaemon
Ensure-Cloudflared

Write-Step "Reading local daemon token"
$token = Get-LocalToken

Write-Step "Opening Cloudtap tunnel for port $Port"
$remote = Invoke-SynapseJson -Method GET -Path '/remote-access' -Token $token
$mobileUrl = Get-MobileUrl -RemoteAccess $remote
if (-not ($remote.wan.active -and $mobileUrl -and $remote.wan.local_port -eq $Port)) {
  Invoke-SynapseJson -Method POST -Path '/tools/cloudtap/actions/tunnel' -Token $token -Body @{
    fields = @{ port = $Port }
    source = 'cli'
  } | Out-Null
}

Write-Step "Waiting for WAN mobile URL"
$remote = Wait-WanReady -Token $token
$mobileUrl = Get-MobileUrl -RemoteAccess $remote
if (-not $mobileUrl) {
  $message = $remote.wan.verification.failure_message
  if (-not $message) {
    $message = 'Cloudtap did not produce a mobile URL.'
  }
  throw $message
}

Write-Step "Issuing pairing code"
$pairing = Invoke-SynapseJson -Method POST -Path '/pair/code' -Token $token

$result = [ordered]@{
  ok = $true
  computer_name = $remote.computer_name
  mobile_url = $mobileUrl
  pairing_code = $pairing.code
  pairing_expires_at = $pairing.expires_at
  wan_status = $remote.wan.verification.status
  wan_failure_message = $remote.wan.verification.failure_message
  daemon_url = $baseUrl
}

if ($Json) {
  $result | ConvertTo-Json -Depth 8
} else {
  Write-Host ''
  Write-Host 'Synapse WAN recovery is ready.'
  Write-Host "Computer     : $($result.computer_name)"
  Write-Host "Mobile URL   : $($result.mobile_url)"
  Write-Host "Pairing code : $($result.pairing_code)"
  Write-Host "Expires at   : $($result.pairing_expires_at)"
  Write-Host "WAN status   : $($result.wan_status)"
  if ($result.wan_failure_message) {
    Write-Host "WAN note     : $($result.wan_failure_message)"
  }
}
