# Account and device synchronization release blocker

User-reported failure on 2026-10-12: publicly downloadable premium v0.2.219 did not provide expected syncing.

## Grounded diagnosis
- The connected laptop was still actively running Synapse daemon v0.1.209 and had an earlier installed Synapse.exe, even though premium v0.2.219 was publicly downloadable.
- On this laptop account preference sync was healthy (signed-in, enabled, recent successful sync, no sync error). Account-host records included one desktop that had not checked in recently, and an older duplicate laptop identity.
- Account preference / device-record sync is not automatic cross-device project-file replication. The latter requires signed-in authorization, consent, manifests, conflict rules, retries and two-machine E2E testing.
- The v0.2.219 premium wrapper previously verified installed files, not the daemon actually serving port 7878 after launch.

## Mitigation prepared (next release only, not shipped)
- Add installer/premium-shell/daemon-version-check.cjs and bundle in electron-builder build.files.
- On setup launch, check the live loopback daemon /api/v1/health and require the actual running version to match installed package. A surviving older daemon raises a concrete error instead of false setup success.
- Probe is read-only, loopback-only, does not read credentials, does not rotate account MCP URL, and never kills a daemon or removes user files.
- Tests cover old daemon detection, correct version, delayed recovery and invalid input. Included under test-daemon-version-check.cjs and the host test harness.

## Before saying sync is fixed
1. Both Windows machines must install same release, reopen it, and report correct live daemon version. Prove upgrade migration, database preservation and rollback.
2. Same account signs in on both, one identity per physical device. Verify host list, nickname, duplicate cleanup, safe revision-based preferences and cross-version behavior.
3. Account MCP link remains stable. Verify per-device permission, remote AI tool execution and device selection.
4. Explicitly authorize permitted project file transfers, with checksum/conflict handling, reconnect/retry and limits. No project or session portability promise until this is tested.
5. Record independent end-to-end proof on two machines, re-package, and publish a new release. Do not silently replace previous artifacts.

No live upgrade or device repair performed by this patch.
