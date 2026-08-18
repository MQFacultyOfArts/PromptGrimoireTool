"""Tests for scripts/analyse_fixture.py fixture resolution.

Covers ``_load_fixture``'s three resolution strategies -- direct path, exact
name match, and unique substring match -- after decomposing it into smaller
helpers (see ``docs/design-plans/2026-04-23-ty-sa-typing-cleanup.md``).
"""

from __future__ import annotations

import gzip
from typing import TYPE_CHECKING

from scripts import analyse_fixture

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_load_fixture_resolves_path_name_and_substring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Synthetic input -> (display_name, html_content) shape for each path."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    monkeypatch.setattr(analyse_fixture, "FIXTURES_DIR", fixtures_dir)

    plain = fixtures_dir / "alpha_debug.html"
    plain.write_text("<p>alpha content</p>", encoding="utf-8")

    gz_path = fixtures_dir / "beta_debug.html.gz"
    with gzip.open(gz_path, "wt", encoding="utf-8") as f:
        f.write("<p>beta content</p>")

    # Exact name match, plain HTML.
    name, html = analyse_fixture._load_fixture("alpha_debug")
    assert (name, html) == ("alpha_debug", "<p>alpha content</p>")

    # Exact name match, gzip-compressed -- transparent decompression.
    name, html = analyse_fixture._load_fixture("beta_debug")
    assert (name, html) == ("beta_debug", "<p>beta content</p>")

    # Unique substring match.
    name, html = analyse_fixture._load_fixture("alpha")
    assert (name, html) == ("alpha_debug", "<p>alpha content</p>")

    # Direct filesystem path, outside FIXTURES_DIR entirely.
    direct = tmp_path / "elsewhere.html"
    direct.write_text("<p>direct content</p>", encoding="utf-8")
    name, html = analyse_fixture._load_fixture(str(direct))
    assert (name, html) == ("elsewhere", "<p>direct content</p>")
