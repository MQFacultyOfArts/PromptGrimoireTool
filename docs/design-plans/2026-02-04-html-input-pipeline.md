# HTML Input Pipeline Design (Issue #106)

## Status: WIP - BRAINSTORM COMPLETE

**Last updated:** 2026-02-04
**Issue:** #106 (Annotation page: Accept raw HTML paste from chatbot exports)
**Related:** #76 (CSS Fidelity - LaTeX pipeline), #101 (CJK/BLNS), #109 (File upload support)

---

## Summary

Enable the annotation page to accept HTML input (paste or upload) from chatbot exports (Claude, ChatGPT, Gemini), blog posts, AustLII legal documents, and other sources. Currently the annotation page only accepts plain text via textarea. This design introduces an HTML-aware input pipeline that preserves document structure (headings, lists, tables) while enabling character-level annotation.

**Key architectural decision:** Single source of truth model. The `content` field stores HTML with `data-char-index` spans. The `raw_content` field is deprecated. PDF export strips the char spans and uses the existing #76 LaTeX pipeline.

## Definition of Done

1. User can paste HTML from clipboard (text/html MIME type) into annotation page
2. User can upload files (.html, .rtf, .docx, .pdf, .txt)
3. HTML structure (headings, lists, tables, paragraphs) is preserved in annotation view
4. Character-level selection works on HTML content (existing char span system)
5. PDF export produces correct output from HTML content with annotations
6. Platform preprocessing (chrome removal, speaker labels) applied to chatbot exports
7. Plain text paste continues to work (backwards compatible)

## Glossary

- **Platform handler**: Module that detects and preprocesses HTML from specific AI platforms (Claude, OpenAI, Gemini, etc.)
- **Chrome**: UI elements (avatars, copy buttons, timestamps) that should be removed from chatbot exports
- **Char span**: `<span class="char" data-char-index="N">` wrapper around each text character for selection
- **preprocess_for_export()**: Existing function in `export/platforms/__init__.py` that removes chrome and injects speaker labels

## Architecture

### Single Source of Truth Model

```
┌─────────────────────────────────────────────────────────────┐
│                        INPUT                                 │
├──────────────┬──────────────┬──────────────┬────────────────┤
│ HTML paste   │ File upload  │ RTF/DOCX     │ Plain text     │
│ (clipboard)  │ (.html)      │ (LibreOffice)│ (legacy)       │
└──────┬───────┴──────┬───────┴──────┬───────┴───────┬────────┘
       │              │              │               │
       └──────────────┴──────────────┴───────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ preprocess_for_ │
                    │ export()        │
                    │ (remove chrome) │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ inject_char_    │
                    │ spans()         │
                    │ (NEW FUNCTION)  │
                    └────────┬────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │     WorkspaceDocument        │
              │  content: HTML + char spans  │
              │  raw_content: "" (deprecated)│
              └──────────────┬───────────────┘
                             │
            ┌────────────────┴────────────────┐
            │                                 │
            ▼                                 ▼
    ┌───────────────┐               ┌─────────────────┐
    │ Annotation UI │               │ PDF Export      │
    │ (char spans   │               │ (strip spans →  │
    │  for selection)│              │  latex.py)      │
    └───────────────┘               └─────────────────┘
```

### Data Flow

**Input → Storage:**
1. Receive content (paste or upload)
2. Convert to HTML if needed (LibreOffice for RTF/DOCX, pdftohtml for PDF)
3. Call `preprocess_for_export()` to remove platform chrome
4. Call `inject_char_spans()` to wrap each text character
5. Store in `WorkspaceDocument.content`

**Storage → PDF Export:**
1. Read `content` (HTML with char spans)
2. Strip char span wrappers using selectolax: `span.unwrap()` for `span.char[data-char-index]`
3. Pass clean HTML to existing `convert_html_with_annotations()` from #76
4. Existing pipeline handles marker insertion, Pandoc conversion, LaTeX generation

### Key Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage model | Single source (`content` only) | Eliminates sync issues between content and raw_content |
| Char span injection | selectolax DOM walk | Already a dependency, fast, preserves structure |
| Char span stripping | selectolax `span.unwrap()` | Safer than regex for HTML manipulation |
| RTF/DOCX conversion | LibreOffice (not Pandoc) | Pandoc RTF support is limited |
| Clipboard HTML access | NiceGUI js_handler on paste event | NiceGUI clipboard API only reads text/plain |
| Whitespace handling | Preserve as entities | Prevents HTML collapse of significant whitespace |
| `<br>` tags | Treat as newline character (gets index) | Consistent with text semantics |

