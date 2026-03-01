"""Unit tests for ChatCraft platform handler."""

from __future__ import annotations

import re

from selectolax.lexbor import LexborHTMLParser

from promptgrimoire.export.platforms.chatcraft import (
    ChatCraftHandler,
    _classify_speaker,
)

# ---------------------------------------------------------------------------
# Minimal HTML fragments for platform detection
# ---------------------------------------------------------------------------

_CHATCRAFT_HTML = """
<html><body>
<div class="chakra-card">
    <span title="Alice">A</span>
    <p>Hello from ChatCraft</p>
</div>
<footer>chatcraft.org</footer>
</body></html>
"""

_CHAKRA_ONLY_HTML = """
<html><body>
<div class="chakra-card">
    <span title="Alice">A</span>
    <p>Hello from some Chakra app</p>
</div>
</body></html>
"""

_CHATCRAFT_TEXT_ONLY_HTML = """
<html><body>
<div class="plain-card">
    <p>Visit chatcraft.org for details</p>
</div>
</body></html>
"""

_CLAUDE_HTML = '<div class="font-user-message">Hello Claude</div>'
_OPENAI_HTML = '<div class="agent-turn">Hello OpenAI</div>'
_OPENROUTER_HTML = '<div class="playground-container">Hello OpenRouter</div>'


# ---------------------------------------------------------------------------
# Preprocess test HTML with realistic structure
# ---------------------------------------------------------------------------

_PREPROCESS_HTML = """
<html><body>
<div class="chakra-accordion__item">Settings panel</div>
<form><input type="text" /></form>
<div class="chakra-menu__menuitem">Copy</div>
<div class="chakra-card">
    <div class="chakra-card__header">
        <span title="Alice Smith">A</span>
        <span>Sep 29, 2025</span>
    </div>
    <div class="chakra-card__body"><p>User message content</p></div>
</div>
<div class="chakra-card">
    <div class="chakra-card__header">
        <span title="claude-sonnet-4">C</span>
        <span>Sep 29, 2025</span>
    </div>
    <div class="chakra-card__body"><p>Assistant response content</p></div>
</div>
<div class="chakra-card">
    <div class="chakra-card__header">
        <span title="System Prompt">S</span>
    </div>
    <div class="chakra-card__body"><p>System instructions</p></div>
</div>
<footer>chatcraft.org</footer>
</body></html>
"""


class TestChatCraftHandlerMatches:
    """Tests for ChatCraft platform detection."""

    def test_matches_html_with_chakra_card_and_chatcraft_org(self) -> None:
        """Both chakra-card class and chatcraft.org text required."""
        handler = ChatCraftHandler()
        assert handler.matches(_CHATCRAFT_HTML) is True

    def test_does_not_match_chakra_card_without_chatcraft_org(self) -> None:
        """Chakra UI HTML without chatcraft.org text does not match."""
        handler = ChatCraftHandler()
        assert handler.matches(_CHAKRA_ONLY_HTML) is False

    def test_does_not_match_chatcraft_org_without_chakra_card(self) -> None:
        """Text with chatcraft.org but without chakra-card class does not match."""
        handler = ChatCraftHandler()
        assert handler.matches(_CHATCRAFT_TEXT_ONLY_HTML) is False

    def test_does_not_match_claude_html(self) -> None:
        """Claude HTML with font-user-message does not match."""
        handler = ChatCraftHandler()
        assert handler.matches(_CLAUDE_HTML) is False

    def test_does_not_match_openai_html(self) -> None:
        """OpenAI HTML with agent-turn does not match."""
        handler = ChatCraftHandler()
        assert handler.matches(_OPENAI_HTML) is False

    def test_does_not_match_openrouter_html(self) -> None:
        """OpenRouter HTML with playground-container does not match."""
        handler = ChatCraftHandler()
        assert handler.matches(_OPENROUTER_HTML) is False

    def test_does_not_match_empty_html(self) -> None:
        """Empty and minimal HTML do not match."""
        handler = ChatCraftHandler()
        assert handler.matches("") is False
        assert handler.matches("<html><body></body></html>") is False


