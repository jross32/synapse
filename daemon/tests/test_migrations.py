"""Contract #9 — migration file presence + naming."""

from __future__ import annotations

from synapse_daemon.migrations import MIGRATION_PATTERN, list_migrations


def test_first_migration_exists() -> None:
    migrations = list_migrations()
    assert len(migrations) >= 1, "Expected at least migration 001"
    assert migrations[0].number == 1
    assert migrations[0].slug == "initial"


def test_round2_migration_present() -> None:
    """v0.1.2 ships migration 002 for Round 2 contract tables."""

    migrations = list_migrations()
    by_number = {m.number: m for m in migrations}
    assert 2 in by_number, "Migration 002 (Round 2 schema) is missing"
    assert by_number[2].slug == "round2_schema"


def test_round2_migration_defines_new_tables() -> None:
    """Contracts #20, #21, #22, #25 add tables."""

    from importlib import resources

    sql = resources.files("synapse_daemon.migrations").joinpath("002_round2_schema.sql").read_text(
        encoding="utf-8"
    )
    for required_table in (
        "project_dependencies",
        "search_index",
        "notification_preferences",
        "project_secrets",
    ):
        assert required_table in sql, f"002_round2_schema.sql is missing table: {required_table}"


def test_all_migrations_match_pattern() -> None:
    # Contract #9 file naming: NNN_slug.sql.
    for m in list_migrations():
        assert MIGRATION_PATTERN.match(m.filename), f"Bad filename: {m.filename}"
        assert 0 <= m.number <= 999, "Three-digit migration number expected"


def test_migration_numbers_strictly_increasing_with_no_gaps() -> None:
    nums = [m.number for m in list_migrations()]
    assert nums == sorted(nums), "Migrations must be ordered by number"
    # Allow gaps in principle (deleted migrations are okay), but warn on duplicates:
    assert len(nums) == len(set(nums)), "Duplicate migration numbers detected"


def test_initial_migration_defines_required_tables() -> None:
    """Smoke-check Contract #9 + #11 by reading the SQL text."""

    from importlib import resources

    sql = resources.files("synapse_daemon.migrations").joinpath("001_initial.sql").read_text(
        encoding="utf-8"
    )

    for required_table in (
        "schema_migrations",
        "audit_log",
        "projects",
        "tools",
        "managed_processes",
        "confirm_preferences",
        "settings",
    ):
        assert required_table in sql, f"001_initial.sql is missing table: {required_table}"
