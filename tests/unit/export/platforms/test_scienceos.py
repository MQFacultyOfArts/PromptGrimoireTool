"""Unit tests for ScienceOS platform handler."""

from __future__ import annotations

from promptgrimoire.export.platforms.scienceos import ScienceOSHandler


class TestScienceOSHandlerMatches:
    """Tests for ScienceOS platform detection."""

    def test_matches_scienceos_html_with_prompt_class(self) -> None:
        """Handler matches HTML containing _prompt_ class pattern."""
        handler = ScienceOSHandler()
        html = '<div class="_prompt_abc123">Content</div>'
        assert handler.matches(html) is True

    def test_matches_scienceos_html_with_class_in_list(self) -> None:
        """Handler matches when _prompt_ class is part of multiple classes."""
        handler = ScienceOSHandler()
        html = '<div class="mantine-Text _prompt_xyz789 other">Content</div>'
        assert handler.matches(html) is True

    def test_matches_scienceos_html_with_tabler_icon(self) -> None:
        """Handler matches HTML containing tabler-icon-robot-face."""
        handler = ScienceOSHandler()
        html = '<svg class="tabler-icon tabler-icon-robot-face">...</svg>'
        assert handler.matches(html) is True

    def test_does_not_match_openai_html(self) -> None:
        """Handler does not match OpenAI exports."""
        handler = ScienceOSHandler()
        html = '<div class="agent-turn">Content</div>'
        assert handler.matches(html) is False

    def test_does_not_match_empty_html(self) -> None:
        """Handler does not match empty HTML."""
        handler = ScienceOSHandler()
        assert handler.matches("") is False


class TestScienceOSHandlerPreprocess:
    """Tests for ScienceOS HTML preprocessing."""

    def test_preserves_conversation_content(self) -> None:
        """Preprocessing preserves actual conversation content."""
        handler = ScienceOSHandler()
        html = """
        <div class="_prompt_abc123">
            <p>Research query</p>
        </div>
        <div class="_markdown_def456">
            <p>Research results</p>
        </div>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Research query" in result
        assert "Research results" in result


class TestScienceOSHandlerTurnMarkers:
    """Tests for ScienceOS turn marker patterns."""

    def test_get_turn_markers_returns_user_pattern(self) -> None:
        """Turn markers include user pattern."""
        handler = ScienceOSHandler()
        markers = handler.get_turn_markers()
        assert "user" in markers
        assert "_prompt_" in markers["user"]

    def test_get_turn_markers_returns_assistant_pattern(self) -> None:
        """Turn markers include assistant pattern."""
        handler = ScienceOSHandler()
        markers = handler.get_turn_markers()
        assert "assistant" in markers
        assert "_markdown_" in markers["assistant"]

    def test_user_pattern_matches_user_turn(self) -> None:
        """User pattern matches actual user turn HTML."""
        import re

        handler = ScienceOSHandler()
        markers = handler.get_turn_markers()
        html = '<div class="_prompt_abc123">Content</div>'

        match = re.search(markers["user"], html, re.IGNORECASE)
        assert match is not None

    def test_assistant_pattern_matches_assistant_turn(self) -> None:
        """Assistant pattern matches actual assistant turn HTML."""
        import re

        handler = ScienceOSHandler()
        markers = handler.get_turn_markers()
        html = '<div class="_markdown_def456">Content</div>'

        match = re.search(markers["assistant"], html, re.IGNORECASE)
        assert match is not None
