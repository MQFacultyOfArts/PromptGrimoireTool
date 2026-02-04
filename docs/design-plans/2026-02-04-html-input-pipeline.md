# HTML Input Pipeline Design (Issue #106)

## Status: VALIDATED

**Last updated:** 2026-02-05
**Issue:** #106 (Annotation page: Accept raw HTML paste from chatbot exports)
**Related:** #76 (CSS Fidelity - LaTeX pipeline), #101 (CJK/BLNS), #109 (File upload support)

---

## Summary

Enable the annotation page to accept HTML input (paste or upload) from chatbot exports (Claude, ChatGPT, Gemini), blog posts, AustLII legal documents, and other sources. Currently the annotation page only accepts plain text via textarea. This design introduces an HTML-aware input pipeline that preserves document structure (headings, lists, tables) while enabling character-level annotation.

**Key architectural decisions:**
- **Single source of truth:** `content` field stores HTML with `data-char-index` spans. `raw_content` removed.
- **Clean break to char-based indexing:** All word-based indexing (`start_word`, `end_word`) replaced with char-based (`start_char`, `end_char`) throughout CRDT, UI, and export layers. No migration needed (pre-launch).
- **Single input path:** All input types (HTML, RTF, DOCX, PDF, plain text) go through the same HTML pipeline.
- **source_type field:** Store detected/confirmed content type for potential citation use.

## Definition of Done

1. User can paste HTML from clipboard (text/html MIME type) into annotation page
2. User can upload files (.html, .rtf, .docx, .pdf, .txt)
3. HTML structure (headings, lists, tables, paragraphs) is preserved in annotation view
4. Character-level selection works on HTML content
5. PDF export produces correct output from HTML content with annotations
6. Platform preprocessing (chrome removal, speaker labels) applied to chatbot exports
7. Plain text goes through same pipeline (wrapped in `<p>` tags)

## Glossary

- **Platform handler**: Module that detects and preprocesses HTML from specific AI platforms (Claude, OpenAI, Gemini, etc.)
- **Chrome**: UI elements (avatars, copy buttons, timestamps) that should be removed from chatbot exports
- **Char span**: `<span class="char" data-char-index="N">` wrapper around each text character for selection
- **preprocess_for_export()**: Existing function in `export/platforms/__init__.py` that removes chrome and injects speaker labels

## Architecture

### Data Model

```python
# WorkspaceDocument (models.py)
class WorkspaceDocument(SQLModel, table=True):
    id: UUID
    workspace_id: UUID
    type: str                    # "source", "draft", "ai_conversation"
    content: str                 # HTML with data-char-index spans (THE source of truth)
    source_type: str             # "html", "rtf", "docx", "pdf", "text" (for citation)
    order_index: int
    title: str | None
    created_at: datetime

    # REMOVED: raw_content
```

```python
# Highlight schema (CRDT layer - annotation_doc.py)
highlight = {
    "id": str,
    "document_id": str,
    "start_char": int,          # Was: start_word
    "end_char": int,            # Was: end_word
    "tag": str,
    "color": str,
    "text": str,
    "created_by": str,
}
```

```python
# UI selection state (annotation.py)
class ClientState:
    selection_start: int | None  # char index
    selection_end: int | None    # char index
    cursor_char: int | None      # was cursor_word
```

