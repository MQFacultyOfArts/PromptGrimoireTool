"""Unit tests for OpenAI platform handler."""

from __future__ import annotations

from promptgrimoire.export.platforms.openai import OpenAIHandler


class TestOpenAIHandlerMatches:
    """Tests for OpenAI platform detection."""

    def test_matches_openai_html_with_agent_turn_class(self) -> None:
        """Handler matches HTML containing agent-turn class."""
        handler = OpenAIHandler()
        html = '<div class="agent-turn">Content</div>'
        assert handler.matches(html) is True

    def test_matches_openai_html_with_agent_turn_in_class_list(self) -> None:
        """Handler matches when agent-turn is part of multiple classes."""
        handler = OpenAIHandler()
        html = (
            '<article class="w-full text-token-text-primary agent-turn">'
            "Content</article>"
        )
        assert handler.matches(html) is True

    def test_does_not_match_claude_html(self) -> None:
        """Handler does not match Claude exports."""
        handler = OpenAIHandler()
        html = '<div class="font-claude-message">Content</div>'
        assert handler.matches(html) is False

    def test_does_not_match_empty_html(self) -> None:
        """Handler does not match empty HTML."""
        handler = OpenAIHandler()
        assert handler.matches("") is False
        assert handler.matches("<html></html>") is False


class TestOpenAIHandlerPreprocess:
    """Tests for OpenAI HTML preprocessing."""

    def test_removes_sr_only_elements(self) -> None:
        """Preprocessing removes screen-reader-only elements."""
        handler = OpenAIHandler()
        html = """
        <article>
            <h5 class="sr-only">You said:</h5>
            <div>User message content</div>
        </article>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "sr-only" not in result
        assert "You said:" not in result
        assert "User message content" in result

    def test_removes_chatgpt_label(self) -> None:
        """Preprocessing removes ChatGPT assistant labels."""
        handler = OpenAIHandler()
        html = """
        <article>
            <h5 class="sr-only">ChatGPT</h5>
            <div>Assistant response</div>
        </article>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "ChatGPT" not in result
        assert "Assistant response" in result

    def test_preserves_conversation_content(self) -> None:
        """Preprocessing preserves actual conversation content."""
        handler = OpenAIHandler()
        html = """
        <div class="agent-turn">
            <div data-message-author-role="user">
                <p>Hello, how are you?</p>
            </div>
        </div>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Hello, how are you?" in result


class TestOpenAIHandlerTurnMarkers:
    """Tests for OpenAI turn marker patterns."""

    def test_get_turn_markers_returns_user_pattern(self) -> None:
        """Turn markers include user pattern."""
        handler = OpenAIHandler()
        markers = handler.get_turn_markers()
        assert "user" in markers
        assert "data-message-author-role" in markers["user"]

    def test_get_turn_markers_returns_assistant_pattern(self) -> None:
        """Turn markers include assistant pattern."""
        handler = OpenAIHandler()
        markers = handler.get_turn_markers()
        assert "assistant" in markers
        assert "data-message-author-role" in markers["assistant"]

    def test_user_pattern_matches_user_turn(self) -> None:
        """User pattern matches actual user turn HTML."""
        import re

        handler = OpenAIHandler()
        markers = handler.get_turn_markers()
        html = '<div data-message-author-role="user" class="other">Content</div>'

        match = re.search(markers["user"], html, re.IGNORECASE)
        assert match is not None

    def test_assistant_pattern_matches_assistant_turn(self) -> None:
        """Assistant pattern matches actual assistant turn HTML."""
        import re

        handler = OpenAIHandler()
        markers = handler.get_turn_markers()
        html = '<div data-message-author-role="assistant">Content</div>'

        match = re.search(markers["assistant"], html, re.IGNORECASE)
        assert match is not None
