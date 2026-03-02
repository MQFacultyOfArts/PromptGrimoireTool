"""Unit tests for PDF export word count snitch badge.

Tests _build_word_count_badge() LaTeX generation:
- AC5.3: Over limit -> red fcolorbox with "(Exceeded)"
- AC5.4: Within limits -> neutral italic line
- No limits -> empty string
- Under minimum -> red fcolorbox with "(Below Minimum)"
"""

from __future__ import annotations

from promptgrimoire.export.pdf_export import _build_word_count_badge


class TestBuildWordCountBadge:
    """Tests for _build_word_count_badge() LaTeX snippet generation."""

    def test_over_limit_red_badge(self) -> None:
        """AC5.3: Over limit produces red fcolorbox with '(Exceeded)'."""
        result = _build_word_count_badge(count=1567, word_minimum=None, word_limit=1500)
        assert r"\fcolorbox{red}{red!10}" in result
        assert "Word Count: 1,567 / 1,500 (Exceeded)" in result
        assert r"\textcolor{red}" in result
        assert r"\textbf{" in result

    def test_within_limits_neutral_badge(self) -> None:
        """AC5.4: Within limits produces neutral italic line."""
        result = _build_word_count_badge(count=1234, word_minimum=None, word_limit=1500)
        assert r"\textit{" in result
        assert "Word Count: 1,234 / 1,500" in result
        # Should NOT have red box or violation text
        assert r"\fcolorbox" not in result
        assert "(Exceeded)" not in result
        assert "(Below Minimum)" not in result

    def test_no_limits_empty_string(self) -> None:
        """No limits configured -> empty string (no badge)."""
        result = _build_word_count_badge(count=500, word_minimum=None, word_limit=None)
        assert result == ""

    def test_under_minimum_red_badge(self) -> None:
        """Under minimum produces red fcolorbox with '(Below Minimum)'."""
        result = _build_word_count_badge(count=50, word_minimum=100, word_limit=None)
        assert r"\fcolorbox{red}{red!10}" in result
        assert "Word Count: 50 / 100 (Below Minimum)" in result
        assert r"\textcolor{red}" in result

    def test_at_exactly_limit_red_badge(self) -> None:
        """At exactly limit (count == limit) counts as over."""
        result = _build_word_count_badge(count=1500, word_minimum=None, word_limit=1500)
        assert r"\fcolorbox{red}{red!10}" in result
        assert "(Exceeded)" in result

    def test_at_exactly_minimum_neutral(self) -> None:
        """At exactly minimum is OK, produces neutral badge."""
        result = _build_word_count_badge(count=100, word_minimum=100, word_limit=200)
        assert r"\textit{" in result
        assert "(Exceeded)" not in result
        assert "(Below Minimum)" not in result

    def test_both_limits_within_range(self) -> None:
        """Within both min and max -> neutral badge showing max."""
        result = _build_word_count_badge(count=150, word_minimum=100, word_limit=200)
        assert r"\textit{" in result
        assert "Word Count: 150 / 200" in result

    def test_badge_has_vspace(self) -> None:
        """Badge includes vertical spacing for separation from body text."""
        result = _build_word_count_badge(count=100, word_minimum=None, word_limit=200)
        assert r"\vspace{1em}" in result

    def test_minimum_only_neutral_within(self) -> None:
        """Minimum-only config, within limits -> neutral badge showing minimum."""
        result = _build_word_count_badge(count=150, word_minimum=100, word_limit=None)
        assert r"\textit{" in result
        assert "Word Count: 150 / 100" in result
        assert r"\fcolorbox" not in result