class TestChatCraftHandlerPreprocess:
    """Tests for ChatCraft HTML preprocessing."""

    def test_removes_accordion_items(self) -> None:
        """Preprocessing removes .chakra-accordion__item elements."""
        handler = ChatCraftHandler()
        tree = LexborHTMLParser(_PREPROCESS_HTML)
        handler.preprocess(tree)

        assert tree.css(".chakra-accordion__item") == []

    def test_removes_form_elements(self) -> None:
        """Preprocessing removes form elements."""
        handler = ChatCraftHandler()
        tree = LexborHTMLParser(_PREPROCESS_HTML)
        handler.preprocess(tree)

        assert tree.css("form") == []

    def test_removes_menu_items(self) -> None:
        """Preprocessing removes .chakra-menu__menuitem elements."""
        handler = ChatCraftHandler()
        tree = LexborHTMLParser(_PREPROCESS_HTML)
        handler.preprocess(tree)

        assert tree.css(".chakra-menu__menuitem") == []

    def test_injects_data_speaker_on_cards(self) -> None:
        """After preprocessing, chakra-card elements have data-speaker attributes."""
        handler = ChatCraftHandler()
        tree = LexborHTMLParser(_PREPROCESS_HTML)
        handler.preprocess(tree)

        cards = tree.css(".chakra-card")
        assert len(cards) == 3

        speakers = [card.attributes.get("data-speaker") for card in cards]
        assert speakers == ["user", "assistant", "system"]

    def test_sets_data_speaker_name(self) -> None:
        """After preprocessing, cards have data-speaker-name with avatar title."""
        handler = ChatCraftHandler()
        tree = LexborHTMLParser(_PREPROCESS_HTML)
        handler.preprocess(tree)

        cards = tree.css(".chakra-card")
        names = [card.attributes.get("data-speaker-name") for card in cards]
        assert names == ["Alice Smith", "claude-sonnet-4", "System Prompt"]

    def test_removes_card_headers(self) -> None:
        """Card headers (name, date, avatar) are removed after extraction."""
        handler = ChatCraftHandler()
        tree = LexborHTMLParser(_PREPROCESS_HTML)
        handler.preprocess(tree)

        assert tree.css(".chakra-card__header") == []
        result = tree.html or ""
        # Date metadata should be gone
        assert "Sep 29, 2025" not in result

    def test_preserves_conversation_content(self) -> None:
        """Card body content is preserved after preprocessing."""
        handler = ChatCraftHandler()
        tree = LexborHTMLParser(_PREPROCESS_HTML)
        handler.preprocess(tree)

        result = tree.html or ""
        assert "User message content" in result
        assert "Assistant response content" in result
        assert "System instructions" in result


class TestChatCraftHandlerTurnMarkers:
    """Tests for ChatCraft turn marker patterns."""

    def test_get_turn_markers_returns_user_pattern(self) -> None:
        """Turn markers include a user pattern matching data-speaker='user'."""
        handler = ChatCraftHandler()
        markers = handler.get_turn_markers()
        assert "user" in markers

        html = '<div class="chakra-card" data-speaker="user">'
        assert re.search(markers["user"], html) is not None

    def test_get_turn_markers_returns_assistant_pattern(self) -> None:
        """Turn markers include an assistant pattern."""
        handler = ChatCraftHandler()
        markers = handler.get_turn_markers()
        assert "assistant" in markers

        html = '<div class="chakra-card" data-speaker="assistant">'
        assert re.search(markers["assistant"], html) is not None

    def test_get_turn_markers_returns_system_pattern(self) -> None:
        """Turn markers include a system pattern matching data-speaker='system'."""
        handler = ChatCraftHandler()
        markers = handler.get_turn_markers()
        assert "system" in markers

        html = '<div class="chakra-card" data-speaker="system">'
        assert re.search(markers["system"], html) is not None


class TestClassifySpeaker:
    """Tests for _classify_speaker heuristic."""

    def test_system_prompt_returns_system(self) -> None:
        """'System Prompt' maps to 'system' (AC3.4)."""
        assert _classify_speaker("System Prompt") == "system"

    def test_hyphenated_model_name_returns_assistant(self) -> None:
        """'claude-sonnet-4' (hyphens, no spaces) maps to 'assistant' (AC3.5)."""
        assert _classify_speaker("claude-sonnet-4") == "assistant"

    def test_gpt_model_returns_assistant(self) -> None:
        """'gpt-4' maps to 'assistant' (AC3.5)."""
        assert _classify_speaker("gpt-4") == "assistant"

    def test_multi_hyphen_model_returns_assistant(self) -> None:
        """'qwen3.5-35B-A3B' maps to 'assistant' (AC3.5)."""
        assert _classify_speaker("qwen3.5-35B-A3B") == "assistant"

    def test_human_name_with_spaces_returns_user(self) -> None:
        """'Alice Smith' maps to 'user' (AC3.6)."""
        assert _classify_speaker("Alice Smith") == "user"

    def test_single_word_no_hyphen_returns_user(self) -> None:
        """'ChatCraft' maps to 'user' (AC3.10)."""
        assert _classify_speaker("ChatCraft") == "user"

    def test_empty_string_returns_user(self) -> None:
        """Empty string falls through to default 'user'."""
        assert _classify_speaker("") == "user"
