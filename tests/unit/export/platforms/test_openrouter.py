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


def _assistant_msg_html(
    response: str,
    *,
    model_slug: str = "qwen/qwen3.5-35b-a3b",
    thinking: str = "",
) -> str:
    """Build realistic OpenRouter assistant-message HTML.

    Mirrors the real structure (as of 2026-03)::

        [data-testid="assistant-message"]
          ├── child 0: timestamp div
          ├── child 1: model link div
          ├── child 2: content wrapper
          │   ├── (optional) thinking div
          │   └── response div (last child)
          └── child 3: actions div (empty)
    """
    thinking_block = ""
    if thinking:
        thinking_block = (
            f'<div class="border rounded-md p-3">'
            f"<p>Thinking Process:</p><p>{thinking}</p></div>"
        )
    return f"""
    <div data-testid="assistant-message">
      <div class="text-muted-foreground text-xs">21 hours ago</div>
      <div><a href="https://openrouter.ai/{model_slug}">model</a></div>
      <div class="flex flex-col">
        {thinking_block}
        <div class="items-stretch"><p>{response}</p></div>
      </div>
      <div class="flex items-center gap-1"></div>
    </div>
    """


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
        html = f"""
        <div data-testid="playground-container">
            <div data-testid="user-message">
                <p>What is the capital of France?</p>
            </div>
            {_assistant_msg_html("The capital of France is Paris.")}
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

    def test_strips_timestamp_from_assistant_messages(self) -> None:
        """Timestamp (child 0) is removed from assistant messages."""
        handler = OpenRouterHandler()
        html = _assistant_msg_html("The answer is 42.")
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "21 hours ago" not in result
        assert "The answer is 42." in result

    def test_strips_model_link_from_assistant_messages(self) -> None:
        """Model link (child 1) is removed from assistant messages."""
        handler = OpenRouterHandler()
        html = _assistant_msg_html("Response text.")
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "openrouter.ai" not in result
        assert "Response text." in result

    def test_strips_actions_from_assistant_messages(self) -> None:
        """Actions div (child 3) is removed from assistant messages."""
        handler = OpenRouterHandler()
        html = _assistant_msg_html("Response text.")
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)

        # Only the content wrapper's last child should remain
        msgs = tree.css('[data-testid="assistant-message"]')
        assert len(msgs) == 1
        # Should have exactly one element child (the response div)
        from promptgrimoire.export.platforms.openrouter import _element_children

        top_children = _element_children(msgs[0])
        # Content wrapper kept, inside it only the response div
        assert len(top_children) == 1

    def test_strips_thinking_content(self) -> None:
        """Thinking/reasoning content blocks are removed."""
        handler = OpenRouterHandler()
        html = _assistant_msg_html(
            "The answer is 42.", thinking="Analyze the request..."
        )
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Thinking Process" not in result
        assert "Analyze the request" not in result
        assert "The answer is 42." in result

    def test_sets_data_speaker_name_from_model_link(self) -> None:
        """Model name extracted from link URL is set as data-speaker-name."""
        handler = OpenRouterHandler()
        html = _assistant_msg_html("Response", model_slug="qwen/qwen3.5-35b-a3b")
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)

        msgs = tree.css('[data-testid="assistant-message"]')
        assert len(msgs) == 1
        assert msgs[0].attributes.get("data-speaker-name") == "qwen3.5-35b-a3b"

    def test_sets_data_speaker_name_with_trailing_slash(self) -> None:
        """Model name extraction handles trailing slashes in URLs."""
        handler = OpenRouterHandler()
        # Build HTML with trailing slash on href
        html = """
        <div data-testid="assistant-message">
          <div class="text-muted-foreground">21 hours ago</div>
          <div><a href="https://openrouter.ai/qwen/qwen3.5-35b-a3b/">model</a></div>
          <div><div><p>Response</p></div></div>
          <div></div>
        </div>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)

        msgs = tree.css('[data-testid="assistant-message"]')
        assert len(msgs) == 1
        assert msgs[0].attributes.get("data-speaker-name") == "qwen3.5-35b-a3b"


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
