# Worker Git checkpoints

The shared checkpoint hook is opt-in and disabled unless configured for an isolated, owned Git repository.

Required worker environment:
- `SYNAPSE_GIT_CHECKPOINT=1`
- `SYNAPSE_GIT_TEST_COMMAND`: executable test command, run after the worker completes
- `SYNAPSE_GIT_OWNED_PATHS`: comma-separated repository-relative owned files
- `SYNAPSE_GIT_CHECKPOINT_MESSAGE`: concise commit message

The worker must complete successfully, the test command must exit zero, and the repository must pass the scoped checkpoint guard. Never treat a model's self-reported test success as verification. Existing shared worktree changes and overlapping ownership need coordination.

Optional publication (feature branches only):
- `SYNAPSE_GIT_AUTO_PUSH=1`
- `SYNAPSE_GITHUB_OWNER`: expected GitHub repository owner
- `SYNAPSE_GIT_PUSH_BRANCH`: exact current feature branch

Publication requires a clean repository, matching origin owner and branch, and a non-divergent remote. It never force-pushes. Prefer one isolated worktree per worker. Do not enable unattended publication in the shared development checkout.

Verification: `python daemon/tests/test_worker_git_checkpoint.py`, `python daemon/tests/test_worker_git_publish.py`, and `python daemon/tests/test_synapse_git_checkpoint.py`. Tests include real local commits and pushes to an isolated bare remote. The browser ChatGPT handoff integration and live authenticated GitHub push remain separate acceptance gates.
