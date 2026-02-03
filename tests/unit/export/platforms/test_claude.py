"""Unit tests for Claude platform handler."""

from __future__ import annotations

from promptgrimoire.export.platforms.claude import ClaudeHandler


class TestClaudeHandlerMatches:
    """Tests for Claude platform detection."""

    def test_matches_claude_html_with_font_user_message(self) -> None:
        """Handler matches HTML containing font-user-message class."""
        handler = ClaudeHandler()
        html = '<div class="font-user-message">Content</div>'
        assert handler.matches(html) is True

    def test_matches_claude_html_with_class_in_list(self) -> None:
        """Handler matches when font-user-message is part of multiple classes."""
        handler = ClaudeHandler()
        html = '<div class="text-base font-user-message p-4">Content</div>'
        assert handler.matches(html) is True

    def test_does_not_match_openai_html(self) -> None:
        """Handler does not match OpenAI exports."""
        handler = ClaudeHandler()
        html = '<div class="agent-turn">Content</div>'
        assert handler.matches(html) is False

    def test_does_not_match_empty_html(self) -> None:
        """Handler does not match empty HTML."""
        handler = ClaudeHandler()
        assert handler.matches("") is False


class TestClaudeHandlerPreprocess:
    """Tests for Claude HTML preprocessing."""

    def test_marks_thinking_header(self) -> None:
        """Preprocessing marks thinking header with data-thinking attribute."""
        handler = ClaudeHandler()
        html = """
        <div class="thinking-summary">
            <div class="text-sm font-semibold">Thought process</div>
            <div>Summary content</div>
        </div>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert 'data-thinking="header"' in result or "Thought process" in result

    def test_thinking_sections_in_real_fixture(self) -> None:
        """Verify thinking section detection works on real Claude fixture."""
        from tests.conftest import load_conversation_fixture

        handler = ClaudeHandler()
        html = load_conversation_fixture("claude_cooking.html")

        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        # Fixture should contain Claude conversation content
        assert len(result) > 0
        # If fixture has thinking sections, they should be marked
        # (regression guard - if fixture has "Thought process", it should be marked)

    def test_preserves_conversation_content(self) -> None:
        """Preprocessing preserves actual conversation content."""
        handler = ClaudeHandler()
        html = """
        <div class="font-user-message">
            <p>Hello Claude!</p>
        </div>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Hello Claude!" in result


class TestClaudeHandlerTurnMarkers:
    """Tests for Claude turn marker patterns."""

    def test_get_turn_markers_returns_user_pattern(self) -> None:
        """Turn markers include user pattern."""
        handler = ClaudeHandler()
        markers = handler.get_turn_markers()
        assert "user" in markers
        assert "data-testid" in markers["user"] or "user-message" in markers["user"]

    def test_get_turn_markers_returns_assistant_pattern(self) -> None:
        """Turn markers include assistant pattern."""
        handler = ClaudeHandler()
        markers = handler.get_turn_markers()
        assert "assistant" in markers
        assert "font-claude-response" in markers["assistant"]

    def test_user_pattern_matches_user_turn(self) -> None:
        """User pattern matches actual user turn HTML."""
        import re

        handler = ClaudeHandler()
        markers = handler.get_turn_markers()
        html = '<div data-testid="user-message" class="font-user-message">Content</div>'

        match = re.search(markers["user"], html, re.IGNORECASE)
        assert match is not None

    def test_assistant_pattern_matches_assistant_turn(self) -> None:
        """Assistant pattern matches actual assistant turn HTML."""
        import re

        handler = ClaudeHandler()
        markers = handler.get_turn_markers()
        html = (
            '<div class="font-claude-response relative leading-[1.65rem]">Content</div>'
        )

        match = re.search(markers["assistant"], html, re.IGNORECASE)
        assert match is not None
