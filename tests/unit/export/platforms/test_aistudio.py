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

    def test_removes_file_chunk_metadata(self) -> None:
        """Preprocessing removes ms-file-chunk elements (filenames, token counts)."""
        handler = AIStudioHandler()
        html = """
        <ms-chat-turn data-turn-role="User">
            <ms-file-chunk>case-brief-tool-prd.md 3,901 tokens</ms-file-chunk>
            <p>Actual user content</p>
        </ms-chat-turn>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "3,901 tokens" not in result
        assert "case-brief-tool-prd.md" not in result
        assert "Actual user content" in result

    def test_removes_thought_chunk_chrome(self) -> None:
        """Preprocessing removes ms-thought-chunk elements."""
        handler = AIStudioHandler()
        html = """
        <ms-chat-turn data-turn-role="Model">
            <ms-thought-chunk>Thoughts Expand to view model thoughts</ms-thought-chunk>
            <p>Model response content</p>
        </ms-chat-turn>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Expand to view model thoughts" not in result
        assert "Model response content" in result

    def test_removes_toolbar_and_token_counts(self) -> None:
        """Preprocessing removes ms-toolbar and .token-count elements."""
        handler = AIStudioHandler()
        html = """
        <div>
            <ms-toolbar>UX Discussion 26,924 tokens</ms-toolbar>
            <ms-chat-turn data-turn-role="User">
                <span class="token-count">3,901 tokens</span>
                <p>Content</p>
            </ms-chat-turn>
        </div>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "26,924 tokens" not in result
        assert "3,901 tokens" not in result
        assert "Content" in result

    def test_removes_virtual_scroll_spacers(self) -> None:
        """Virtual scroll spacer divs (empty, fixed height) are removed."""
        handler = AIStudioHandler()
        html = """
        <div class="virtual-scroll-container user-prompt-container"
             data-turn-role="User">
            <div style="height: 352px;"></div>
            <div class="turn-content">
                <p>User message</p>
            </div>
        </div>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "352px" not in result
        assert "User message" in result

    def test_removes_chat_turn_options(self) -> None:
        """Turn options menus are removed."""
        handler = AIStudioHandler()
        html = """
        <ms-chat-turn data-turn-role="User">
            <ms-chat-turn-options>More options</ms-chat-turn-options>
            <p>User content</p>
        </ms-chat-turn>
        """
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "More options" not in result
        assert "User content" in result

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
