param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [int]$Port = 7878,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$package = Get-Content (Join-Path $RepoRoot 'package.json') -Raw | ConvertFrom-Json
$moduleFile = Join-Path $RepoRoot 'daemon/synapse_daemon/__init__.py'
$moduleText = Get-Content $moduleFile -Raw
$match = [regex]::Match($moduleText, '__version__\s*=\s*"([^"]+)"')
if (-not $match.Success) { throw 'Unable to resolve source daemon version' }
$frontend = [string]$package.version
$backend = $match.Groups[1].Value
$listenerInfo = @()
foreach ($c in @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) {
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" -ErrorAction SilentlyContinue
    $command = if ($processInfo) { [string]$processInfo.CommandLine } else { '' }
    $listenerInfo += [pscustomobject]@{
        pid = [int]$c.OwningProcess
        address = [string]$c.LocalAddress
        source_process = $command.Contains($RepoRoot)
        installed_binary = $command -match '\\Programs\\Synapse\\resources\\daemon\\synapse-daemon\.exe'
        executable_name = if ($processInfo) { [string]$processInfo.Name } else { 'unknown' }
    }
}
$listenerInfo = @($listenerInfo | Sort-Object pid,address -Unique)
$result = [pscustomobject]@{
    repo = $RepoRoot
    frontend_version = $frontend
    source_daemon_version = $backend
    source_versions_match = $frontend -eq $backend
    listeners = $listenerInfo
    safe_to_start = ($frontend -eq $backend) -and ($listenerInfo.Count -eq 0)
    blocked_reason = if ($frontend -ne $backend) {
        "Source package version $frontend differs from daemon $backend. Reconcile source versions before launching dev mode."
    } elseif ($listenerInfo.Count) {
        "Port $Port is already held by $($listenerInfo.Count) daemon listener(s). Existing Synapse work and MCP link will not be interrupted. Restart only after explicit checks."
    } else { $null }
}
$result | ConvertTo-Json -Depth 5
if (-not $CheckOnly -and -not $result.safe_to_start) { exit 4 }
