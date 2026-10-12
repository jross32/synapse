# Synapse Railway monitor credential setup (Windows user-scoped DPAPI).
# Run interactively from the same Windows account running Synapse.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$folder = Join-Path $root 'data\railway-costs'
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$target = Join-Path $folder 'railway-token.dpapi'
Write-Host 'Create an account/workspace API token at https://railway.com/account/tokens'
Write-Host 'Enter it here. No token is displayed, logged, committed, or sent to ChatGPT.'
$secret = Read-Host -Prompt 'Railway API token' -AsSecureString
if (-not $secret -or $secret.Length -lt 10) { throw 'Token is too short' }
$encoded = ConvertFrom-SecureString -SecureString $secret
[System.IO.File]::WriteAllText($target, $encoded, [System.Text.UTF8Encoding]::new($false))
Write-Host 'Encrypted Railway credential saved for this Windows account.'
Write-Host 'Next open Synapse Watchdogs and refresh the Railway panel after safe daemon reload.'
