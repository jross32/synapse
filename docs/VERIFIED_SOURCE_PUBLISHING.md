# Verified Source Publishing Contract

Applies to all Synapse implementation workers, including AI workers, on the laptop and in isolated worktrees.

## Required completion gate

A change is **not finished** merely because it runs locally. After the change passes relevant tests and review:

1. Identify only the files owned by this change. Never `git add .` or `git add -A` in a shared checkout.
2. Check `git diff --check`, run focused tests, and review the exact staged diff for credentials, tokens, personal data, binary output, and unrelated worker changes.
3. Commit the verified source with a descriptive message in a dedicated branch/worktree.
4. Push that commit to `origin` (`jross32/synapse`) and confirm the remote branch contains its SHA.
5. Record the commit SHA, branch, tests, and any outstanding merge/release blockers in the work report.

If push fails or review identifies unsafe files, report the task as **verified locally, NOT synced**. Never claim GitHub is current until remote verification succeeds. A pushed branch is a backup, not necessarily a merged or deployed release.

## Safety and collaboration

- Never stage credentials, `.env` files, private keys, auth tokens, session data, database files, or generated installers/artifacts.
- Use isolated worktrees when other workers are modifying the same repository. Do not reset, overwrite, or commit another worker's unreviewed changes.
- Do not force-push shared branches or automatically merge unreviewed changes.
- Preserve the existing live Synapse MCP URL, signing identity, and device routing; connector rotation requires explicit owner authorization.
- If source verification requires dependencies or unpublished concurrent changes, identify those dependencies and keep the task open rather than shipping an incomplete commit.

## Visibility

Run `scripts/audit-github-source.ps1` to identify unsynced local source. `-Strict` exits nonzero when modified tracked files, untracked source files, or unpushed commits exist. The audit does not stage, commit, push, or delete anything.

## Remote verification command

From a clean, verified feature worktree, run `scripts/verify-github-push.ps1 -Push`. It pushes only the current branch to the approved Synapse GitHub origin and checks the remote SHA. Without `-Push`, it checks whether GitHub already contains the exact local commit. This is an opt-in command, not a background worker hook; worker-wide automatic invocation remains to be integrated.

