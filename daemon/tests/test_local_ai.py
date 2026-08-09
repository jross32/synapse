"""Tests for the local-AI layer.

Deliberately hermetic: nothing here talks to Ollama or loads a model, because a test that
needs a 5 GB download and a GPU is a test nobody runs. The parts worth protecting are the
permission gating, the workspace containment boundary, and the chat storage - all of which
are pure logic and all of which would be dangerous to get wrong.
"""

from __future__ import annotations

import asyncio

import pytest

from synapse_daemon import local_chat, local_models
from synapse_daemon.storage import Storage
from synapse_daemon.local_agent import (
    TOOL_REQUIRED_ARGS,
    MODE_TOOLS,
    PermissionMode,
    Workspace,
    build_tools,
    missing_args,
)


# ---------------------------------------------------------------- permission modes


def test_plan_mode_offers_no_mutating_tools():
    """Plan mode must not even show write_file or run_command.

    A tool that is never offered cannot be misused, which is the whole point of enforcing
    at the tool layer instead of asking the model to behave.
    """
    names = {t["function"]["name"] for t in build_tools(PermissionMode.PLAN, allow_web=True)}
    assert "write_file" not in names
    assert "run_command" not in names
    assert "read_file" in names


def test_accept_edits_allows_files_but_not_shell():
    names = {t["function"]["name"]
             for t in build_tools(PermissionMode.ACCEPT_EDITS, allow_web=False)}
    assert "write_file" in names
    assert "run_command" not in names


def test_web_tools_are_independent_of_mode():
    """Network access is orthogonal: plan mode may still need to read documentation."""
    with_web = {t["function"]["name"] for t in build_tools(PermissionMode.PLAN, allow_web=True)}
    without = {t["function"]["name"] for t in build_tools(PermissionMode.PLAN, allow_web=False)}
    assert "web_search" in with_web
    assert "web_search" not in without


def test_every_mode_has_a_tool_set():
    for mode in PermissionMode:
        assert mode in MODE_TOOLS, f"{mode} has no tool policy"


# ---------------------------------------------------------------- workspace containment


def test_workspace_blocks_escape(tmp_path):
    ws = Workspace(tmp_path)
    with pytest.raises(ValueError) as exc:
        ws.read_file("../../etc/passwd")
    # The message must tell the model what to do instead, or it loops inventing new
    # absolute paths rather than correcting the shape.
    assert "relative" in str(exc.value).lower()


def test_workspace_blocks_absolute_paths(tmp_path):
    ws = Workspace(tmp_path)
    with pytest.raises(ValueError):
        ws.write_file("/etc/hosts", "nope")


def test_workspace_roundtrip(tmp_path):
    ws = Workspace(tmp_path)
    ws.write_file("sub/hello.py", "print('hi')")
    assert "print('hi')" in ws.read_file("sub/hello.py")
    assert "hello.py" in ws.list_dir("sub")


def test_shell_disabled_by_default(tmp_path):
    ws = Workspace(tmp_path, allow_shell=False)
    assert "disabled" in ws.run_command("echo hi").lower()


def test_destructive_command_refused_unless_bypass(tmp_path):
    guarded = Workspace(tmp_path, allow_shell=True, allow_destructive=False)
    assert "refused" in guarded.run_command("rm -rf /").lower()


# ---------------------------------------------------------------- tool argument help


def test_missing_args_named_so_the_model_can_correct():
    assert missing_args("write_file", {"path": "a.py"}) == ["content"]
    assert missing_args("write_file", {"path": "a.py", "content": "x"}) == []


def test_every_offered_tool_declares_its_required_args():
    for mode in PermissionMode:
        for spec in build_tools(mode, allow_web=True):
            assert spec["function"]["name"] in TOOL_REQUIRED_ARGS


# ---------------------------------------------------------------- hardware profile


def test_hardware_profile_is_always_answerable():
    """Must degrade to a truthful answer on a machine with no GPU rather than raise."""
    hw = local_models.detect_hardware()
    assert hw.os
    assert hw.vram_gb >= 0
    if not hw.gpus:
        assert any("CPU" in n for n in hw.notes)


def test_role_recommendations_cover_every_role():
    roles = {r.role for r in local_models.recommend_for_roles()}
    assert roles == set(local_models.ROLE_TASKS)


def test_summary_for_ai_has_usage_instructions():
    """An AI reading /ai/context needs to know how to actually call these models."""
    summary = local_models.summarize_for_ai()
    assert "how_to_use" in summary
    assert "11434" in summary["how_to_use"]


