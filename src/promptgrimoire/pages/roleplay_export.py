"""Pure-function conversion of roleplay sessions to annotatable HTML.

Extracted from roleplay.py for testability (functional core / imperative shell).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import markdown

if TYPE_CHECKING:
    from promptgrimoire.models import Session


def session_to_html(session: Session) -> str:
    """Convert a roleplay Session to HTML with speaker marker divs.

    Each turn produces:
    1. An empty marker div: <div data-speaker="role" data-speaker-name="Name"></div>
    2. The turn content rendered from markdown to HTML (as a sibling, not child)

    Args:
        session: The roleplay session to convert.

    Returns:
        HTML string with speaker markers, or empty string if no turns.
    """
    if not session.turns:
        return ""

    parts: list[str] = []
    for turn in session.turns:
        role = "user" if turn.is_user else ("system" if turn.is_system else "assistant")
        name = session.user_name if turn.is_user else session.character.name

        marker = f'<div data-speaker="{role}" data-speaker-name="{name}"></div>'
        content_html = markdown.markdown(turn.content)

        parts.append(marker)
        parts.append(content_html)

    return "\n".join(parts)
