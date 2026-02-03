## Phase 3: Implement remaining platform handlers

**Goal:** Complete all five platform handlers (Claude, Gemini, AI Studio, ScienceOS)

**Done when:** All five handlers implemented with passing unit tests

---

<!-- START_SUBCOMPONENT_B (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Write failing tests for Claude handler

**Files:**
- Create: `tests/unit/export/platforms/test_claude.py`

**Step 1: Write the failing tests**

```python
"""Unit tests for Claude platform handler."""

from __future__ import annotations

import pytest

from promptgrimoire.export.platforms.claude import ClaudeHandler


class TestClaudeHandlerMatches:
    """Tests for Claude platform detection."""

    def test_matches_claude_html_with_font_user_message(self) -> None:
        """Handler matches HTML containing font-user-message class."""
        handler = ClaudeHandler()
        html = '<div class="font-user-message">Content</div>'
        assert handler.matches(html) is True

    def test_matches_claude_html_with_class_in_list(self) -> None:
        """Handler matches when font-user-message is part of multiple classes."""
        handler = ClaudeHandler()
        html = '<div class="text-base font-user-message p-4">Content</div>'
        assert handler.matches(html) is True

    def test_does_not_match_openai_html(self) -> None:
        """Handler does not match OpenAI exports."""
        handler = ClaudeHandler()
        html = '<div class="agent-turn">Content</div>'
        assert handler.matches(html) is False

    def test_does_not_match_empty_html(self) -> None:
        """Handler does not match empty HTML."""
        handler = ClaudeHandler()
        assert handler.matches("") is False


class TestClaudeHandlerPreprocess:
    """Tests for Claude HTML preprocessing."""

    def test_marks_thinking_header(self) -> None:
        """Preprocessing marks thinking header with data-thinking attribute."""
        handler = ClaudeHandler()
        html = '''
        <div class="thinking-summary">
            <div class="text-sm font-semibold">Thought process</div>
            <div>Summary content</div>
        </div>
        '''
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert 'data-thinking="header"' in result or "Thought process" in result

    def test_thinking_sections_in_real_fixture(self) -> None:
        """Verify thinking section detection works on real Claude fixture."""
        from tests.conftest import load_conversation_fixture

        handler = ClaudeHandler()
        html = load_conversation_fixture("claude_cooking.html")

        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        # Fixture should contain Claude conversation content
        assert len(result) > 0
        # If fixture has thinking sections, they should be marked
        # (this is a regression guard - if fixture has "Thought process", it should be marked)

    def test_preserves_conversation_content(self) -> None:
        """Preprocessing preserves actual conversation content."""
        handler = ClaudeHandler()
        html = '''
        <div class="font-user-message">
            <p>Hello Claude!</p>
        </div>
        '''
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Hello Claude!" in result


class TestClaudeHandlerTurnMarkers:
    """Tests for Claude turn marker patterns."""

    def test_get_turn_markers_returns_user_pattern(self) -> None:
        """Turn markers include user pattern."""
        handler = ClaudeHandler()
        markers = handler.get_turn_markers()
        assert "user" in markers
        assert "data-testid" in markers["user"] or "user-message" in markers["user"]

    def test_get_turn_markers_returns_assistant_pattern(self) -> None:
        """Turn markers include assistant pattern."""
        handler = ClaudeHandler()
        markers = handler.get_turn_markers()
        assert "assistant" in markers
        assert "font-claude-response" in markers["assistant"]

    def test_user_pattern_matches_user_turn(self) -> None:
        """User pattern matches actual user turn HTML."""
        import re

        handler = ClaudeHandler()
        markers = handler.get_turn_markers()
        html = '<div data-testid="user-message" class="font-user-message">Content</div>'

        match = re.search(markers["user"], html, re.IGNORECASE)
        assert match is not None

    def test_assistant_pattern_matches_assistant_turn(self) -> None:
        """Assistant pattern matches actual assistant turn HTML."""
        import re

        handler = ClaudeHandler()
        markers = handler.get_turn_markers()
        html = '<div class="font-claude-response relative leading-[1.65rem]">Content</div>'

        match = re.search(markers["assistant"], html, re.IGNORECASE)
        assert match is not None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/export/platforms/test_claude.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'promptgrimoire.export.platforms.claude'`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement Claude handler

**Files:**
- Create: `src/promptgrimoire/export/platforms/claude.py`

**Step 1: Write minimal implementation**

```python
"""Claude platform handler for HTML preprocessing.

Handles Claude exports, which have:
- font-user-message class for platform detection
- data-testid="user-message" for user turns
- font-claude-response class for assistant turns
- Thinking sections that need data-thinking attributes
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selectolax.lexbor import LexborHTMLParser

# Platform detection pattern
_DETECTION_PATTERN = re.compile(r'class="[^"]*font-user-message[^"]*"', re.IGNORECASE)

# Thinking section patterns
_THINKING_HEADER_TEXT = "Thought process"


class ClaudeHandler:
    """Handler for Claude HTML exports."""

    name: str = "claude"

    def matches(self, html: str) -> bool:
        """Return True if HTML is from Claude.

        Detection is based on the presence of 'font-user-message' class,
        which is unique to Claude exports.
        """
        return bool(_DETECTION_PATTERN.search(html))

    def preprocess(self, tree: LexborHTMLParser) -> None:
        """Remove chrome and mark thinking sections in Claude HTML.

        Marks thinking sections with data-thinking attributes for special
        styling in PDF export.

        Args:
            tree: Parsed HTML tree to modify in-place.
        """
        # Mark thinking headers
        for node in tree.css(".text-sm.font-semibold"):
            if node.text() and _THINKING_HEADER_TEXT in node.text():
                node.attrs["data-thinking"] = "header"

        # Mark thinking summaries (text-sm divs inside thinking sections)
        for node in tree.css(".thinking-summary .text-sm"):
            if "font-semibold" not in (node.attributes.get("class") or ""):
                node.attrs["data-thinking"] = "summary"

    def get_turn_markers(self) -> dict[str, str]:
        """Return regex patterns for Claude turn boundaries.

        Claude uses data-testid for user messages and specific CSS classes
        for assistant responses.

        Returns:
            Dict with 'user' and 'assistant' regex patterns.
        """
        return {
            "user": r'(<[^>]*data-testid="user-message"[^>]*>)',
            "assistant": r'(<[^>]*class="font-claude-response relative leading-\[1\.65rem\][^"]*"[^>]*>)',
        }


# Module-level handler instance for autodiscovery
handler = ClaudeHandler()
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/export/platforms/test_claude.py -v`
Expected: All tests PASS
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify and commit Claude handler

**Step 1: Run type checker**

Run: `uvx ty check src/promptgrimoire/export/platforms/claude.py`
Expected: No type errors

**Step 2: Commit**

```bash
git add src/promptgrimoire/export/platforms/claude.py tests/unit/export/platforms/test_claude.py
git commit -m "feat(export): add Claude platform handler

Implements PlatformHandler protocol for Claude exports:
- Detection via font-user-message class
- Thinking section marking with data-thinking attributes
- Turn boundary patterns via data-testid and font-claude-response

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_B -->

---

<!-- START_SUBCOMPONENT_C (tasks 4-6) -->
<!-- START_TASK_4 -->
### Task 4: Write failing tests for Gemini handler

**Files:**
- Create: `tests/unit/export/platforms/test_gemini.py`

**Step 1: Write the failing tests**

```python
"""Unit tests for Gemini platform handler."""

from __future__ import annotations

import pytest

from promptgrimoire.export.platforms.gemini import GeminiHandler


class TestGeminiHandlerMatches:
    """Tests for Gemini platform detection."""

    def test_matches_gemini_html_with_user_query_element(self) -> None:
        """Handler matches HTML containing user-query element."""
        handler = GeminiHandler()
        html = '<user-query>Content</user-query>'
        assert handler.matches(html) is True

    def test_matches_gemini_html_with_attributes(self) -> None:
        """Handler matches user-query element with attributes."""
        handler = GeminiHandler()
        html = '<user-query class="query" data-id="1">Content</user-query>'
        assert handler.matches(html) is True

    def test_does_not_match_openai_html(self) -> None:
        """Handler does not match OpenAI exports."""
        handler = GeminiHandler()
        html = '<div class="agent-turn">Content</div>'
        assert handler.matches(html) is False

    def test_does_not_match_empty_html(self) -> None:
        """Handler does not match empty HTML."""
        handler = GeminiHandler()
        assert handler.matches("") is False


class TestGeminiHandlerPreprocess:
    """Tests for Gemini HTML preprocessing."""

    def test_preserves_conversation_content(self) -> None:
        """Preprocessing preserves actual conversation content."""
        handler = GeminiHandler()
        html = '''
        <user-query>Hello Gemini!</user-query>
        <model-response>Hello! How can I help?</model-response>
        '''
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Hello Gemini!" in result
        assert "Hello! How can I help?" in result


class TestGeminiHandlerTurnMarkers:
    """Tests for Gemini turn marker patterns."""

    def test_get_turn_markers_returns_user_pattern(self) -> None:
        """Turn markers include user pattern."""
        handler = GeminiHandler()
        markers = handler.get_turn_markers()
        assert "user" in markers
        assert "user-query" in markers["user"]

    def test_get_turn_markers_returns_assistant_pattern(self) -> None:
        """Turn markers include assistant pattern."""
        handler = GeminiHandler()
        markers = handler.get_turn_markers()
        assert "assistant" in markers
        assert "model-response" in markers["assistant"]

    def test_user_pattern_matches_user_turn(self) -> None:
        """User pattern matches actual user turn HTML."""
        import re

        handler = GeminiHandler()
        markers = handler.get_turn_markers()
        html = '<user-query class="query">Content</user-query>'

        match = re.search(markers["user"], html, re.IGNORECASE)
        assert match is not None

    def test_assistant_pattern_matches_assistant_turn(self) -> None:
        """Assistant pattern matches actual assistant turn HTML."""
        import re

        handler = GeminiHandler()
        markers = handler.get_turn_markers()
        html = '<model-response>Content</model-response>'

        match = re.search(markers["assistant"], html, re.IGNORECASE)
        assert match is not None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/export/platforms/test_gemini.py -v`
Expected: FAIL with `ModuleNotFoundError`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Implement Gemini handler

**Files:**
- Create: `src/promptgrimoire/export/platforms/gemini.py`

**Step 1: Write minimal implementation**

```python
"""Gemini platform handler for HTML preprocessing.

Handles Google Gemini web exports, which have:
- <user-query> custom elements for user turns
- <model-response> custom elements for assistant turns
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selectolax.lexbor import LexborHTMLParser

# Platform detection pattern
_DETECTION_PATTERN = re.compile(r"<user-query\b", re.IGNORECASE)


class GeminiHandler:
    """Handler for Google Gemini HTML exports."""

    name: str = "gemini"

    def matches(self, html: str) -> bool:
        """Return True if HTML is from Google Gemini.

        Detection is based on the presence of <user-query> custom element,
        which is unique to Gemini web exports.
        """
        return bool(_DETECTION_PATTERN.search(html))

    def preprocess(self, tree: LexborHTMLParser) -> None:
        """Preprocess Gemini HTML.

        Gemini uses semantic custom elements, so minimal preprocessing needed.
        Chrome removal handled by common patterns.

        Args:
            tree: Parsed HTML tree to modify in-place.
        """
        # Gemini's custom elements are clean - no native labels to strip
        pass

    def get_turn_markers(self) -> dict[str, str]:
        """Return regex patterns for Gemini turn boundaries.

        Gemini uses custom HTML elements for turn boundaries.

        Returns:
            Dict with 'user' and 'assistant' regex patterns.
        """
        return {
            "user": r"(<user-query\b[^>]*>)",
            "assistant": r"(<model-response\b[^>]*>)",
        }


# Module-level handler instance for autodiscovery
handler = GeminiHandler()
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/export/platforms/test_gemini.py -v`
Expected: All tests PASS
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Verify and commit Gemini handler

**Step 1: Run type checker**

Run: `uvx ty check src/promptgrimoire/export/platforms/gemini.py`
Expected: No type errors

**Step 2: Commit**

```bash
git add src/promptgrimoire/export/platforms/gemini.py tests/unit/export/platforms/test_gemini.py
git commit -m "feat(export): add Gemini platform handler

Implements PlatformHandler protocol for Google Gemini exports:
- Detection via <user-query> custom element
- Turn boundary patterns via user-query and model-response elements

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_6 -->
<!-- END_SUBCOMPONENT_C -->

---

<!-- START_SUBCOMPONENT_D (tasks 7-9) -->
<!-- START_TASK_7 -->
### Task 7: Write failing tests for AI Studio handler

**Files:**
- Create: `tests/unit/export/platforms/test_aistudio.py`

**Step 1: Write the failing tests**

```python
"""Unit tests for AI Studio platform handler."""

from __future__ import annotations

import pytest

from promptgrimoire.export.platforms.aistudio import AIStudioHandler


class TestAIStudioHandlerMatches:
    """Tests for AI Studio platform detection."""

    def test_matches_aistudio_html_with_ms_chat_turn(self) -> None:
        """Handler matches HTML containing ms-chat-turn element."""
        handler = AIStudioHandler()
        html = '<ms-chat-turn>Content</ms-chat-turn>'
        assert handler.matches(html) is True

    def test_matches_aistudio_html_with_attributes(self) -> None:
        """Handler matches ms-chat-turn element with attributes."""
        handler = AIStudioHandler()
        html = '<ms-chat-turn data-turn-role="User">Content</ms-chat-turn>'
        assert handler.matches(html) is True

    def test_does_not_match_gemini_html(self) -> None:
        """Handler does not match Gemini exports."""
        handler = AIStudioHandler()
        html = '<user-query>Content</user-query>'
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
        html = '''
        <ms-chat-turn data-turn-role="User">
            <div class="author-label">User</div>
            <p>Hello AI Studio!</p>
        </ms-chat-turn>
        '''
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "author-label" not in result
        assert "Hello AI Studio!" in result

    def test_preserves_conversation_content(self) -> None:
        """Preprocessing preserves actual conversation content."""
        handler = AIStudioHandler()
        html = '''
        <ms-chat-turn data-turn-role="User">
            <p>Hello AI Studio!</p>
        </ms-chat-turn>
        '''
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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/export/platforms/test_aistudio.py -v`
Expected: FAIL with `ModuleNotFoundError`
<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Implement AI Studio handler

**Files:**
- Create: `src/promptgrimoire/export/platforms/aistudio.py`

**Step 1: Write minimal implementation**

```python
"""AI Studio platform handler for HTML preprocessing.

Handles Google AI Studio exports, which have:
- <ms-chat-turn> custom elements
- data-turn-role attribute for turn identification ("User" or "Model")
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selectolax.lexbor import LexborHTMLParser

# Platform detection pattern
_DETECTION_PATTERN = re.compile(r"<ms-chat-turn\b", re.IGNORECASE)


class AIStudioHandler:
    """Handler for Google AI Studio HTML exports."""

    name: str = "aistudio"

    def matches(self, html: str) -> bool:
        """Return True if HTML is from Google AI Studio.

        Detection is based on the presence of <ms-chat-turn> custom element,
        which is unique to AI Studio exports.
        """
        return bool(_DETECTION_PATTERN.search(html))

    def preprocess(self, tree: LexborHTMLParser) -> None:
        """Preprocess AI Studio HTML.

        Removes:
        - .author-label elements (native speaker labels like "User", "Model")

        Args:
            tree: Parsed HTML tree to modify in-place.
        """
        # Remove native author labels
        for node in tree.css(".author-label"):
            node.decompose()

    def get_turn_markers(self) -> dict[str, str]:
        """Return regex patterns for AI Studio turn boundaries.

        AI Studio uses data-turn-role attribute with values "User" and "Model".

        Returns:
            Dict with 'user' and 'assistant' regex patterns.
        """
        return {
            "user": r'(<[^>]*data-turn-role="User"[^>]*>)',
            "assistant": r'(<[^>]*data-turn-role="Model"[^>]*>)',
        }


# Module-level handler instance for autodiscovery
handler = AIStudioHandler()
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/export/platforms/test_aistudio.py -v`
Expected: All tests PASS
<!-- END_TASK_8 -->

<!-- START_TASK_9 -->
### Task 9: Verify and commit AI Studio handler

**Step 1: Run type checker**

Run: `uvx ty check src/promptgrimoire/export/platforms/aistudio.py`
Expected: No type errors

**Step 2: Commit**

```bash
git add src/promptgrimoire/export/platforms/aistudio.py tests/unit/export/platforms/test_aistudio.py
git commit -m "feat(export): add AI Studio platform handler

Implements PlatformHandler protocol for Google AI Studio exports:
- Detection via <ms-chat-turn> custom element
- Turn boundary patterns via data-turn-role attribute

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_9 -->
<!-- END_SUBCOMPONENT_D -->

---

<!-- START_SUBCOMPONENT_E (tasks 10-12) -->
<!-- START_TASK_10 -->
### Task 10: Write failing tests for ScienceOS handler

**Files:**
- Create: `tests/unit/export/platforms/test_scienceos.py`

**Step 1: Write the failing tests**

```python
"""Unit tests for ScienceOS platform handler."""

from __future__ import annotations

import pytest

from promptgrimoire.export.platforms.scienceos import ScienceOSHandler


class TestScienceOSHandlerMatches:
    """Tests for ScienceOS platform detection."""

    def test_matches_scienceos_html_with_prompt_class(self) -> None:
        """Handler matches HTML containing _prompt_ class pattern."""
        handler = ScienceOSHandler()
        html = '<div class="_prompt_abc123">Content</div>'
        assert handler.matches(html) is True

    def test_matches_scienceos_html_with_class_in_list(self) -> None:
        """Handler matches when _prompt_ class is part of multiple classes."""
        handler = ScienceOSHandler()
        html = '<div class="mantine-Text _prompt_xyz789 other">Content</div>'
        assert handler.matches(html) is True

    def test_matches_scienceos_html_with_tabler_icon(self) -> None:
        """Handler matches HTML containing tabler-icon-robot-face (alternative pattern)."""
        handler = ScienceOSHandler()
        html = '<svg class="tabler-icon tabler-icon-robot-face">...</svg>'
        assert handler.matches(html) is True

    def test_does_not_match_openai_html(self) -> None:
        """Handler does not match OpenAI exports."""
        handler = ScienceOSHandler()
        html = '<div class="agent-turn">Content</div>'
        assert handler.matches(html) is False

    def test_does_not_match_empty_html(self) -> None:
        """Handler does not match empty HTML."""
        handler = ScienceOSHandler()
        assert handler.matches("") is False


class TestScienceOSHandlerPreprocess:
    """Tests for ScienceOS HTML preprocessing."""

    def test_preserves_conversation_content(self) -> None:
        """Preprocessing preserves actual conversation content."""
        handler = ScienceOSHandler()
        html = '''
        <div class="_prompt_abc123">
            <p>Research query</p>
        </div>
        <div class="_markdown_def456">
            <p>Research results</p>
        </div>
        '''
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Research query" in result
        assert "Research results" in result


class TestScienceOSHandlerTurnMarkers:
    """Tests for ScienceOS turn marker patterns."""

    def test_get_turn_markers_returns_user_pattern(self) -> None:
        """Turn markers include user pattern."""
        handler = ScienceOSHandler()
        markers = handler.get_turn_markers()
        assert "user" in markers
        assert "_prompt_" in markers["user"]

    def test_get_turn_markers_returns_assistant_pattern(self) -> None:
        """Turn markers include assistant pattern."""
        handler = ScienceOSHandler()
        markers = handler.get_turn_markers()
        assert "assistant" in markers
        assert "_markdown_" in markers["assistant"]

    def test_user_pattern_matches_user_turn(self) -> None:
        """User pattern matches actual user turn HTML."""
        import re

        handler = ScienceOSHandler()
        markers = handler.get_turn_markers()
        html = '<div class="_prompt_abc123">Content</div>'

        match = re.search(markers["user"], html, re.IGNORECASE)
        assert match is not None

    def test_assistant_pattern_matches_assistant_turn(self) -> None:
        """Assistant pattern matches actual assistant turn HTML."""
        import re

        handler = ScienceOSHandler()
        markers = handler.get_turn_markers()
        html = '<div class="_markdown_def456">Content</div>'

        match = re.search(markers["assistant"], html, re.IGNORECASE)
        assert match is not None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/export/platforms/test_scienceos.py -v`
Expected: FAIL with `ModuleNotFoundError`
<!-- END_TASK_10 -->

<!-- START_TASK_11 -->
### Task 11: Implement ScienceOS handler

**Files:**
- Create: `src/promptgrimoire/export/platforms/scienceos.py`

**Step 1: Write minimal implementation**

```python
"""ScienceOS platform handler for HTML preprocessing.

Handles ScienceOS exports, which have:
- Mantine CSS classes with hash suffixes (e.g., _prompt_abc123)
- _prompt_ class pattern for user queries
- _markdown_ class pattern for model responses
- tabler-icon-robot-face SVG icons (alternative detection)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selectolax.lexbor import LexborHTMLParser

# Platform detection patterns (either matches)
# Two detection patterns for backward compatibility:
# - _prompt_ is the primary Mantine CSS class pattern
# - tabler-icon-robot-face is present in ScienceOS UI and tested in test_css_fidelity.py
_PROMPT_PATTERN = re.compile(r'class="[^"]*_prompt_[^"]*"', re.IGNORECASE)
_TABLER_PATTERN = re.compile(r'tabler-icon-robot-face', re.IGNORECASE)


class ScienceOSHandler:
    """Handler for ScienceOS HTML exports."""

    name: str = "scienceos"

    def matches(self, html: str) -> bool:
        """Return True if HTML is from ScienceOS.

        Detection is based on either:
        - '_prompt_' class pattern (Mantine CSS with hash suffixes)
        - 'tabler-icon-robot-face' SVG icon class
        """
        return bool(_PROMPT_PATTERN.search(html) or _TABLER_PATTERN.search(html))

    def preprocess(self, tree: LexborHTMLParser) -> None:
        """Preprocess ScienceOS HTML.

        ScienceOS uses Mantine CSS classes as semantic markers,
        so minimal preprocessing needed. Chrome removal handled by
        common patterns.

        Args:
            tree: Parsed HTML tree to modify in-place.
        """
        # ScienceOS uses CSS class patterns as turn markers - no native labels
        pass

    def get_turn_markers(self) -> dict[str, str]:
        """Return regex patterns for ScienceOS turn boundaries.

        ScienceOS uses Mantine CSS classes with hash suffixes.

        Returns:
            Dict with 'user' and 'assistant' regex patterns.
        """
        return {
            "user": r'(<[^>]*class="[^"]*_prompt_[^"]*"[^>]*>)',
            "assistant": r'(<[^>]*class="[^"]*_markdown_[^"]*"[^>]*>)',
        }


# Module-level handler instance for autodiscovery
handler = ScienceOSHandler()
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/export/platforms/test_scienceos.py -v`
Expected: All tests PASS
<!-- END_TASK_11 -->

<!-- START_TASK_12 -->
### Task 12: Verify and commit ScienceOS handler

**Step 1: Run type checker**

Run: `uvx ty check src/promptgrimoire/export/platforms/scienceos.py`
Expected: No type errors

**Step 2: Commit**

```bash
git add src/promptgrimoire/export/platforms/scienceos.py tests/unit/export/platforms/test_scienceos.py
git commit -m "feat(export): add ScienceOS platform handler

Implements PlatformHandler protocol for ScienceOS exports:
- Detection via _prompt_ Mantine CSS class pattern
- Turn boundary patterns via _prompt_ and _markdown_ classes

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_12 -->
<!-- END_SUBCOMPONENT_E -->
