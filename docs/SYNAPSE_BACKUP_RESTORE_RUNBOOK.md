# Synapse Ecosystem Backup & Isolated Restore Runbook

Last reviewed: 2026-10-15. **Backup is not yet complete**. This file is a recovery plan, not a claim that off-device backups exist.

## Recovery layers

1. **Primary Synapse working tree**: \`C:\Users\justi\synapse\`. Preserve \`.git\`, uncommitted changes, untracked files and \`data\`. A GitHub clone **alone is insufficient**.
2. **Separate product repositories and worktrees**: discover under \`C:\Users\justi\` and reconcile against Synapse's registered projects. Preserve unpushed changes. Distinguish shared Git worktree objects from independent repos.
3. **Synapse state**: \`data\` including \`synapse.sqlite\`, \`synapse-accounts.sqlite\`, project and worker ledgers, signed consent/identity state, local files, image/video assets and logs needed for audit. Preserve browser profiles and session data with encryption.
4. **Windows user state**: \`%APPDATA%\Synapse\`, \`%LOCALAPPDATA%\Synapse\`, and the installed binary/package identity, with specific attention to device ID, login/account state and current connector URL. Save installer source commit and SHA-256.
5. **Cloud account system**: Railway project **Synapse Accounts**, production \`accounts-api\` from \`jross32/synapse\`, persistent volume **accounts-persistent-data** mounted at \`/data\` (500 MB provisioned, **not** 500 MB used). This needs a consistent service-controlled snapshot plus an independent restore test. **No cloud-volume snapshot or restore has yet been verified.**
6. **Other cloud state**: Railway **SYNAPS-OS Clinic OS Staging** currently lists no production services or volumes. Audit connected GitHub repos, Cloudflare tunnels/DNS, download.whatapc.com hosting, service OAuth grants, API keys, and all other connected providers independently. GitHub code is not a backup of remote databases or OAuth connections.
7. **Signing and secrets**: release Ed25519 **private** key under user-specific local release signing path, public trust configuration, account credentials and tokens, private browser profile. Never print the secrets or include them in a plain JSON report, public Git repo, or unencrypted cloud/USB backup.

## Space model

\`scripts/synapse_backup_inventory.py\` records raw bytes and an **upper bound** for recovery data after excluding common generated folders (\`node_modules\`, \`.venv\`, \`dist\`, build outputs). Git worktrees can share objects and inflate both totals. Compression may reduce bytes but cannot be assumed until measured.

Available USB \`D:\` uses FAT32, so a *single* archive file must be smaller than 4 GiB; FAT32 does not preserve NTFS permissions, symlinks or ACLs. Use split encrypted archives or an NTFS/exFAT backup drive if appropriate. **Never directly relocate a working repository onto FAT32.**

## Safe capture order

1. Save a versioned read-only inventory JSON outside the repository; review exclusions and missing source folders.
2. Collect Git status and commit IDs; capture dirty/untracked worktrees explicitly, not merely remote URLs.
3. Take application-aware SQLite snapshots using Python SQLite \`Connection.backup()\` (not raw copies of live WAL databases), inspect \`PRAGMA integrity_check\`, and record checksums.
4. Export Synapse configuration, media files, project ledgers and encrypted secrets; distinguish rebuilding dependencies from irreplaceable user state.
5. Ask the production service for a **consistent Railway /data export**. Confirm restore on a **separate isolated service/environment**, not production. Volume size is not used bytes.
6. Store two encrypted copies on physically separate media or providers. Retain offline recovery credentials and a recovery key in a secure location separate from backup files.
7. Verify checksums and perform the isolated restore smoke before considering the backup usable.

## Restore test / anti-footgun

\`scripts/synapse_restore_verify.py\` verifies manifest paths, SHA-256 and byte counts before restoration. It **refuses existing destinations** and never overwrites the running installation. It supports isolated restore into a newly created directory and checks SQLite integrity. Tests use fake files and fake SQLite databases only.

Run synthetic proof:
\`python -m pytest daemon/tests/test_synapse_backup_inventory.py daemon/tests/test_synapse_restore_verify.py -q\`

A **real production recovery test** is still required: restore encrypted copies on a spare NTFS machine/VM, start a detached Synapse daemon against the restored database, confirm the app can open, verify project counts, real login/account/device routing, MCP connector preservation, and rollback. Do not reuse production credentials from an unsafe environment.

## Not done / strict gates

- An inventory cannot assert all assets are covered until Synapse's registered project paths and cloud services are reconciled.
- A GitHub push is not a database backup.
- A test against synthetic files does not prove real Synapse service recovery.
- No service restarts, deletion, cloud key rotation, migration, or production database restore should occur during inventory.
