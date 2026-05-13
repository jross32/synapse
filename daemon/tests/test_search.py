"""Contract #21 — search tokeniser + helpers."""

from __future__ import annotations

from synapse_daemon.search import build_search_tokens, tokenise


def test_tokenise_strips_punctuation_and_lowers() -> None:
    assert tokenise("Web-Scraper v2 (alpha)") == ["web", "scraper", "v2", "alpha"]


def test_tokenise_handles_empty() -> None:
    assert tokenise("") == []
    assert tokenise("   ") == []


def test_build_search_tokens_dedups_and_sorts() -> None:
    tokens = build_search_tokens("Web-Scraper", "Web Scraper", tags=["scraping", "tools"])
    assert tokens == sorted(set(tokens))
    assert "scraper" in tokens
    assert "web" in tokens
    assert "scraping" in tokens
    assert "tools" in tokens


def test_build_search_tokens_ignores_none() -> None:
    tokens = build_search_tokens(None, "Cloudtap", None, tags=[])
    assert tokens == ["cloudtap"]
