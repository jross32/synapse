# Synapse backup and restore runbook

## Live inventory (as of October 16, 2026)
- Synapse project registry: 100 projects, 95 distinct registered paths prior to adding application-data and owner secret locations. Deduplicate nested directory roots for sizing.
- Live primary checkout: C:/Users/justi/synapse, including uncommitted and untracked files, working data, images, user-generated outputs and package manifests.
- Other registered project checkouts outside the main repository: must be separately inventoried. GitHub source alone does not preserve dirty local state.
- User and identity files: %APPDATA%/Synapse, %LOCALAPPDATA%/Synapse, ~/.synapse, private backup keys, cloudflared configuration, machine identity and runtime management configuration. They are sensitive: encrypt before storage, do not commit.
- Installed Electron app and Python daemon; installation packages can be rebuilt from pinned sources and verified published releases.
- Connected Railway Synapse Accounts production has live accounts-api service backed by persistent volume accounts-persistent-data mounted at /data, provisioned 500 MB. This is allocated capacity, not actual usage or proof of backup.
- Railway SYNAPS-OS Clinic OS Staging production currently has no live services or volumes.
- Cloud service credentials, third-party access, persistent browser sessions and connected service records need independent export or documented reauthentication.
- D: USB is FAT32; individual files larger than 4 GiB cannot be copied there.

## Recovery priority
Tier A, irreplaceable: consistent SQLite/database snapshots including WAL state; local Synapse profiles; keys/device identity; uncommitted and untracked code; generated media and uploads; project records; worker durable state; and Railway volume data. Encrypt and guard secrets; do not log raw values.
Tier B, reproducible if pinned: Git commits and refs, lockfiles, installer build recipes, deployment manifests, signed release digests, published artifacts and documented cloud configuration.
Tier C, usually rebuildable after confirming no owner-only data: node_modules, .venv, caches, dist, build output and throwaway staging artifacts.

## End-to-end recovery procedure (not yet performed)
1. Complete the local metadata inventory and separately measure Railway production /data and all independent connected providers. Do not equate volume capacity with used bytes.
2. Select at least two backup targets, both sized for measured data and retention; encrypt sensitive content. Record RPO/RTO and ownership.
3. Use transaction-consistent SQLite online backups, not unsafe blind file copies while the daemon runs. Confirm SQLite integrity_check and schema/version compatibility on an isolated copy.
4. Export Railway /data through a service-approved authenticated backup endpoint or provider-supported snapshot mechanism. Do not delete, detach, resize or replace the production volume during an inventory.
5. Securely escrow private keys and identities with restricted access; record which provider OAuth tokens must be reauthorized. Never commit encrypted secrets without explicit owner approval or store any plaintext ones in logs.
6. Hash source-to-destination archives and retain signed or otherwise independently verifiable manifests. Do not label uploads successful backups until hashes match.
7. Restore into a new empty disconnected directory and test read-only database integrity, desktop startup, account/profile import, role grants and worker state. Verify existing owner MCP connector URL is preserved without rotating it.
8. Record exact restore evidence and rehearse periodic drills. A synthetic fixture pass is NOT evidence of an entire application, cloud or device recovery.

## Tools
- scripts/synapse_backup_inventory.py: inventory registered non-overlapping directory roots, metadata-only, no file contents read.
- scripts/synapse_backup_inventory.py restore-test: safe SHA-256 checked synthetic-fixture copy and isolated restore, never overwrites live data.
- daemon/tests/test_synapse_backup_inventory.py: safety regression tests.
- Keep private generated inventory and file paths off GitHub.

## Release and backup gates
Do not call all of Synapse backed up, restored, or safe for an unattended migration until real local state, source changes, Railway persistent data, credentials, external dependencies and cross-device account/MCP continuity have independent restore evidence.

## SQLite-specific recovery tool
Use scripts/synapse_sqlite_backup_verify.py with three distinct paths: --source (existing live SQLite DB), --archive (new encrypted-target staging file), and --restored (new isolated verification path). Uses SQLite's online backup interface, PRAGMA integrity_check, and SHA-256 on the restored file. It never overwrites an existing archive or source, but the new backup file **can contain secrets** and must be encrypted before cloud transfer. Tests in daemon/tests/test_synapse_sqlite_backup_verify.py exercise WAL mode and overwrite refusal. Passing fixture tests does not certify the production Railway accounts volume.

## Measurement status
The read-only registered-project recovery estimate reported 29.64 GiB of local project and selected Synapse state roots with generated build/dependency folders excluded. A separate fast scan of 170 local repositories reported 32.91 GiB before selected application state. These scopes overlap; never add their totals. Neither includes actual Railway /data usage or third-party cloud exports. The slower exhaustive scan timed out without producing a report.
