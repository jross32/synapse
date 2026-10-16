# Synapse backup and disaster recovery inventory

Status: read-only inventory plus synthetic restore test. No complete live-data backup exists yet.

## Include in encrypted backups

- Main Synapse source, every registered project folder, dirty and unpushed worktrees, Git histories and untracked work.
- Roaming and Local Synapse state, SQLite data including WAL/SHM as applicable, settings, device enrollment, worker execution/checkpoints.
- Account identifiers and stable MCP connector URL binding, owner-approved encrypted credentials, certificates and signing trust keys.
- Browser worker profiles, agent state and startup settings required for active workflows.
- Cloud: Railway Synapse Accounts production accounts-api with the accounts-persistent-data volume mounted at /data, GitHub repos/releases/Actions, Cloudflare DNS/tunnel routing, and connected OAuth/cloud-storage providers.

## Size and methodology

Run python scripts/synapse_backup_inventory.py --skip-generated --output PRIVATE_PATH
Run python scripts/synapse_dependency_backup_inventory.py --registry PRIVATE_REGISTERED_PROJECT_PATHS_JSON --output PRIVATE_PATH
Registry path export must include path and id only, NEVER the env or secret values from Synapse project records.
These give logical-file sizes excluding rebuildable dependency/build directories; nested roots are deduplicated only within the registered-project report. Actual archive size, media, cloud data, compression ratios and unregistered sources remain uncertain.

## Snapshot and restore plan

1. Acquire dedicated encrypted NTFS 64+ GB or bigger backup storage, or encrypted cloud storage, with a second independent copy. Current FAT32 USB is not suitable for a complete archive.
2. Produce consistent online SQLite backups, check integrity, and do not copy a live database without its active WAL. Snapshot Railway /data via provider-supported mechanisms, including restore credentials kept securely.
3. Record content SHA256, size, schema, current release version, project refs and database integrity. Encrypt credentials, browser profiles and data at rest; NEVER commit backup bytes or secrets to GitHub.
4. Offline-verify the supported manifest-format archive with scripts/synapse_restore_verify.py; restore into a new isolated directory, never over an existing live installation.
5. Restore Railway data into an isolated service and prove login, stable connector URL, device identities, worker restarts, actual cross-device commands and encrypted transfers before announcing recovery.
6. Repeat after upgrades and retain at least one offline copy. GitHub pushes are not database, device-identity, token, hosted-volume or cloud-secret backups.

## Evidence and limitations

On 2026-10-16, the existing restore verifier passed 14 focused inventory/restore tests including new registry tests. A synthetic SQLite/settings archive was integrity-checked and restored to an empty D: folder; SQLite integrity and overwrite refusal passed.
Production restore of actual credentials, real devices and hosted databases has NOT been performed. Remote used bytes and backup availability are UNKNOWN until queried/exported directly.
