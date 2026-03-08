"""Fixture-driven ChatCraft regression tests."""

from __future__ import annotations

from collections import Counter

from selectolax.lexbor import LexborHTMLParser

from promptgrimoire.export.platforms import preprocess_for_export
from tests.conftest import load_conversation_fixture


def _count_speaker_roles(html: str) -> Counter[str]:
    """Count ``data-speaker`` roles in processed HTML."""
    tree = LexborHTMLParser(html)
    counts: Counter[str] = Counter()
    for node in tree.css("[data-speaker]"):
        role = node.attributes.get("data-speaker")
        if role:
            counts[role] += 1
    return counts


class TestChatCraftFixturePreprocess:
    """Regression coverage for the ChatCraft Sonnet issue fixture."""

    def test_chatcraft_sonnet_fixture_preserves_turn_roles(self) -> None:
        """Import preprocessing labels all ten conversation cards correctly."""
        raw_html = load_conversation_fixture("chatcraft_sonnet-232")

        processed_html = preprocess_for_export(raw_html, platform_hint="chatcraft")

        counts = _count_speaker_roles(processed_html)
        assert counts == Counter({"assistant": 5, "user": 4, "system": 1})
        assert sum(counts.values()) == 10

    def test_chatcraft_sonnet_fixture_preserves_rich_content(self) -> None:
        """Import preprocessing keeps the fixture's blockquotes and code blocks."""
        raw_html = load_conversation_fixture("chatcraft_sonnet-232")

        processed_html = preprocess_for_export(raw_html, platform_hint="chatcraft")
        tree = LexborHTMLParser(processed_html)

        assert len(tree.css("blockquote")) == 8
        assert len(tree.css("pre")) == 5
        assert len(tree.css("code")) == 10

    def test_chatcraft_sonnet_fixture_strips_page_chrome(self) -> None:
        """Import preprocessing removes non-conversation page chrome."""
        raw_html = load_conversation_fixture("chatcraft_sonnet-232")

        processed_html = preprocess_for_export(raw_html, platform_hint="chatcraft")

        assert "Activity Denubis" not in processed_html
        assert "&lt;ChatCraft /&gt;" not in processed_html
        assert "Search chat history" not in processed_html
