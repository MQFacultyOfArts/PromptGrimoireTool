"""Unit tests for Gemini platform handler."""

from __future__ import annotations

from promptgrimoire.export.platforms.gemini import GeminiHandler


class TestGeminiHandlerMatches:
    """Tests for Gemini platform detection."""

    def test_matches_gemini_html_with_user_query_element(self) -> None:
        """Handler matches HTML containing user-query element."""
        handler = GeminiHandler()
        html = "<user-query>Content</user-query>"
        assert handler.matches(html) is True

    def test_matches_gemini_html_with_attributes(self) -> None:
        """Handler matches user-query element with attributes."""
        handler = GeminiHandler()
        html = '<user-query class="query" data-id="1">Content</user-query>'
        assert handler.matches(html) is True

    def test_does_not_match_openai_html(self) -> None:
        """Handler does not match OpenAI exports."""
        handler = GeminiHandler()
        html = '<div class="agent-turn">Content</div>'
        assert handler.matches(html) is False

    def test_does_not_match_empty_html(self) -> None:
        """Handler does not match empty HTML."""
        handler = GeminiHandler()
        assert handler.matches("") is False


class TestGeminiHandlerPreprocess:
    """Tests for Gemini HTML preprocessing."""

    def test_preserves_conversation_content(self) -> None:
        """Preprocessing preserves actual conversation content."""
        handler = GeminiHandler()
        html = """
        <user-query>Hello Gemini!</user-query>
        <model-response>Hello! How can I help?</model-response>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Hello Gemini!" in result
        assert "Hello! How can I help?" in result


class TestGeminiHandlerTurnMarkers:
    """Tests for Gemini turn marker patterns."""

    def test_get_turn_markers_returns_user_pattern(self) -> None:
        """Turn markers include user pattern."""
        handler = GeminiHandler()
        markers = handler.get_turn_markers()
        assert "user" in markers
        assert "user-query" in markers["user"]

    def test_get_turn_markers_returns_assistant_pattern(self) -> None:
        """Turn markers include assistant pattern."""
        handler = GeminiHandler()
        markers = handler.get_turn_markers()
        assert "assistant" in markers
        assert "model-response" in markers["assistant"]

    def test_user_pattern_matches_user_turn(self) -> None:
        """User pattern matches actual user turn HTML."""
        import re

        handler = GeminiHandler()
        markers = handler.get_turn_markers()
        html = '<user-query class="query">Content</user-query>'

        match = re.search(markers["user"], html, re.IGNORECASE)
        assert match is not None

    def test_assistant_pattern_matches_assistant_turn(self) -> None:
        """Assistant pattern matches actual assistant turn HTML."""
        import re

        handler = GeminiHandler()
        markers = handler.get_turn_markers()
        html = "<model-response>Content</model-response>"

        match = re.search(markers["assistant"], html, re.IGNORECASE)
        assert match is not None
