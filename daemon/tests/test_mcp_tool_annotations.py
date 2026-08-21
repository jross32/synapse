"""Every advertised tool must tell an MCP client whether it is safe to call unconfirmed.

Found by investigating a real report: ChatGPT could see and list all 24 write-mode tools but
denied every call. Per OpenAI's own documentation, a tool with no `annotations.readOnlyHint`
is treated as a write action needing confirmation - and none of these tools carried one, so
even the plain listing/reading tools were gated as if they were dangerous. These tests pin
the classification, not just its presence: getting one wrong in the permissive direction
(marking a real write `readOnlyHint: true`) is a safety regression, not a cosmetic one.
"""

from __future__ import annotations

from synapse_daemon.mcp_connector import _TOOL_ANNOTATIONS, _tool_specs

# Tools that genuinely cannot change state on this machine, matched against the actual
# handler logic in mcp_connector.py - not just "sounds like a getter".
EXPECTED_READ_ONLY = {
    "synapse_get_context",
    "synapse_list_projects",
    "synapse_get_project_records",
    "synapse_get_project_ai_context",
    "synapse_list_tools",
    "synapse_list_quick_actions",
    "synapse_list_skill_packs",
    "synapse_get_skill_pack",
    "synapse_list_agent_squads",
    "synapse_list_sessions",
    "synapse_recent_activity",
    "synapse_quality_summary",
    "synapse_runtime_status",
    "synapse_list_blueprints",
    "synapse_list_mcp_tools",
    "synapse_read_file",
    "synapse_watch_repo",
    "synapse_launch_work_item",  # looks up + returns instructions, does not itself launch
    "synapse_web_search",  # reaches the public internet, but changes nothing anywhere
}

# Tools whose handlers demonstrably write, execute, or proxy to something that can - these
# must NEVER be readOnlyHint: true, however convenient that would be for getting past a
# client's confirmation step.
EXPECTED_NOT_READ_ONLY = {
    "synapse_add_project_idea",
    "synapse_capture_note",
    "synapse_create_squad",
    "synapse_add_work_item",
    "synapse_delegate_module",
    "synapse_write_file",
    "synapse_run_command",
    "synapse_http",
    "synapse_call_mcp_tool",
}

# The tools most worth getting right: run arbitrary shell, or proxy to something that can.
EXPECTED_DESTRUCTIVE = {"synapse_run_command", "synapse_http", "synapse_call_mcp_tool",
                        "synapse_delegate_module", "synapse_write_file"}


def test_every_advertised_tool_has_annotations():
    specs = _tool_specs(allow_writes=True)
    missing = [s["name"] for s in specs if "annotations" not in s]
    assert not missing, f"advertised with no annotations at all: {missing}"
    for spec in specs:
        assert isinstance(spec["annotations"].get("readOnlyHint"), bool), (
            f"{spec['name']}: readOnlyHint must be an explicit bool, not absent")


def test_readonly_classification_matches_what_the_handler_does():
    specs = {s["name"]: s for s in _tool_specs(allow_writes=True)}
    assert set(specs) >= EXPECTED_READ_ONLY | EXPECTED_NOT_READ_ONLY, (
        "a tool was added or renamed without updating this test's expectations")

    for name in EXPECTED_READ_ONLY:
        assert specs[name]["annotations"]["readOnlyHint"] is True, (
            f"{name} should be readOnlyHint: true - its handler never mutates state")
    for name in EXPECTED_NOT_READ_ONLY:
        assert specs[name]["annotations"]["readOnlyHint"] is False, (
            f"{name} must NOT be readOnlyHint: true - its handler writes, executes, or "
            f"proxies to something that can. A client that skips confirmation because of "
            f"a wrong hint here is the actual safety bug.")


def test_dangerous_tools_are_marked_destructive_not_softened():
    """Nobody gets to look safer than they are to get past a client's safety layer."""
    specs = {s["name"]: s for s in _tool_specs(allow_writes=True)}
    for name in EXPECTED_DESTRUCTIVE:
        assert specs[name]["annotations"].get("destructiveHint") is True, (
            f"{name} can overwrite or execute arbitrary things and must say so")


def test_the_read_only_connector_url_only_ever_advertises_read_only_tools():
    """`?mode=read` tools must all be readOnlyHint: true - that is the whole point of the URL."""
    specs = _tool_specs(allow_writes=False)
    for spec in specs:
        assert spec["annotations"]["readOnlyHint"] is True, (
            f"{spec['name']} is on the read-only surface but is not annotated read-only")


def test_annotation_table_has_no_orphans():
    """An entry for a tool that no longer exists is a stale claim, not a harmless leftover."""
    real_names = {s["name"] for s in _tool_specs(allow_writes=True)}
    stale = set(_TOOL_ANNOTATIONS) - real_names
    assert not stale, f"annotations exist for tools that are no longer advertised: {stale}"