# ---------------------------------------------------------------- chat titles


@pytest.mark.parametrize(("prompt", "expected"), [
    ("please add a login page", "Add a login page"),
    ("can you fix the header bug", "Fix the header bug"),
    ("", "New chat"),
])
def test_title_from_prompt_reads_like_a_subject(prompt, expected):
    assert local_chat.title_from_prompt(prompt) == expected


def test_long_titles_are_truncated_on_a_word_boundary():
    title = local_chat.title_from_prompt("build " + "a really long description " * 10)
    assert len(title) <= 63
    assert title.endswith("...")


# ---------------------------------------------------------------- chat storage


@pytest.fixture()
def storage(tmp_path):
    """A real migrated database on disk - the chat tables only exist after migration 031,
    so an in-memory stub would test nothing."""
    store = Storage(tmp_path / "data")
    store.open()
    store.migrate()
    try:
        yield store
    finally:
        store.close()



def test_chat_crud_roundtrip(storage):
    chat = local_chat.create_chat(storage.conn, model="qwen2.5:1.5b",
                                  first_prompt="add a login page")
    assert chat.title == "Add a login page"

    local_chat.append_message(storage.conn, chat.id, "user", "add a login page")
    local_chat.append_message(storage.conn, chat.id, "assistant", "done")
    msgs = local_chat.get_messages(storage.conn, chat.id)
    assert [m.seq for m in msgs] == [0, 1]
    assert [m.role for m in msgs] == ["user", "assistant"]

    assert local_chat.get_chat(storage.conn, chat.id).message_count == 2
    assert chat.id in {c.id for c in local_chat.list_chats(storage.conn)}

    local_chat.rename_chat(storage.conn, chat.id, "Renamed")
    assert local_chat.get_chat(storage.conn, chat.id).title == "Renamed"

    local_chat.archive_chat(storage.conn, chat.id)
    assert chat.id not in {c.id for c in local_chat.list_chats(storage.conn)}
    assert chat.id in {c.id for c in local_chat.list_chats(storage.conn, include_archived=True)}

    local_chat.delete_chat(storage.conn, chat.id)
    assert local_chat.get_chat(storage.conn, chat.id) is None


def test_deleting_a_chat_takes_its_messages(storage):
    chat = local_chat.create_chat(storage.conn, model="m", first_prompt="hi")
    local_chat.append_message(storage.conn, chat.id, "user", "hi")
    local_chat.delete_chat(storage.conn, chat.id)
    assert local_chat.get_messages(storage.conn, chat.id) == []


# ---------------------------------------------------------------- vram fit


def test_vram_estimate_matches_what_was_actually_measured():
    """The 7B/6 GB case is the one that matters, and it was measured, not guessed.

    Every 7B model in benchmarks/local-models/REPORT.md spilled to CPU on this card and
    collapsed to ~6 tok/s. The estimator must independently reach the same verdict, or it
    will happily recommend a download that cannot run well.
    """
    seven_b = local_models.estimate_vram_fit(4.68, 6.0, 4096)
    assert seven_b["fits"] is False
    assert seven_b["headroom_gb"] < 0

    three_b = local_models.estimate_vram_fit(2.02, 6.0, 4096)
    assert three_b["fits"] is True


def test_a_7b_fits_once_the_context_is_small_enough():
    """Refusing outright would be wrong: the cache, not the weights, is what overflows."""
    assert local_models.estimate_vram_fit(4.68, 6.0, 1024)["fits"] is True


def test_max_context_is_solved_for_not_scaled_from_the_request():
    """max_context answers "how much can I have", so it must not depend on what was asked."""
    a = local_models.estimate_vram_fit(2.02, 6.0, 512)["max_context"]
    b = local_models.estimate_vram_fit(2.02, 6.0, 8192)["max_context"]
    assert a == b
    assert a % 512 == 0


def test_a_model_too_big_for_the_card_reports_no_context_at_all():
    r = local_models.estimate_vram_fit(20.0, 6.0, 4096)
    assert r["fits"] is False
    assert r["max_context"] == 0


@pytest.mark.parametrize("bad", [(0, 6.0, 4096), (4.0, 0, 4096), (4.0, 6.0, 0)])
def test_vram_estimate_rejects_impossible_input(bad):
    with pytest.raises(ValueError):
        local_models.estimate_vram_fit(*bad)
