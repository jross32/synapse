"""Pure helpers in ai_context_memory (the shared cross-AI memory module) -- previously untested.

work_item_title_slug / _context_excerpt / _rotate_if_needed had no direct coverage even though
they shape filenames, the prompt context window, and log rotation for every squad run.
"""

from __future__ import annotations

from pathlib import Path

from synapse_daemon.ai_context_memory import (
    AI_CONTEXT_ARCHIVE_PREFIX,
    AI_CONTEXT_ROTATE_BYTES,
    _context_excerpt,
    _rotate_if_needed,
    work_item_title_slug,
)


# ---- work_item_title_slug -------------------------------------------------

def test_slug_basic_lowercase_and_separators() -> None:
    assert work_item_title_slug("Fix the Login Bug!") == "fix-the-login-bug"


def test_slug_collapses_runs_of_separators() -> None:
    assert work_item_title_slug("a   b__c//d") == "a-b-c-d"


def test_slug_strips_leading_and_trailing_separators() -> None:
    assert work_item_title_slug("  !!hello!!  ") == "hello"


def test_slug_empty_and_all_separators_fall_back() -> None:
    assert work_item_title_slug("") == "work-item"
    assert work_item_title_slug("***///") == "work-item"


def test_slug_truncates_to_48_chars() -> None:
    out = work_item_title_slug("x" * 100)
    assert out == "x" * 48
    assert len(out) <= 48


# ---- _context_excerpt -----------------------------------------------------

def test_excerpt_missing_file(tmp_path: Path) -> None:
    assert "No project AI context" in _context_excerpt(tmp_path / "nope.md", "standard")


def test_excerpt_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "ctx.md"
    p.write_text("   \n  ", encoding="utf-8")
    assert "empty" in _context_excerpt(p, "standard").lower()


def test_excerpt_short_text_returned_whole(tmp_path: Path) -> None:
    p = tmp_path / "ctx.md"
    p.write_text("hello world", encoding="utf-8")
    assert _context_excerpt(p, "standard") == "hello world"


def test_excerpt_returns_newest_tail_when_over_cap(tmp_path: Path) -> None:
    p = tmp_path / "ctx.md"
    # Oldest content first (appended newest-last), so the tail is the newest.
    p.write_text("OLDEST_MARKER\n" + ("filler " * 3000) + "\nNEWEST_MARKER", encoding="utf-8")
    excerpt = _context_excerpt(p, "minimal")  # cap 1200
    assert len(excerpt) <= 1200
    assert "NEWEST_MARKER" in excerpt
    assert "OLDEST_MARKER" not in excerpt


def test_excerpt_cap_scales_with_mode(tmp_path: Path) -> None:
    p = tmp_path / "ctx.md"
    p.write_text("z" * 8000, encoding="utf-8")
    assert len(_context_excerpt(p, "minimal")) == 1200
    assert len(_context_excerpt(p, "standard")) == 3000
    assert len(_context_excerpt(p, "full")) == 7000
    # Unknown mode falls back to the standard cap.
    assert len(_context_excerpt(p, "bogus")) == 3000


# ---- _rotate_if_needed ----------------------------------------------------

def test_rotate_noop_when_missing(tmp_path: Path) -> None:
    # Must not raise on a nonexistent path.
    _rotate_if_needed(tmp_path / "absent.md")


def test_rotate_noop_when_small(tmp_path: Path) -> None:
    p = tmp_path / "ctx.md"
    p.write_text("small", encoding="utf-8")
    _rotate_if_needed(p)
    assert p.read_text(encoding="utf-8") == "small"
    assert not list(tmp_path.glob(f"{AI_CONTEXT_ARCHIVE_PREFIX}*"))


def test_rotate_archives_when_over_threshold(tmp_path: Path) -> None:
    p = tmp_path / "ctx.md"
    p.write_text("A" * (AI_CONTEXT_ROTATE_BYTES + 10), encoding="utf-8")
    _rotate_if_needed(p)
    archives = list(tmp_path.glob(f"{AI_CONTEXT_ARCHIVE_PREFIX}*.md"))
    assert len(archives) == 1
    assert archives[0].read_text(encoding="utf-8").startswith("A" * 100)
    # A fresh context file is written with a rotation header (old bulk content gone).
    fresh = p.read_text(encoding="utf-8")
    assert "rotated" in fresh.lower()
    assert "A" * 100 not in fresh
