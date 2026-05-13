# Synapse — Pydantic → TypeScript type generator (Contract #8).
#
# Reads daemon/synapse_daemon/models.py (via model_registry()) and writes
# renderer/lib/generated-types.ts. CI compares the freshly-generated output to
# the committed file and fails if they differ.
#
# v0.1.1 — placeholder. Hand-maintained generated-types.ts ships today.
# Real generator wires in during Milestone B alongside the daemon's FastAPI
# app (which makes `python -c "from synapse_daemon.models import model_registry"`
# meaningful).

param(
  [switch]$Check  # CI mode: exit non-zero if file would change
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$outFile = Join-Path $root 'renderer\lib\generated-types.ts'

Write-Host "gen-types.ps1 — Synapse type generator"
Write-Host ""
Write-Host "Status: scaffolded but not yet wired (Milestone B will activate)."
Write-Host "Target file: $outFile"
Write-Host ""

if ($Check) {
  Write-Host "Check mode requested — no-op until generator is live."
  Write-Host "Will compare generated output to committed file and exit non-zero on drift."
  exit 0
}

Write-Host "Skipping regeneration in v0.1.1 — generator activates in Milestone B."
Write-Host "If you need to edit generated-types.ts in the meantime, edit by hand"
Write-Host "and keep it in sync with daemon/synapse_daemon/models.py."
