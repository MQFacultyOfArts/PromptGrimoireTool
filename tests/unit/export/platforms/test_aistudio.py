"""Unit tests for AI Studio platform handler."""

from __future__ import annotations

from promptgrimoire.export.platforms.aistudio import AIStudioHandler


class TestAIStudioHandlerMatches:
    """Tests for AI Studio platform detection."""

    def test_matches_aistudio_html_with_ms_chat_turn(self) -> None:
        """Handler matches HTML containing ms-chat-turn element."""
        handler = AIStudioHandler()
        html = "<ms-chat-turn>Content</ms-chat-turn>"
        assert handler.matches(html) is True

    def test_matches_aistudio_html_with_attributes(self) -> None:
        """Handler matches ms-chat-turn element with attributes."""
        handler = AIStudioHandler()
        html = '<ms-chat-turn data-turn-role="User">Content</ms-chat-turn>'
        assert handler.matches(html) is True

    def test_does_not_match_gemini_html(self) -> None:
        """Handler does not match Gemini exports."""
        handler = AIStudioHandler()
        html = "<user-query>Content</user-query>"
        assert handler.matches(html) is False

    def test_does_not_match_empty_html(self) -> None:
        """Handler does not match empty HTML."""
        handler = AIStudioHandler()
        assert handler.matches("") is False


class TestAIStudioHandlerPreprocess:
    """Tests for AI Studio HTML preprocessing."""

    def test_removes_author_label_elements(self) -> None:
        """Preprocessing removes .author-label elements (native speaker labels)."""
        handler = AIStudioHandler()
        html = """
        <ms-chat-turn data-turn-role="User">
            <div class="author-label">User</div>
            <p>Hello AI Studio!</p>
        </ms-chat-turn>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "author-label" not in result
        assert "Hello AI Studio!" in result

    def test_preserves_conversation_content(self) -> None:
        """Preprocessing preserves actual conversation content."""
        handler = AIStudioHandler()
        html = """
        <ms-chat-turn data-turn-role="User">
            <p>Hello AI Studio!</p>
        </ms-chat-turn>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Hello AI Studio!" in result


class TestAIStudioHandlerTurnMarkers:
    """Tests for AI Studio turn marker patterns."""

    def test_get_turn_markers_returns_user_pattern(self) -> None:
        """Turn markers include user pattern."""
        handler = AIStudioHandler()
        markers = handler.get_turn_markers()
        assert "user" in markers
        assert "data-turn-role" in markers["user"]

    def test_get_turn_markers_returns_assistant_pattern(self) -> None:
        """Turn markers include assistant pattern."""
        handler = AIStudioHandler()
        markers = handler.get_turn_markers()
        assert "assistant" in markers
        assert "data-turn-role" in markers["assistant"]

    def test_user_pattern_matches_user_turn(self) -> None:
        """User pattern matches actual user turn HTML."""
        import re

        handler = AIStudioHandler()
        markers = handler.get_turn_markers()
        html = '<ms-chat-turn data-turn-role="User">Content</ms-chat-turn>'

        match = re.search(markers["user"], html, re.IGNORECASE)
        assert match is not None

    def test_assistant_pattern_matches_assistant_turn(self) -> None:
        """Assistant pattern matches actual assistant turn HTML."""
        import re

        handler = AIStudioHandler()
        markers = handler.get_turn_markers()
        html = '<ms-chat-turn data-turn-role="Model">Content</ms-chat-turn>'

        match = re.search(markers["assistant"], html, re.IGNORECASE)
        assert match is not None
