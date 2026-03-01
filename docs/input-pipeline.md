# HTML Input Pipeline

*Last updated: 2026-03-01*

The input pipeline (`src/promptgrimoire/input_pipeline/`) processes pasted or uploaded content for character-level annotation. It is the primary entry path for the annotation page.

## Pipeline Steps

1. **Content type detection** -- `detect_content_type()` uses magic bytes (PDF, DOCX, RTF) and structural heuristics (HTML tags) to classify input
2. **User confirmation** -- `show_content_type_dialog()` lets user override detected type
3. **Conversion to HTML** -- Plain text is wrapped in `<p>` tags; HTML passes through; RTF/DOCX/PDF conversion is Phase 7 (not yet implemented)
4. **Platform preprocessing** -- `preprocess_for_export()` strips chatbot chrome and injects speaker labels (with double-injection guard)
5. **Attribute stripping** -- Removes heavy inline styles, `data-*` attributes (except `data-speaker`), and class attributes to reduce size
6. **Empty element removal** -- Strips empty `<p>`/`<div>` elements (common in Office-pasted HTML)
7. **Text extraction** -- `extract_text_from_html()` builds a character list from clean HTML for highlight coordinate mapping. Highlight rendering and text selection use the CSS Custom Highlight API and JS text walker on the client side.

## Key Design Decision: CSS Custom Highlight API

The pipeline returns clean HTML from the server. Highlight rendering uses the CSS Custom Highlight API (`CSS.highlights`) with `StaticRange` objects built from a JS text walker's node map. Text selection detection converts browser `Selection` ranges to character offsets via the same text walker. The server extracts `document_chars` from the clean HTML using `extract_text_from_html()` for highlight coordinate mapping.

## Paragraph Numbering

After processing, the pipeline can build a paragraph map and inject `data-para` attributes into the clean HTML. Two modes:

- **Auto-number** (default): sequential numbering of block elements (`<p>`, `<blockquote>`, leaf `<div>`). Headers (`h1`-`h6`) and list items are excluded. Double `<br><br>` within a block creates a new paragraph.
- **Source-number**: reads `<li value="N">` attributes from the HTML (e.g. AustLII judgments).

`detect_source_numbering()` inspects HTML to recommend which mode to use (threshold: 2+ `<li value>` elements). The upload dialog and paste handler use this to auto-detect or let the user override.

The paragraph map (`dict[str, int]`) maps char-offset (string key, for JSON storage) to paragraph number. It is stored on `WorkspaceDocument.paragraph_map` and used at render time to inject `data-para` attributes. CSS `::before` pseudo-elements display the numbers in the left margin.

`lookup_para_ref()` converts highlight char ranges to human-readable `[N]` or `[N]-[M]` references for annotation cards and PDF export margin notes.

## Public API (`input_pipeline/__init__.py`)

- `detect_content_type(content: str | bytes) -> ContentType` -- Classify input content
- `process_input(content, source_type, platform_hint) -> str` -- Full pipeline (async)
- `extract_text_from_html(html: str) -> list[str]` -- Extract text chars from clean HTML
- `build_paragraph_map(html, auto_number) -> dict[int, int]` -- Build char-offset to paragraph-number map
- `detect_source_numbering(html) -> bool` -- True if HTML has 2+ `<li value>` elements
- `inject_paragraph_attributes(html, para_map) -> str` -- Add `data-para` attributes to block elements
- `lookup_para_ref(para_map, start_char, end_char) -> str` -- Compute `[N]` or `[N]-[M]` reference string
- `ContentType` -- Literal type: `"html" | "rtf" | "docx" | "pdf" | "text"`
- `CONTENT_TYPES` -- Tuple of all supported type strings
