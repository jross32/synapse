# Call the shared Playwright MCP through the local Synapse MCP endpoint and print only the result.
# Usage: pw.ps1 -CodeFile x.js            (browser_run_code_unsafe with code from file)
#        pw.ps1 -Tool browser_tabs -ArgsJson '{"action":"select","index":3}'
param([string]$CodeFile = '', [string]$Tool = 'browser_run_code_unsafe', [string]$ArgsJson = '{}', [int]$Max = 4000, [string]$Config = (Join-Path $PSScriptRoot 'config.json'))
$cfg = Get-Content $Config -Raw | ConvertFrom-Json
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$tok = (Get-Content $cfg.tokenFile -Raw).Trim()
if ($CodeFile) { $toolArgs = @{ code = [string][System.IO.File]::ReadAllText($CodeFile) } } else { $toolArgs = $ArgsJson | ConvertFrom-Json }
$rpc = @{ jsonrpc = '2.0'; id = 1; method = 'tools/call'; params = @{ name = 'synapse_call_mcp_tool'; arguments = @{ server = 'playwright'; tool = $Tool; arguments = $toolArgs } } } | ConvertTo-Json -Depth 8 -Compress
$r = Invoke-RestMethod -Method POST -Uri (($cfg.synapseUrl.TrimEnd('/') + "/mcp/") + $tok) -ContentType 'application/json' -Body ([System.Text.Encoding]::UTF8.GetBytes($rpc)) -TimeoutSec 170
if ($r.error) { 'RPC_ERROR ' + ($r.error | ConvertTo-Json -Compress); exit 1 }
$text = ($r.result.content | ForEach-Object { $_.text }) -join "`n"
# The proxied playwright payload is JSON text containing its own content array.
try { $inner = $text | ConvertFrom-Json; if ($inner.content) { $text = ($inner.content | ForEach-Object { $_.text }) -join "`n" } } catch {}
$cut = $text.IndexOf('### Ran Playwright code'); if ($cut -lt 0) { $cut = $text.IndexOf('### Open tabs') }
if ($cut -gt 0) { $text = $text.Substring(0, $cut) }
$text = $text.Trim()
if ($text.Length -gt $Max) { $text = $text.Substring(0, $Max) + '...[truncated]' }
$text
