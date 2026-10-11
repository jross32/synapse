# Synapse first-run toolchain provisioning. Non-elevated, user-scoped installs only.
[CmdletBinding()]
param(
  [ValidateSet('Audit','Install')][string]$Mode = 'Audit',
  [ValidateSet('Essential','Developer')][string]$Profile = 'Essential',
  [string]$ReportPath = ''
)
$ErrorActionPreference='Stop'
$tools=@(
  @{name='Git';command='git';package='Git.Git'},
  @{name='Node.js';command='node';package='OpenJS.NodeJS.LTS'},
  @{name='Python';command='python';package='Python.Python.3.12'}
)
if($Profile -eq 'Developer') {
  $tools+=@{name='VS Code';command='code';package='Microsoft.VisualStudioCode'}
}
$winget=Get-Command winget -ErrorAction SilentlyContinue
$results=@()
foreach($tool in $tools) {
  $present=[bool](Get-Command $tool.command -ErrorAction SilentlyContinue)
  $state=if($present){'installed'}else{'missing'}
  if(-not $present -and $Mode -eq 'Install') {
    if(-not $winget){$state='winget-unavailable'}
    else {
      & $winget.Source install --id $tool.package --exact --scope user --silent --disable-interactivity --accept-package-agreements --accept-source-agreements
      if($LASTEXITCODE -eq 0){$state='installed-pending-shell-refresh'}
      else {$state='install-failed'}
    }
  }
  $results+=@{tool=$tool.name;package=$tool.package;status=$state}
}
$report=[pscustomobject]@{
  mode=$Mode; profile=$Profile; wingetAvailable=[bool]$winget
  results=$results
}
if($ReportPath) {
  $parent=Split-Path -Parent $ReportPath
  if($parent){New-Item -ItemType Directory -Path $parent -Force | Out-Null}
  $report | ConvertTo-Json -Depth 5 | Set-Content -Path $ReportPath -Encoding UTF8
}
$report | ConvertTo-Json -Depth 5
if($Mode -eq 'Install' -and @($results|Where-Object {$_.status -in @('install-failed','winget-unavailable')}).Count -gt 0){exit 1}
