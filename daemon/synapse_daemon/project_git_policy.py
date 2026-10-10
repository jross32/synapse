"""Non-destructive Git collaboration instructions for newly created Synapse projects.

This does not initialize, publish, or modify Git repositories.
"""
from pathlib import Path

POLICY = """# AI development agreement

This project is managed through Synapse. Every AI working here must:

1. Read current project context and Git status before changing files.
2. Register a Synapse coordination session and claim a scoped file lane; do not overwrite other workers.
3. Use an isolated branch/worktree for simultaneous changes whenever possible.
4. Make small, reversible changes with focused tests and broader regression checks.
5. Stage only owned files; never use blind `git add -A`, reset, force-push, or overwrite another agent's work.
6. Before committing, verify tests, diff, and concurrent changes. Record evidence, update README/CHANGELOG/version when applicable.
7. Push only to a verified authorized GitHub remote after checking ahead/behind and resolving conflicts safely; do not create public repos automatically.
8. Save a durable Synapse handoff containing files touched, checks, blockers, and next actions.
9. If coordination or verification is unavailable, stop the risky Git operation and report the blocker.

A passing test suite is evidence, not a guarantee of zero bugs.
"""

def provision_new_project_policy(path: Path) -> bool:
    """Create instructions only if none exist; never modify an existing policy."""
    target = path / "AGENTS.md"
    try:
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(POLICY)
        return True
    except FileExistsError:
        return False
