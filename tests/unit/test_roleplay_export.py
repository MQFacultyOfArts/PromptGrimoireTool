"""Unit tests for session-to-HTML export.

Tests pure-function conversion of roleplay Session to HTML with
data-speaker marker divs. Verifies AC3.2.
"""

from __future__ import annotations

import pytest

from promptgrimoire.models import Character, Session


@pytest.fixture
def character() -> Character:
    return Character(name="Becky Bennett", description="Test character")


@pytest.fixture
def session(character: Character) -> Session:
    return Session(character=character, user_name="Jane")


class TestSessionToHtml:
    """Tests for session_to_html pure function."""

    def test_user_turn_has_correct_speaker_attrs(self, session: Session) -> None:
        """AC3.2: Output contains data-speaker='user' and data-speaker-name='Jane'."""
        from promptgrimoire.pages.roleplay_export import session_to_html

        session.add_turn("Hello Becky", is_user=True)
        html = session_to_html(session)
        assert 'data-speaker="user"' in html
        assert 'data-speaker-name="Jane"' in html

    def test_ai_turn_has_correct_speaker_attrs(self, session: Session) -> None:
        """AC3.2: AI turn has assistant speaker and character name."""
        from promptgrimoire.pages.roleplay_export import session_to_html

        session.add_turn("*shifts uncomfortably* Hi there", is_user=False)
        html = session_to_html(session)
        assert 'data-speaker="assistant"' in html
        assert 'data-speaker-name="Becky Bennett"' in html

    def test_markdown_converts_to_html(self, session: Session) -> None:
        """Markdown formatting is converted to HTML."""
        from promptgrimoire.pages.roleplay_export import session_to_html

        session.add_turn("*italics* and **bold**", is_user=False)
        html = session_to_html(session)
        assert "<em>italics</em>" in html
        assert "<strong>bold</strong>" in html

    def test_marker_divs_are_siblings_not_parents(self, session: Session) -> None:
        """Marker div is a sibling of content, not wrapping it."""
        from promptgrimoire.pages.roleplay_export import session_to_html

        session.add_turn("Hello", is_user=True)
        html = session_to_html(session)
        # Marker div should be empty, NOT wrapping the content
        # <div data-speaker="user" ...></div>\n<p>Hello</p>
        assert "</div>\n<p>" in html or "</div><p>" in html

    def test_multiple_turns_alternate_correctly(self, session: Session) -> None:
        """Multi-turn session produces alternating marker+content blocks."""
        from promptgrimoire.pages.roleplay_export import session_to_html

        session.add_turn("Hello", is_user=True)
        session.add_turn("Hi there", is_user=False)
        html = session_to_html(session)
        # Both markers should be present
        assert 'data-speaker="user"' in html
        assert 'data-speaker="assistant"' in html
        # User marker should come before assistant marker
        user_pos = html.index('data-speaker="user"')
        assistant_pos = html.index('data-speaker="assistant"')
        assert user_pos < assistant_pos

    def test_empty_session_returns_empty_string(self, session: Session) -> None:
        """Empty session (no turns) returns empty string."""
        from promptgrimoire.pages.roleplay_export import session_to_html

        assert session_to_html(session) == ""

    def test_system_turn_has_system_role(self, session: Session) -> None:
        """System turns produce data-speaker='system'."""
        from promptgrimoire.models.scenario import Turn
        from promptgrimoire.pages.roleplay_export import session_to_html

        session.turns.append(
            Turn(
                name="System",
                content="Context injection",
                is_user=False,
                is_system=True,
            )
        )
        html = session_to_html(session)
        assert 'data-speaker="system"' in html
