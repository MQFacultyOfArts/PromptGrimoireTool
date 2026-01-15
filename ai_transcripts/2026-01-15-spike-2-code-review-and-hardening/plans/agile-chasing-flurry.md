# Code Review: Spike 1 & Spike 2 - Notes for Main Programmer

**Reviewer:** Claude Opus 4.5
**Date:** 2026-01-15
**Scope:** CRDT real-time sync (spike 1) + Text selection annotation (spike 2)

---

## Executive Summary

The spike work demonstrates competent implementation of CRDT synchronization and text selection features. Test coverage is strong for E2E and integration layers. However, there are **critical issues with multi-user state isolation** and several areas needing attention before production.

**Overall Assessment:** Good spike work that validates the technical approach. Needs refactoring for multi-user correctness before merge.

---

## CRITICAL Issues (Must Fix Before Merge)

### 1. Global Mutable State Not User-Isolated

**Location:** [text_selection.py:16](src/promptgrimoire/pages/text_selection.py#L16), [text_selection.py:109](src/promptgrimoire/pages/text_selection.py#L109)

```python
_current_selection: dict[str, str | int] = {}  # Module-level global

async def handle_selection(e) -> None:
    global _current_selection  # Shared across ALL users
```

**Problem:** In a multi-user scenario, one user's selection overwrites another's. This is a data leakage bug.

**Fix:** Use NiceGUI's per-client context storage:
```python
# Store per-client, not globally
if not hasattr(ui.context, 'selection'):
    ui.context.selection = {}
ui.context.selection = {"text": text, "start": start, "end": end}
```

### 2. Range Object May Become Invalid

**Location:** [text_selection.py:148-149](src/promptgrimoire/pages/text_selection.py#L148-L149)

```javascript
window._savedRange = range.cloneRange();
```

**Problem:** DOM Range objects become invalid when the DOM changes. If content reflows or updates occur between selection and highlight, `_savedRange` will silently fail or throw.

**Fix:** Store selection data (start/end offsets, text) instead of the Range object. Reconstruct the range when needed for highlighting.

### 3. Thread Safety in CRDT Origin Tracking

**Location:** [sync.py:50-52](src/promptgrimoire/crdt/sync.py#L50-L52)

```python
self._current_origin = origin_client_id
self.doc.apply_update(update)
self._current_origin = None
```

**Problem:** In async/multi-threaded NiceGUI, concurrent updates could interfere with `_current_origin`. If two updates arrive simultaneously, one's origin gets lost.

**Fix:** Use `contextvars.ContextVar` for async-safe context:
```python
from contextvars import ContextVar
_origin_var: ContextVar[str | None] = ContextVar('origin', default=None)
```

---

## HIGH Priority Issues

### 4. Missing Type Hint on Event Handler

**Location:** [text_selection.py:107](src/promptgrimoire/pages/text_selection.py#L107)

```python
async def handle_selection(e) -> None:  # 'e' untyped
```

**Fix:** Add proper type annotation. Check NiceGUI's event types (likely `GenericEventArguments` or similar).

### 5. No Input Validation on Event Args

**Location:** [text_selection.py:110-112](src/promptgrimoire/pages/text_selection.py#L110-L112)

```python
text = e.args.get("text", "")
start = e.args.get("start", 0)
end = e.args.get("end", 0)
```

**Problem:** No validation that `start` and `end` are integers, or that `start <= end`, or that text matches the range length.

**Fix:** Add validation:
```python
if not isinstance(start, int) or not isinstance(end, int):
    return
if start > end or end - start != len(text):
    return  # Invalid selection data
```

### 6. HTML Sanitization Disabled

**Location:** [text_selection.py:57](src/promptgrimoire/pages/text_selection.py#L57)

```python
sanitize=False,
```

**Risk:** Safe for hardcoded demo content, but if this pattern is copied for user-provided content, it enables XSS attacks.

**Fix:** Add a warning comment, or create a separate trusted HTML component:
```python
# WARNING: sanitize=False is ONLY safe for static/trusted content.
# NEVER use with user-provided content.
```

### 7. Silent Failures in JavaScript

**Location:** [text_selection.py:86-93](src/promptgrimoire/pages/text_selection.py#L86-L93)

```javascript
} catch (e) {
    // surroundContents fails if range spans multiple elements
    const fragment = window._savedRange.extractContents();
    // ...
}
```

**Problem:** The catch block has no error logging. If both approaches fail, debugging is nearly impossible.

**Fix:** Add console logging and return error status to Python:
```javascript
} catch (e) {
    console.warn('Highlight fallback used:', e.message);
    try {
        // fallback approach
    } catch (e2) {
        console.error('Highlight failed:', e2);
        return {success: false, error: e2.message};
    }
}
```

---

## MEDIUM Priority Issues

### 8. Hard-Coded Port Number

**Location:** [__init__.py:21](src/promptgrimoire/__init__.py#L21)

```python
ui.run(port=8080, reload=False)
```

**Fix:** Use environment variable with default:
```python
port = int(os.environ.get("PROMPTGRIMOIRE_PORT", "8080"))
ui.run(port=port, reload=False)
```

### 9. Magic Numbers Without Constants

**Location:** [text_selection.py:165](src/promptgrimoire/pages/text_selection.py#L165)

```javascript
setTimeout(checkAndEmitSelection, 10);  // Why 10ms?
```

Also [text_selection.py:116](src/promptgrimoire/pages/text_selection.py#L116):
```python
f'"{text[:50]}..."' if len(text) > 50  # Why 50?
```

**Fix:** Define constants with explanatory names:
```python
SELECTION_DEBOUNCE_MS = 10  # Debounce to let browser finalize selection
MAX_DISPLAY_LENGTH = 50  # Truncate displayed text for readability
```

### 10. Module-Level Singleton Pattern Doesn't Scale

**Location:** [sync_demo.py](src/promptgrimoire/pages/sync_demo.py) (not directly read but mentioned in spike 1)

```python
shared_doc = SharedDocument()  # Single document for all users
```

**Problem:** Works for demo, but production needs document-per-room/conversation.

**Recommendation:** Document this as a known limitation. Plan refactoring for document isolation when implementing persistence.

### 11. Loose Typing on Client Data

**Location:** [sync.py:26](src/promptgrimoire/crdt/sync.py#L26)

```python
self._clients: dict[str, Any] = {}
```

**Fix:** Define a proper type or TypedDict:
```python
from typing import TypedDict

class ClientData(TypedDict):
    ui_elements: tuple[Label, Input]
    connected_at: float

self._clients: dict[str, ClientData] = {}
```

---

## Test Suite Issues

### 12. Primary Use Case Not Tested - Click-Drag Selection

**Location:** [test_text_selection.py](tests/e2e/test_text_selection.py)

All selection tests use triple-click:
```python
content.locator("p").first.click(click_count=3)  # Always triple-click
```

**Problem:** The actual primary use case (click-drag to select arbitrary text) is never tested.

**Fix:** Add Playwright drag-to-select test:
```python
def test_click_drag_selection(self, page: Page, text_selection_url: str) -> None:
    """User can click-drag to select partial text."""
    page.goto(text_selection_url)
    content = page.get_by_test_id("selectable-content")
    p = content.locator("p").first

    # Get bounding box and drag within it
    box = p.bounding_box()
    page.mouse.move(box["x"] + 10, box["y"] + 10)
    page.mouse.down()
    page.mouse.move(box["x"] + 100, box["y"] + 10)
    page.mouse.up()

    expect(page.get_by_test_id("selected-text")).not_to_have_text("No selection")
```

### 13. Anti-Pattern: Hard-Coded Wait

**Location:** [test_text_selection.py:217](tests/e2e/test_text_selection.py#L217)

```python
page.wait_for_timeout(500)  # Arbitrary sleep
```

**Problem:** Creates flakiness and slows tests.

**Fix:** Use condition-based waiting:
```python
expect(content.locator("p").first).to_be_visible()
# JavaScript handlers are ready once content is visible and page is stable
```

### 14. Missing Test Assertions

**Location:** [test_text_selection.py:238](tests/e2e/test_text_selection.py#L238)

```python
def test_multiline_selection(self, ...):
    # ...
    expect(selected_text).not_to_have_text("No selection", timeout=2000)
    # Missing: Assert that multiline text was actually captured correctly
```

**Fix:** Add assertion that validates the captured text spans multiple paragraphs.

### 15. No Unit Tests for Non-UI Components

**Observation:** `tests/unit/test_example.py` only tests version string. No unit tests for:
- Parsers (`src/promptgrimoire/parsers/`)
- Models
- CRDT operations (only integration tests exist)

**Recommendation:** Add unit tests for parser logic before Feb 23 launch.

---

## Documentation Gaps

### 16. Event Handler Contract Undocumented

**Location:** [text_selection.py:107-112](src/promptgrimoire/pages/text_selection.py#L107-L112)

The handler expects `e.args` to have specific keys (`text`, `start`, `end`) but this isn't documented.

**Fix:** Add docstring with expected event structure:
```python
async def handle_selection(e: GenericEventArguments) -> None:
    """Handle text selection from browser.

    Expected e.args:
        text (str): Selected text content
        start (int): Start offset within container
        end (int): End offset within container
    """
```

### 17. Browser Requirements Undocumented

The text selection feature requires:
- JavaScript enabled
- Modern browser with `window.getSelection()` API
- `Range.surroundContents()` or `extractContents()` support

**Recommendation:** Add browser requirements to module docstring or README.

---

## Architecture Observations

### Strengths

1. **Clean CRDT abstraction** - `SharedDocument` class nicely encapsulates pycrdt
2. **Comprehensive E2E fixtures** - `conftest.py` has excellent subprocess and context management
3. **Test-friendly UI** - Consistent use of `data-testid` attributes
4. **Good async patterns** - Proper use of `await ui.context.client.connected()`

### Areas for Future Improvement

1. **Page module duplication** - Both demo pages duplicate connection handling; consider base class
2. **No shared utilities** - JavaScript injection patterns repeated; consider helper module
3. **Callback typing** - The `_broadcast_callback` typing is correct but complex; consider Protocol class

---

## Summary Checklist

### Before Merge
- [ ] Fix global `_current_selection` state isolation (CRITICAL)
- [ ] Add type hint to event handler parameter
- [ ] Add input validation on event args
- [ ] Add click-drag selection test
- [ ] Remove `wait_for_timeout(500)` anti-pattern

### Before Production
- [ ] Implement per-session state storage
- [ ] Add error logging to JavaScript fallbacks
- [ ] Fix thread safety in CRDT origin tracking
- [ ] Add unit tests for parsers
- [ ] Document browser requirements

### Nice to Have
- [ ] Extract magic numbers to constants
- [ ] Make port configurable via environment
- [ ] Add TypedDict for selection data structure
- [ ] Consider Range validation before use

---

## Verification

To verify fixes work correctly:

1. **Multi-user isolation test:**
   - Open two browser tabs
   - Select different text in each
   - Verify each tab shows its own selection (not the other's)

2. **Range invalidation test:**
   - Select text
   - Trigger a UI update that modifies the DOM
   - Click "Create Highlight"
   - Verify graceful failure or correct behavior

3. **Run full test suite:**
   ```bash
   uv run pytest tests/ -v
   ```