## Implementation Components

### 1. New Module: `src/promptgrimoire/import/html_input.py`

```python
async def convert_to_html(
    content: str | bytes,
    source_type: Literal["html", "rtf", "docx", "pdf", "text"],
) -> str:
    """Convert any supported format to HTML via pandoc/libreoffice."""

def inject_char_spans(html: str) -> tuple[str, int]:
    """Walk HTML DOM, wrap each text character in data-char-index span.

    Returns:
        (html_with_spans, total_char_count)
    """

async def process_input(
    content: str | bytes,
    source_type: str,
) -> str:
    """Full pipeline: convert → preprocess → inject spans."""
```

### 2. Char Span Injection

Walk preprocessed HTML DOM with selectolax. For each text node:
- Wrap each character in `<span class="char" data-char-index="N">`
- Increment index counter
- Preserve surrounding HTML structure (headings, lists, tables)
- Whitespace characters get spans (stored as entities like `&nbsp;`)
- `<br>` tags become newline chars with indices

### 3. Char Span Stripping (for PDF export)

```python
def _strip_char_spans(html_with_spans: str) -> str:
    """Remove char span wrappers, preserving content."""
    from selectolax.lexbor import LexborHTMLParser

    tree = LexborHTMLParser(html_with_spans)
    for span in tree.css('span.char[data-char-index]'):
        span.unwrap()  # Removes tag, keeps text content
    return tree.html
```

### 4. UI Changes (annotation.py)

**Paste handling with js_handler:**
```python
content_input.on('paste',
    js_handler='''(event) => {
        const html = event.clipboardData.getData('text/html');
        const text = event.clipboardData.getData('text/plain');
        emit('paste', { html: html, text: text });
        event.preventDefault();
    }''',
    handler=handle_paste
)
```

**File upload:**
```python
ui.upload(on_upload=handle_upload).props('accept=".html,.htm,.rtf,.docx,.pdf,.txt"')
```

### 5. Storage Model Changes

```python
class WorkspaceDocument(SQLModel, table=True):
    content: str      # HTML with char spans (THE source of truth)
    raw_content: str  # DEPRECATED - store empty string
```

## Spikes Needed

1. **js_handler paste event**: Test browser compatibility for clipboard HTML access, edge cases with different browsers/platforms
2. **LibreOffice conversion**: Test RTF and DOCX conversion quality, identify edge cases
3. **selectolax text node iteration**: Verify `include_text=True` behavior, test with complex nested HTML

## Implementation Phases (Draft)

### Phase 1: Core Input Pipeline
- Create `html_input.py` module
- Implement `inject_char_spans()` with selectolax
- Implement `_strip_char_spans()` for export
- Unit tests for injection/stripping roundtrip

### Phase 2: UI Integration
- Add paste event handler with js_handler
- Add file upload component
- Integrate `process_input()` into document creation flow
- Update `handle_add_document()` to use new pipeline

### Phase 3: Export Adaptation
- Modify `pdf_export.py` to strip char spans from content
- Remove `raw_content` usage from export path
- Verify existing #76 tests still pass

### Phase 4: Format Conversion
- Add LibreOffice conversion for RTF/DOCX
- Add pdftohtml or LibreOffice for PDF
- Integration tests for each format

### Phase 5: E2E Tests
- Reimplement skipped annotation E2E tests with HTML input
- Test paste flow with various chatbot exports
- Test file upload flow

## Related Issues

- **#76**: CSS Fidelity - LaTeX pipeline (OUTPUT side, already implemented)
- **#101**: CJK/BLNS support (character tokenization, already implemented)
- **#104**: Extract WordSpanProcessor (superseded by this design)
- **#109**: File upload support (incorporated into this design)
- **#116**: Platform handler refactor (preprocessing used by this design)

## Open Questions

1. Should we store `source_type` on WorkspaceDocument for debugging/reprocessing?
2. How to handle conversion failures gracefully (show error, fall back to text)?
3. Should plain text input go through HTML pipeline or keep separate path?
