"""Unit tests for OpenRouter platform handler."""

from __future__ import annotations

from promptgrimoire.export.platforms.openrouter import OpenRouterHandler


class TestOpenRouterHandlerMatches:
    """Tests for OpenRouter platform detection."""

    def test_matches_openrouter_html_with_playground_container(self) -> None:
        """Handler matches HTML containing data-testid="playground-container"."""
        handler = OpenRouterHandler()
        html = '<div data-testid="playground-container">Content</div>'
        assert handler.matches(html) is True

    def test_matches_openrouter_html_with_other_attributes(self) -> None:
        """Detection works even with other attributes on the element."""
        handler = OpenRouterHandler()
        html = (
            '<div class="flex h-full" data-testid="playground-container"'
            ' id="main">Content</div>'
        )
        assert handler.matches(html) is True

    def test_does_not_match_claude_html(self) -> None:
        """Handler does not match Claude exports."""
        handler = OpenRouterHandler()
        html = '<div class="font-user-message">Content</div>'
        assert handler.matches(html) is False

    def test_does_not_match_openai_html(self) -> None:
        """Handler does not match OpenAI exports."""
        handler = OpenRouterHandler()
        html = '<article class="agent-turn">Content</article>'
        assert handler.matches(html) is False

    def test_does_not_match_gemini_html(self) -> None:
        """Handler does not match Gemini exports."""
        handler = OpenRouterHandler()
        html = "<user-query>What is 2+2?</user-query><model-response>4</model-response>"
        assert handler.matches(html) is False

    def test_does_not_match_chatcraft_html(self) -> None:
        """Handler does not match ChatCraft exports."""
        handler = OpenRouterHandler()
        html = (
            '<div class="chakra-card">'
            '<a href="https://chatcraft.org">ChatCraft</a>'
            "Content</div>"
        )
        assert handler.matches(html) is False

    def test_does_not_match_empty_html(self) -> None:
        """Handler does not match empty or minimal HTML."""
        handler = OpenRouterHandler()
        assert handler.matches("") is False
        assert handler.matches("<html></html>") is False


class TestOpenRouterHandlerPreprocess:
    """Tests for OpenRouter HTML preprocessing."""

    def test_removes_playground_composer(self) -> None:
        """Preprocessing removes element with data-testid="playground-composer"."""
        handler = OpenRouterHandler()
        html = """
        <div data-testid="playground-container">
            <div data-testid="user-message">Hello</div>
            <div data-testid="assistant-message">Hi there</div>
            <div data-testid="playground-composer">
                <textarea>Type a message...</textarea>
            </div>
        </div>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "playground-composer" not in result
        assert "Type a message" not in result

    def test_preserves_conversation_content(self) -> None:
        """Preprocessing preserves actual conversation content."""
        handler = OpenRouterHandler()
        html = """
        <div data-testid="playground-container">
            <div data-testid="user-message">
                <p>What is the capital of France?</p>
            </div>
            <div data-testid="assistant-message">
                <p>The capital of France is Paris.</p>
            </div>
            <div data-testid="playground-composer">
                <textarea></textarea>
            </div>
        </div>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "What is the capital of France?" in result
        assert "The capital of France is Paris." in result

    def test_strips_metadata_row_from_assistant_messages(self) -> None:
        """Metadata row (timestamp, model name, badge) is removed."""
        handler = OpenRouterHandler()
        html = """
        <div data-testid="assistant-message">
            <div class="text-xs text-gray-500 mb-1">
                <span>5 seconds ago</span>
                <span class="font-medium">Qwen3.5-35B-A3B</span>
                <span class="text-blue-600">Reasoning</span>
            </div>
            <div class="prose"><p>The answer is 42.</p></div>
        </div>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "5 seconds ago" not in result
        assert "Reasoning" not in result
        assert "The answer is 42." in result

    def test_sets_data_speaker_name_from_model(self) -> None:
        """Model name from metadata is folded into data-speaker-name."""
        handler = OpenRouterHandler()
        html = """
        <div data-testid="assistant-message">
            <div class="text-xs text-gray-500">
                <span>5 seconds ago</span>
                <span class="font-medium">Qwen3.5-35B-A3B</span>
            </div>
            <p>Response</p>
        </div>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)

        msgs = tree.css('[data-testid="assistant-message"]')
        assert len(msgs) == 1
        assert msgs[0].attributes.get("data-speaker-name") == "Qwen3.5-35B-A3B"


class TestOpenRouterHandlerTurnMarkers:
    """Tests for OpenRouter turn marker patterns."""

    def test_get_turn_markers_returns_user_pattern(self) -> None:
        """Turn markers include user key."""
        handler = OpenRouterHandler()
        markers = handler.get_turn_markers()
        assert "user" in markers

    def test_get_turn_markers_returns_assistant_pattern(self) -> None:
        """Turn markers include assistant key."""
        handler = OpenRouterHandler()
        markers = handler.get_turn_markers()
        assert "assistant" in markers

    def test_user_pattern_matches_user_message(self) -> None:
        """User regex matches data-testid="user-message" HTML."""
        import re

        handler = OpenRouterHandler()
        markers = handler.get_turn_markers()
        html = '<div data-testid="user-message" class="flex">Content</div>'

        match = re.search(markers["user"], html, re.IGNORECASE)
        assert match is not None

    def test_assistant_pattern_matches_assistant_message(self) -> None:
        """Assistant regex matches data-testid="assistant-message" HTML."""
        import re

        handler = OpenRouterHandler()
        markers = handler.get_turn_markers()
        html = '<div data-testid="assistant-message">Content</div>'

        match = re.search(markers["assistant"], html, re.IGNORECASE)
        assert match is not None