### Input Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                         INPUT                                    │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│ HTML paste   │ File upload  │ RTF/DOCX     │ Plain text        │
│ (clipboard)  │ (.html)      │ (LibreOffice)│ (wrap in <p>)     │
└──────┬───────┴──────┬───────┴──────┬───────┴──────────┬────────┘
       └──────────────┴──────────────┴─────────────────┘
                              │
                              ▼
                 ┌────────────────────────┐
                 │ detect_content_type()  │
                 │ (sniff MIME/structure) │
                 └───────────┬────────────┘
                             │
                             ▼
                 ┌────────────────────────┐
                 │ show_content_type_     │
                 │ dialog() - AWAIT       │
                 │ (confirm or override)  │
                 └───────────┬────────────┘
                             │
                             ▼
                 ┌────────────────────────┐
                 │ convert_to_html()      │
                 │ (LibreOffice/Pandoc)   │
                 └───────────┬────────────┘
                             │
                             ▼
                 ┌────────────────────────┐
                 │ preprocess_for_export()│
                 │ (reuse #76 handlers)   │
                 └───────────┬────────────┘
                             │
                             ▼
                 ┌────────────────────────┐
                 │ inject_char_spans()    │
                 │ (selectolax DOM walk)  │
                 └───────────┬────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │     WorkspaceDocument        │
              │  content: HTML + char spans  │
              │  source_type: confirmed type │
              └──────────────────────────────┘
```

### Annotation UI Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    ANNOTATION VIEW                               │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ <span data-char-index="0">H</span>                        │  │
│  │ <span data-char-index="1">e</span>                        │  │
│  │ <span data-char-index="2">l</span>  ← User clicks/drags   │  │
│  │ ...                                                        │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │ JS: mousedown/mouseup events  │
              │ Extract data-char-index from  │
              │ selection start/end spans     │
              └───────────────┬───────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │ Python: ClientState           │
              │ selection_start: int (char)   │
              │ selection_end: int (char)     │
              └───────────────┬───────────────┘
                              │
                              ▼ (user clicks "Add Highlight")
              ┌───────────────────────────────┐
              │ CRDT: add_highlight()         │
              │ start_char, end_char, tag...  │
              └───────────────┬───────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │ Render: Apply highlight CSS   │
              │ to spans in [start, end)      │
              └───────────────────────────────┘
```

### Export Path

```
┌──────────────────────────────────────────────────────────────┐
│                 WorkspaceDocument                             │
│  content: HTML with <span class="char" data-char-index="N">  │
│  + CRDT highlights: [{start_char, end_char, tag, color}...]  │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
             ┌─────────────────────────────┐
             │ strip_char_spans(content)   │
             │ selectolax span.unwrap()    │
             └─────────────┬───────────────┘
                           │
                           ▼
             ┌─────────────────────────────┐
             │ Clean HTML (structure only) │
             │ No char spans, no chrome    │
             └─────────────┬───────────────┘
                           │
                           ▼
      ┌────────────────────────────────────────────────┐
      │ Existing #76 pipeline (latex.py)               │
      │ _insert_markers_into_html() → Pandoc → LaTeX   │
      │ (already uses start_char/end_char with shims)  │
      └────────────────────────────────────────────────┘
```

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage model | Single source (`content` only) | Eliminates sync issues |
| `raw_content` | Removed | No longer needed with char-based indexing |
| `source_type` field | Added | Potential citation use, reprocessing |
| Indexing | Char-based throughout | Clean break, no migration (pre-launch) |
| Single input path | All types → HTML pipeline | Consistency, no special cases |
| Content type dialog | Autodetect + confirm modal | User can override if detection is wrong |
| Char span injection | selectolax DOM walk | Already a dependency, fast, preserves structure |
| Char span stripping | selectolax `span.unwrap()` | Safer than regex for HTML manipulation |
| RTF/DOCX conversion | LibreOffice (not Pandoc) | Pandoc RTF support is limited |
| Whitespace handling | Preserve as entities | Prevents HTML collapse of significant whitespace |
| `<br>` tags | Treat as newline character (gets index) | Consistent with text semantics |

## Spikes Required

Three approaches for HTML input must be spiked to determine the best mechanism:

| # | Approach | What to Test | Pros | Cons |
|---|----------|--------------|------|------|
| **D** | `ui.editor` (Quasar QEditor) | Does paste preserve chatbot HTML structure? Does `.value` give clean HTML? | NiceGUI-native, no custom JS | WYSIWYG editor may be overkill |
| **A** | `js_handler` on paste event | Cross-browser clipboard access? Edge cases? | Full control over clipboard data | Custom JS (5 lines) |
| **B** | Contenteditable div | Browser normalisation issues? innerHTML reliability? | Native HTML paste | Browser quirks, cursor issues |

**Spike D first** - if `ui.editor` preserves HTML on paste and gives us clean `.value`, no custom JS needed.

Additional spikes:
- **LibreOffice conversion**: Test RTF and DOCX conversion quality
- **selectolax text node iteration**: Verify `include_text=True` behavior with complex nested HTML

## Implementation Components

### 1. New Module: `src/promptgrimoire/import/html_input.py`

```python
CONTENT_TYPES = ["html", "rtf", "docx", "pdf", "text"]

def detect_content_type(content: str | bytes) -> str:
    """Sniff content type from magic bytes/structure."""

async def convert_to_html(
    content: str | bytes,
    source_type: Literal["html", "rtf", "docx", "pdf", "text"],
) -> str:
    """Convert any supported format to HTML via LibreOffice/Pandoc."""

def inject_char_spans(html: str) -> str:
    """Walk HTML DOM, wrap each text character in data-char-index span."""

async def process_input(content: str | bytes, source_type: str) -> str:
    """Full pipeline: convert → preprocess → inject spans."""
```

### 2. New Module: `src/promptgrimoire/pages/dialogs.py`

```python
async def show_content_type_dialog(
    detected_type: str,
    preview: str = "",
) -> str | None:
    """Awaitable modal to confirm or override detected content type.

    Returns selected type, or None if cancelled.
    """
```

### 3. Content Type Detection Heuristics

| Signal | Detected Type |
|--------|---------------|
| Starts with `<!DOCTYPE` or `<html` | html |
| Starts with `{\rtf` | rtf |
| File extension `.docx` / PK magic bytes | docx |
| File extension `.pdf` / `%PDF` magic | pdf |
| Clipboard `text/html` MIME present | html |
| Default fallback | text |

### 4. Char Span Injection

Walk preprocessed HTML DOM with selectolax. For each text node:
- Wrap each character in `<span class="char" data-char-index="N">`
- Increment index counter
- Preserve surrounding HTML structure (headings, lists, tables)
- Whitespace characters get spans (stored as entities like `&nbsp;`)
- `<br>` tags become newline chars with indices

### 5. Char Span Stripping (for PDF export)

```python
def strip_char_spans(html_with_spans: str) -> str:
    """Remove char span wrappers, preserving content."""
    tree = LexborHTMLParser(html_with_spans)
    for span in tree.css('span.char[data-char-index]'):
        span.unwrap()
    return tree.html
```

### 6. Text Extraction for Highlights

```python
def extract_text_from_char_range(content_html: str, start: int, end: int) -> str:
    """Extract text from char spans in range [start, end)."""
    tree = LexborHTMLParser(content_html)
    chars = []
    for span in tree.css('span.char[data-char-index]'):
        idx = int(span.attributes.get('data-char-index', -1))
        if start <= idx < end:
            chars.append(span.text() or '')
    return ''.join(chars)
```

## Implementation Phases

### Phase 0: Spikes
- Spike D: Test `ui.editor` for HTML paste preservation
- Spike A: Test `js_handler` clipboard access cross-browser
- Spike B: Test contenteditable div approach
- Spike: LibreOffice RTF/DOCX conversion quality
- Spike: selectolax text node iteration with nested HTML

### Phase 1: Schema Changes
- Alembic migration: remove `raw_content`, add `source_type`
- Update `WorkspaceDocument` model
- Update `create_workspace_document()` function

### Phase 2: CRDT/UI Rename
- `start_word` → `start_char` in `annotation_doc.py`
- `end_word` → `end_char` in `annotation_doc.py`
- Update `ClientState` in `annotation.py`
- Update all word-based references in UI layer

### Phase 3: Input Pipeline
- Create `import/html_input.py` module
- Implement `detect_content_type()`
- Implement `inject_char_spans()` with selectolax
- Implement `process_input()` orchestration
- Unit tests for injection roundtrip

### Phase 4: Content Dialog
- Create `pages/dialogs.py`
- Implement `show_content_type_dialog()`
- Integrate into paste/upload flow

### Phase 5: UI Integration
- Add paste/input handler (based on spike winner)
- Add file upload component
- Integrate `process_input()` into document creation
- Update `handle_add_document()` to use new pipeline

### Phase 6: Export Integration
- Add `strip_char_spans()` to export path
- Remove `raw_content` usage from `pdf_export.py`
- Clean up migration shims in `latex.py` (optional)
- Verify existing #76 tests still pass

### Phase 7: Format Conversion
- Add LibreOffice conversion for RTF/DOCX
- Add pdftohtml or LibreOffice for PDF
- Integration tests for each format

### Phase 8: E2E Tests
- Reimplement skipped annotation E2E tests with HTML input
- Test paste flow with various chatbot exports
- Test file upload flow

## Related Issues

- **#76**: CSS Fidelity - LaTeX pipeline (OUTPUT side, already implemented)
- **#101**: CJK/BLNS support (character tokenization, already implemented)
- **#104**: Extract WordSpanProcessor (superseded by this design)
- **#109**: File upload support (incorporated into this design)
- **#116**: Platform handler refactor (preprocessing used by this design)

## Resolved Questions

| Question | Answer | Design Impact |
|----------|--------|---------------|
| Store `source_type`? | Yes - may become citation | Added `source_type: str` field |
| Conversion failures? | Autodetect + dropdown modal | Added `show_content_type_dialog()` |
| Plain text path? | One path only - goes through HTML | Plain text wrapped in `<p>` tags |
