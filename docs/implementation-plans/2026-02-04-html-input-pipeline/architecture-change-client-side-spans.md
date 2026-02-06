# Architecture Change: Client-Side Char Span Injection

**Date:** 2026-02-05
**Issue:** #106 HTML Input Pipeline
**Status:** ✅ Implemented
**Reason:** Websocket message size limit hit with 32K character document (~1.8MB after span injection)

## Problem

Server-side char span injection multiplies content size ~55x:
- 32,735 characters → ~1.8MB HTML
- NiceGUI websockets can't handle this payload
- Error: "message too long for websocket transmission"

## Solution

Move char span injection from server to client (JavaScript).

### Before (Server-Side)

```
User paste → process_input() → inject_char_spans() → 1.8MB stored in DB
                                                    ↓
                                              websocket (1.8MB)
                                                    ↓
                                              ui.html() renders
```

### After (Client-Side)

```
User paste → process_input() → clean HTML stored in DB (~32KB)
                                    ↓
                              websocket (~32KB)
                                    ↓
                              ui.html() renders
                                    ↓
                              JavaScript injects char spans in DOM
```

## Benefits

1. **Smaller websocket payloads** - Clean HTML only
2. **Simpler export** - No need to strip char spans before PDF export
3. **Faster storage** - Less data in database
4. **Same functionality** - Selection/highlighting still works via DOM spans

## Implementation Details

### 1. `process_input()` - Returns clean HTML

```python
# html_input.py - process_input() now returns preprocessed HTML
# without char spans (they're injected client-side)
return preprocessed  # Clean HTML, no char spans
```

### 2. `extract_text_from_html()` for server-side text extraction

```python
def extract_text_from_html(html: str) -> list[str]:
    """Extract text characters from clean HTML (no char spans).

    Used for building document_chars list server-side when char spans
    are injected client-side.
    """
    tree = LexborHTMLParser(html)
    body = tree.body
    root = body if body else tree.root
    if root is None:
        return []
    text = root.text() or ""
    return list(text)
```

### 3. Client-side JavaScript for span injection

In `annotation.py`, after `ui.html()` renders the document, JavaScript
processes each text node and wraps characters in spans:

```javascript
// Walks DOM tree, wrapping each text character in:
// <span class="char" data-char-index="N">c</span>
function processNode(node) {
    if (node.nodeType === Node.TEXT_NODE) {
        // Wrap each character in a span
        for (const char of text) {
            const span = document.createElement('span');
            span.className = 'char';
            span.dataset.charIndex = charIndex++;
            span.textContent = char;
            // ...
        }
    }
    // Recursively process child nodes
}
```

### 4. `_render_document_with_highlights()` updated

- Sends clean HTML via `ui.html()`
- Runs JavaScript to inject spans after render
- Extracts text server-side using `extract_text_from_html()` for `document_chars`

### 5. Export path simplified

- Database stores clean HTML
- No need to call `strip_char_spans()` before PDF export
- Phase 6 becomes simpler

## Files Modified

- `src/promptgrimoire/input_pipeline/html_input.py`
  - `process_input()` returns clean HTML
  - Added `extract_text_from_html()` function
- `src/promptgrimoire/pages/annotation.py`
  - Added JavaScript for client-side span injection
  - Updated `_render_document_with_highlights()` to use `extract_text_from_html()`
- `tests/unit/input_pipeline/test_process_input.py`
  - Updated tests to expect clean HTML (no char spans)
- `tests/unit/input_pipeline/test_char_spans.py`
  - Added tests for `extract_text_from_html()`

## Migration

No migration needed - this is pre-launch. New documents will have clean HTML.
Existing test documents can be re-created.

## Testing

All 1819 unit tests pass after this change.
