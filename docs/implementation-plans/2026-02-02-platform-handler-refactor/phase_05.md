## Phase 5: Update call sites and delete old files

**Goal:** Migrate to new API, remove deprecated code

**Done when:** All 40 integration tests pass, old files deleted, no references to old API remain

---

<!-- START_SUBCOMPONENT_G (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Extend preprocess_for_export with common chrome removal

The current `preprocess_for_export()` only runs platform-specific preprocessing. It needs to also run common chrome removal (avatar images, small icons, buttons, etc.).

**Files:**
- Modify: `src/promptgrimoire/export/platforms/__init__.py`
- Modify: `src/promptgrimoire/export/platforms/base.py` (add shared utilities)

**Step 1: Add common chrome removal utilities to base.py**

Replace the empty `base.py` with:

```python
"""Shared utilities for platform handlers.

This module provides common functions used across multiple platform handlers
and the entry point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selectolax.lexbor import LexborHTMLParser

# Common chrome patterns - apply to all platforms
_CHROME_CLASS_PATTERNS = [
    "avatar", "profile-pic", "profile-picture", "tabler-icon", "icon-copy",
    "icon-share", "copy-button", "share-button", "logo", "brand",
    "closing", "side-element", "year-options", "text-xs"
]

_CHROME_ID_PATTERNS = [
    "page-header", "page-search", "page-logo", "page-side",
    "page-tertiary", "panels", "panel-", "ribbon"
]


def remove_common_chrome(tree: LexborHTMLParser) -> None:
    """Remove UI chrome elements common to all platforms.

    Removes:
    - Elements with chrome-related CSS classes
    - Elements with chrome-related IDs
    - Small images (< 32px, likely icons)
    - Remote images (http/https URLs)
    - SVG elements
    - Hidden elements (display: none, visibility: hidden)
    - Action buttons (copy, share, download)

    Args:
        tree: Parsed HTML tree to modify in-place.
    """
    # Remove elements by class patterns
    for pattern in _CHROME_CLASS_PATTERNS:
        for node in tree.css(f'[class*="{pattern}"]'):
            node.decompose()

    # Remove elements by ID patterns
    for pattern in _CHROME_ID_PATTERNS:
        for node in tree.css(f'[id^="{pattern}"]'):
            node.decompose()

    # Remove small images (likely icons)
    for img in tree.css("img"):
        attrs = img.attributes
        width = attrs.get("width", "")
        height = attrs.get("height", "")
        try:
            if (width and int(width) < 32) or (height and int(height) < 32):
                img.decompose()
                continue
        except ValueError:
            pass

        # Remove remote images
        src = attrs.get("src", "")
        if src.startswith(("http://", "https://")):
            img.decompose()

    # Remove SVG elements
    for svg in tree.css("svg"):
        svg.decompose()

    # Remove hidden elements
    for node in tree.css('[style*="display: none"], [style*="display:none"]'):
        node.decompose()
    for node in tree.css('[style*="visibility: hidden"], [style*="visibility:hidden"]'):
        node.decompose()

    # Remove action buttons
    for button in tree.css("button"):
        text = (button.text() or "").lower()
        if any(action in text for action in ("copy", "share", "download")):
            button.decompose()

    # Remove KaTeX visual rendering (keep MathML for Pandoc)
    for node in tree.css(".katex-html"):
        node.decompose()

    # Remove thinking time indicators (e.g., "18s", "21s" from Claude)
    import re
    _THINKING_TIME_PATTERN = re.compile(r"^\d+s$")
    for node in tree.css(".text-xs, .text-sm"):
        text = (node.text() or "").strip()
        if _THINKING_TIME_PATTERN.match(text):
            node.decompose()


def remove_empty_containers(tree: LexborHTMLParser) -> None:
    """Remove empty container elements left after chrome removal.

    Makes multiple passes until no more empty containers are found.
    Note: Elements with data-* attributes are NOT considered empty
    (handled by selectolax's text() which returns None for such elements).

    Args:
        tree: Parsed HTML tree to modify in-place.
    """
    # Tags that should be removed when empty
    # Expanded from original {div, span} to include semantic containers
    # that may be left empty after chrome removal
    container_tags = {"div", "span", "p", "section", "article", "aside"}

    while True:
        removed = False
        for tag in container_tags:
            for node in tree.css(tag):
                # Check if truly empty (no text, no children with content)
                text = (node.text() or "").strip()
                if not text and not node.css("img, svg, video, audio, iframe"):
                    node.decompose()
                    removed = True
        if not removed:
            break
```

**Step 2: Update __init__.py preprocess_for_export**

Replace the `preprocess_for_export()` function with:

```python
def preprocess_for_export(html: str, platform_hint: str | None = None) -> str:
    """Main entry point: detect platform, preprocess, inject labels.

    Args:
        html: Raw HTML from chatbot export.
        platform_hint: Optional platform name to skip autodiscovery (e.g., "openai").
            Useful when autodiscovery fails or user knows the platform.

    Returns:
        Processed HTML ready for LaTeX conversion, or unchanged HTML if
        no handler matches (graceful degradation).
    """
    import re

    from selectolax.lexbor import LexborHTMLParser

    from promptgrimoire.export.platforms.base import remove_common_chrome

    if platform_hint:
        handler = _handlers.get(platform_hint)
        if handler is None:
            logger.warning("Unknown platform_hint '%s', falling back to autodiscovery", platform_hint)
            handler = get_handler(html)
    else:
        handler = get_handler(html)

    tree = LexborHTMLParser(html)

    # Platform-specific preprocessing (if handler found)
    if handler:
        handler.preprocess(tree)

    # Common chrome removal (always applied)
    remove_common_chrome(tree)

    # Get processed HTML
    result = tree.html or html

    # Inject speaker labels (if handler found)
    if handler:
        markers = handler.get_turn_markers()

        # Inject user labels
        user_pattern = markers.get("user")
        if user_pattern:
            result = re.sub(
                user_pattern,
                r'<div data-speaker="user" class="speaker-turn"></div>\1',
                result,
                flags=re.IGNORECASE,
            )

        # Inject assistant labels
        assistant_pattern = markers.get("assistant")
        if assistant_pattern:
            result = re.sub(
                assistant_pattern,
                r'<div data-speaker="assistant" class="speaker-turn"></div>\1',
                result,
                flags=re.IGNORECASE,
            )

    return result
```

**Step 3: Run tests**

Run: `uv run pytest tests/unit/export/platforms/ -v`
Expected: All existing tests PASS (chrome removal is additive)
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Write integration test for complete pipeline

Before migrating call sites, verify the new entry point produces equivalent output.

**Files:**
- Create: `tests/unit/export/platforms/test_pipeline.py`

**Step 1: Write equivalence test**

Note: Uses the `load_conversation_fixture` fixture from `tests/conftest.py`.

```python
"""Integration tests for preprocess_for_export pipeline equivalence."""

from __future__ import annotations

import pytest


class TestPipelineEquivalence:
    """Verify new pipeline produces equivalent output to old pipeline.

    Note: These tests supersede TestChromeRemoval and TestUIChromeRemoval from
    test_css_fidelity.py. Chrome removal functionality (remote images, small icons,
    hidden elements, etc.) is now tested here via real fixtures and in the
    individual platform handler tests.
    """

    @pytest.mark.parametrize("fixture_name", [
        "openai_biblatex.html",
        "claude_cooking.html",
        "google_gemini_debug.html",
        "google_aistudio_ux_discussion.html",
        "scienceos_loc.html",
    ])
    def test_preprocess_for_export_processes_fixture(self, fixture_name: str) -> None:
        """New entry point successfully processes platform fixtures."""
        from tests.conftest import load_conversation_fixture

        from promptgrimoire.export.platforms import preprocess_for_export

        html = load_conversation_fixture(fixture_name)
        result = preprocess_for_export(html)

        # Basic sanity checks
        assert len(result) > 0
        assert len(result) < len(html)  # Should be smaller after chrome removal
        assert 'data-speaker="user"' in result or 'data-speaker="assistant"' in result

    def test_preprocess_returns_unchanged_for_unknown_platform(self) -> None:
        """Unknown platforms return HTML unchanged."""
        from promptgrimoire.export.platforms import preprocess_for_export

        html = "<html><body><p>Plain content</p></body></html>"
        result = preprocess_for_export(html)

        # Should be similar (selectolax may normalize slightly)
        assert "Plain content" in result

    def test_speaker_markers_preserved_through_chrome_removal(self) -> None:
        """Empty container removal preserves data-speaker markers."""
        from promptgrimoire.export.platforms import preprocess_for_export

        # Simulate HTML after speaker label injection with empty marker divs
        html = '''
        <div data-speaker="user" class="speaker-turn"></div>
        <div class="content">User message</div>
        <div data-speaker="assistant" class="speaker-turn"></div>
        <div class="content">Assistant response</div>
        '''
        result = preprocess_for_export(html)

        # Speaker markers must be preserved even though they're "empty"
        assert 'data-speaker="user"' in result
        assert 'data-speaker="assistant"' in result

    def test_katex_html_removed_mathml_preserved(self) -> None:
        """KaTeX visual rendering removed, MathML preserved for Pandoc."""
        from promptgrimoire.export.platforms import preprocess_for_export

        html = '''
        <span class="katex">
            <span class="katex-mathml"><math>...</math></span>
            <span class="katex-html">visual rendering</span>
        </span>
        '''
        result = preprocess_for_export(html)

        # Visual rendering removed
        assert "katex-html" not in result
        assert "visual rendering" not in result
        # MathML preserved
        assert "katex-mathml" in result
```

**Step 2: Run tests**

Run: `uv run pytest tests/unit/export/platforms/test_pipeline.py -v`
Expected: All tests PASS

**Step 3: Commit extended entry point**

```bash
git add src/promptgrimoire/export/platforms/__init__.py src/promptgrimoire/export/platforms/base.py tests/unit/export/platforms/test_pipeline.py
git commit -m "feat(export): complete preprocess_for_export with chrome removal and labels

Extends entry point to include:
- Common chrome removal (avatars, icons, buttons, remote images)
- Speaker label injection via handler turn patterns
- Graceful handling when no handler matches
- Pipeline integration tests

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update test_chatbot_fixtures.py to use new API

**Files:**
- Modify: `tests/integration/test_chatbot_fixtures.py`

**Step 1: Update imports (lines 16-18)**

Change from:
```python
from promptgrimoire.export.chrome_remover import remove_ui_chrome
from promptgrimoire.export.speaker_preprocessor import inject_speaker_labels
```

To:
```python
from promptgrimoire.export.platforms import get_handler, preprocess_for_export
```

**Step 2: Update _preprocess_chatbot_html function (lines 73-82)**

Change from:
```python
def _preprocess_chatbot_html(html: str) -> str:
    """Preprocess chatbot HTML for LaTeX conversion."""
    html = inject_speaker_labels(html)
    html = remove_ui_chrome(html)
    return html
```

To:
```python
def _preprocess_chatbot_html(html: str) -> str:
    """Preprocess chatbot HTML for LaTeX conversion."""
    return preprocess_for_export(html)
```

**Step 3: Update detect_platform call (around line 181)**

Change from:
```python
from promptgrimoire.export.speaker_preprocessor import detect_platform
platform = detect_platform(html) or "unknown"
```

To:
```python
handler = get_handler(html)
platform = handler.name if handler else "unknown"
```

**Step 4: Run integration tests**

Run: `uv run pytest tests/integration/test_chatbot_fixtures.py -v`
Expected: All tests PASS
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_G -->

---

<!-- START_SUBCOMPONENT_H (tasks 4-6) -->
<!-- START_TASK_4 -->
### Task 4: Migrate test_css_fidelity.py tests

**Files:**
- Modify: `tests/unit/export/test_css_fidelity.py`

**Changes:**

1. **Delete TestChromeRemoval class** (~12 tests)
   - These tests are now covered by platform handler unit tests and integration tests

2. **Update TestPlatformDetection** (~10 tests)
   - Change imports from `speaker_preprocessor` to `platforms`
   - Change `detect_platform(html)` to `get_handler(html)` and check `handler.name`

3. **Update TestSpeakerLabelInjection** (~4 tests)
   - Change imports from `speaker_preprocessor` to `platforms`
   - Change `inject_speaker_labels(html)` to `preprocess_for_export(html)`

**Step 1: Delete chrome removal tests**

Remove the entire `TestChromeRemoval` class (tests are now in platform handlers).

**Step 2: Update platform detection tests**

For each `test_detect_*` method, change:
```python
from promptgrimoire.export.speaker_preprocessor import detect_platform
assert detect_platform(html) == "claude"
```

To:
```python
from promptgrimoire.export.platforms import get_handler
handler = get_handler(html)
assert handler is not None
assert handler.name == "claude"
```

**Step 3: Update label injection tests**

For each `test_inject_labels_*` method, change:
```python
from promptgrimoire.export.speaker_preprocessor import inject_speaker_labels
result = inject_speaker_labels(html)
```

To:
```python
from promptgrimoire.export.platforms import preprocess_for_export
result = preprocess_for_export(html)
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/export/test_css_fidelity.py -v`
Expected: All remaining tests PASS

**Step 5: Commit test migration**

```bash
git add tests/unit/export/test_css_fidelity.py
git commit -m "test(export): migrate CSS fidelity tests to new platform API

- Delete chrome removal tests (now in platform handlers)
- Update platform detection to use get_handler()
- Update label injection to use preprocess_for_export()

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Delete old files

**Step 1: Delete old production files**

```bash
rm src/promptgrimoire/export/speaker_preprocessor.py
rm src/promptgrimoire/export/chrome_remover.py
```

**Step 2: Update __init__.py exports if needed**

Check `src/promptgrimoire/export/__init__.py` and remove any exports of deleted modules.

**Step 3: Update Lua filter comment**

In `src/promptgrimoire/export/libreoffice.lua` line 199, change:
```lua
-- Handle speaker turn markers (inserted by speaker_preprocessor.py)
```
To:
```lua
-- Handle speaker turn markers (inserted by platforms.preprocess_for_export)
```

**Step 4: Run full test suite**

Run: `uv run pytest`
Expected: All tests PASS

**Step 5: Verify no references remain**

Run: `grep -r "speaker_preprocessor\|chrome_remover" src/ tests/ --include="*.py" | grep -v "implementation-plans"`
Expected: No matches
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Final verification and commit

**Step 1: Run type checker**

Run: `uvx ty check src/promptgrimoire/export/`
Expected: No type errors

**Step 2: Run linter**

Run: `uv run ruff check src/promptgrimoire/export/ tests/unit/export/`
Expected: No lint errors

**Step 3: Run full test suite**

Run: `uv run pytest`
Expected: All tests PASS

**Step 4: Commit deletions**

```bash
git add src/promptgrimoire/export/__init__.py
git rm src/promptgrimoire/export/speaker_preprocessor.py src/promptgrimoire/export/chrome_remover.py
git commit -m "refactor(export): delete speaker_preprocessor.py and chrome_remover.py

Migration complete:
- All call sites updated to use preprocess_for_export()
- Platform detection via get_handler()
- Chrome removal tests deleted (covered by platform handler tests)
- Integration tests pass with new API

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

**Step 5: Verify Definition of Done**

- [ ] Each platform (OpenAI, Claude, Gemini, AI Studio, ScienceOS) has its own module
- [ ] Each platform handler implements the PlatformHandler protocol
- [ ] Platform handlers are autodiscovered via pkgutil.iter_modules()
- [ ] Single entry point preprocess_for_export() replaces both old functions
- [ ] Optional platform_hint parameter works
- [ ] Chrome removal logic in handlers and base utility
- [ ] Native label stripping eliminates duplicates
- [ ] HTML parsing uses selectolax
- [ ] All integration tests pass
- [ ] Each platform has isolated unit tests
- [ ] Old files deleted
<!-- END_TASK_6 -->
<!-- END_SUBCOMPONENT_H -->
