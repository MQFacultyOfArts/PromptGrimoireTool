## Phase 2: Implement OpenAI handler

**Goal:** First platform handler as reference implementation

**Done when:** OpenAI handler detects platform, removes chrome, strips "You said:" native labels, unit tests pass

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Write failing tests for OpenAI handler

**Files:**
- Create: `tests/unit/export/platforms/__init__.py`
- Create: `tests/unit/export/platforms/test_openai.py`

**Step 1: Create test directory structure**

```bash
mkdir -p tests/unit/export/platforms
touch tests/unit/export/platforms/__init__.py
```

**Step 2: Write the failing tests**

```python
"""Unit tests for OpenAI platform handler."""

from __future__ import annotations

import pytest

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
        html = '<article class="w-full text-token-text-primary agent-turn">Content</article>'
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
        html = '''
        <article>
            <h5 class="sr-only">You said:</h5>
            <div>User message content</div>
        </article>
        '''
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
        html = '''
        <article>
            <h5 class="sr-only">ChatGPT</h5>
            <div>Assistant response</div>
        </article>
        '''
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "ChatGPT" not in result
        assert "Assistant response" in result

    def test_preserves_conversation_content(self) -> None:
        """Preprocessing preserves actual conversation content."""
        handler = OpenAIHandler()
        html = '''
        <div class="agent-turn">
            <div data-message-author-role="user">
                <p>Hello, how are you?</p>
            </div>
        </div>
        '''
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
```

**Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/export/platforms/test_openai.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'promptgrimoire.export.platforms.openai'`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement OpenAI handler

**Files:**
- Create: `src/promptgrimoire/export/platforms/openai.py`

**Step 1: Write minimal implementation to pass tests**

```python
"""OpenAI platform handler for HTML preprocessing.

Handles ChatGPT exports, which have:
- agent-turn class for platform detection
- data-message-author-role attribute for turn boundaries
- sr-only elements containing native labels ("You said:", "ChatGPT")
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selectolax.lexbor import LexborHTMLParser

# Platform detection pattern
_DETECTION_PATTERN = re.compile(r'class="[^"]*agent-turn[^"]*"', re.IGNORECASE)

# CSS selectors for elements to remove
_CHROME_SELECTORS = [
    ".sr-only",  # Screen-reader-only labels ("You said:", "ChatGPT")
]


class OpenAIHandler:
    """Handler for OpenAI/ChatGPT HTML exports."""

    name: str = "openai"

    def matches(self, html: str) -> bool:
        """Return True if HTML is from OpenAI/ChatGPT.

        Detection is based on the presence of 'agent-turn' class,
        which is unique to ChatGPT exports.
        """
        return bool(_DETECTION_PATTERN.search(html))

    def preprocess(self, tree: LexborHTMLParser) -> None:
        """Remove chrome and native labels from OpenAI HTML.

        Removes:
        - sr-only elements (contain "You said:" and "ChatGPT" labels)

        Args:
            tree: Parsed HTML tree to modify in-place.
        """
        for selector in _CHROME_SELECTORS:
            for node in tree.css(selector):
                node.decompose()

    def get_turn_markers(self) -> dict[str, str]:
        """Return regex patterns for OpenAI turn boundaries.

        OpenAI uses data-message-author-role attribute to identify
        user vs assistant turns.

        Returns:
            Dict with 'user' and 'assistant' regex patterns.
        """
        return {
            "user": r'(<[^>]*data-message-author-role="user"[^>]*>)',
            "assistant": r'(<[^>]*data-message-author-role="assistant"[^>]*>)',
        }


# Module-level handler instance for autodiscovery
handler = OpenAIHandler()
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/export/platforms/test_openai.py -v`
Expected: All tests PASS
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify and commit

**Step 1: Run type checker**

Run: `uvx ty check src/promptgrimoire/export/platforms/openai.py`
Expected: No type errors

**Step 2: Run linter**

Run: `uv run ruff check src/promptgrimoire/export/platforms/openai.py tests/unit/export/platforms/test_openai.py`
Expected: No lint errors

**Step 3: Commit**

```bash
git add src/promptgrimoire/export/platforms/openai.py tests/unit/export/platforms/__init__.py tests/unit/export/platforms/test_openai.py
git commit -m "feat(export): add OpenAI platform handler

Implements PlatformHandler protocol for ChatGPT exports:
- Detection via agent-turn class
- Chrome removal (sr-only elements with native labels)
- Turn boundary patterns via data-message-author-role

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
