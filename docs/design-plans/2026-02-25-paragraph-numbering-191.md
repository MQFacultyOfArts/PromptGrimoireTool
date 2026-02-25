# Paragraph Numbering Design

**GitHub Issue:** #191

## Summary

PromptGrimoire attaches paragraph numbers to annotated legal and educational documents so that annotation cards, margin labels, and PDF exports all cite the same reference point. A document can have numbers derived in two ways: *auto-numbering* assigns sequential integers to every block element in document order, while *source-numbering* reads existing paragraph numbers directly from `<li value="N">` HTML attributes — the convention used by AustLII and similar legal databases. The correct mode is detected automatically when a document is pasted in, and can be overridden by the user at any time.

The implementation centres on a mapping builder — a pure function that walks the document HTML using the same traversal logic as the existing text-extraction pipeline, producing a `dict[int, int]` that maps each block's character offset to its paragraph number. That mapping is stored on the document record and consumed by three display surfaces: a CSS `::before` counter injected into the rendered document's left margin, a `para_ref` string baked into each highlight at creation time and shown on its annotation card, and a PDF margin note populated during export. Because all three surfaces read from the same stored mapping, the paragraph reference on a card, in the document margin, and in the exported PDF are guaranteed to agree.

## Definition of Done

- Annotation cards display `para_ref` when the highlight has one
- AustLII documents with OL paragraphs show correct paragraph numbers on cards
- Documents without OL paragraphs get synthetic sequential paragraph numbers
- Paragraph numbers appear in the document left margin
- Paragraph numbers appear in PDF export margin notes
- Per-document toggle controls auto-number vs source-number mode
- Paste-in auto-detects source numbering from `<li value>` attributes
- Toggle is changeable post-creation from workspace header

## Acceptance Criteria

### paragraph-numbering-191.AC1: Auto-numbered documents get sequential paragraph numbers
- **paragraph-numbering-191.AC1.1 Success:** Plain prose document (`<p>` elements) gets sequential numbers starting at 1
- **paragraph-numbering-191.AC1.2 Success:** Document with mixed block elements (`<p>`, `<blockquote>`, `<li>`) numbers all of them sequentially
- **paragraph-numbering-191.AC1.3 Success:** `<br><br>+` sequences within a block create new paragraph numbers
- **paragraph-numbering-191.AC1.4 Edge:** Single `<br>` within a block does NOT create a new paragraph number
- **paragraph-numbering-191.AC1.5 Edge:** Headers (`<h1>`-`<h6>`) are skipped — not numbered
- **paragraph-numbering-191.AC1.6 Edge:** Empty/whitespace-only blocks are skipped — not numbered
- **paragraph-numbering-191.AC1.7 Edge:** Pasted markdown (converts to `<br>`-heavy HTML) produces sensible numbering

### paragraph-numbering-191.AC2: Source-numbered documents use `<li value>` attributes
- **paragraph-numbering-191.AC2.1 Success:** AustLII document with `<li value="1">` through `<li value="42">` shows those numbers
- **paragraph-numbering-191.AC2.2 Success:** Gaps in source numbering are preserved (e.g. values 1, 2, 5, 6)
- **paragraph-numbering-191.AC2.3 Edge:** Non-numbered block elements between numbered `<li>` items have no paragraph number

### paragraph-numbering-191.AC3: Auto-detection on paste-in
- **paragraph-numbering-191.AC3.1 Success:** Pasting HTML with 2+ `<li value>` elements sets `auto_number_paragraphs = False`
- **paragraph-numbering-191.AC3.2 Success:** Pasting HTML with 0-1 `<li value>` elements sets `auto_number_paragraphs = True`
- **paragraph-numbering-191.AC3.3 Success:** Upload dialog shows detected state with override checkbox

### paragraph-numbering-191.AC4: Paragraph numbers display in document left margin
- **paragraph-numbering-191.AC4.1 Success:** Auto-numbered document shows sequential numbers in left margin
- **paragraph-numbering-191.AC4.2 Success:** Source-numbered document shows source numbers in left margin
- **paragraph-numbering-191.AC4.3 Edge:** Margin numbers don't overlap with document content

### paragraph-numbering-191.AC5: Annotation cards display para_ref
- **paragraph-numbering-191.AC5.1 Success:** Highlight on paragraph 3 shows `[3]` on the annotation card
- **paragraph-numbering-191.AC5.2 Success:** Highlight spanning paragraphs 3-5 shows `[3]-[5]`
- **paragraph-numbering-191.AC5.3 Success:** User can edit `para_ref` on an existing annotation card
- **paragraph-numbering-191.AC5.4 Edge:** Highlight on unnumbered block (header, empty) shows no `para_ref`

### paragraph-numbering-191.AC6: PDF export includes paragraph references
- **paragraph-numbering-191.AC6.1 Success:** PDF margin notes show `[N]` for annotations on numbered paragraphs
- **paragraph-numbering-191.AC6.2 Success:** Both auto-numbered and source-numbered documents produce correct PDF output

### paragraph-numbering-191.AC7: Toggle is changeable post-creation
- **paragraph-numbering-191.AC7.1 Success:** Toggle visible in workspace header area
- **paragraph-numbering-191.AC7.2 Success:** Toggling rebuilds `paragraph_map` and updates margin numbers
- **paragraph-numbering-191.AC7.3 Success:** Toggling does NOT modify existing `para_ref` values on highlights

### paragraph-numbering-191.AC8: Char-offset alignment
- **paragraph-numbering-191.AC8.1 Success:** Mapping builder char offsets match `extract_text_from_html()` output positions exactly

## Glossary

- **AustLII**: Australasian Legal Information Institute — a free online database of Australian and New Zealand legal materials. Its HTML uses `<ol>` lists with explicit `<li value="N">` attributes to encode official paragraph numbers.
- **auto-number mode**: Paragraph numbering mode where sequential integers are assigned to block elements in document order, ignoring any numbering present in the source HTML.
- **source-number mode**: Paragraph numbering mode where paragraph numbers are read directly from `<li value="N">` attributes in the HTML, preserving whatever numbering the source document used.
- **`para_ref`**: A short string (e.g. `"[3]"` or `"[3]-[5]"`) stored on a highlight record that identifies the paragraph(s) the highlighted text falls within.
- **`paragraph_map`**: A JSON-serialised `dict[int, int]` stored on a `WorkspaceDocument` record, mapping the character offset of each numbered block's start to its paragraph number.
- **char offset**: A character position within the plain-text representation of a document, produced by `extract_text_from_html()`. Used to locate which paragraph a highlight falls within.
- **mapping builder** (`build_paragraph_map()`): A pure function that walks document HTML and produces the `paragraph_map`. Must use the same traversal logic as `extract_text_from_html()` to keep char offsets aligned.
- **`extract_text_from_html()`**: The canonical function in `input_pipeline/html_input.py` that converts document HTML to a plain-text character list with consistent char offsets. The mapping builder's traversal must match it exactly.
- **`walk_and_map()`**: An existing DOM walker in `html_input.py` that yields characters and `TextNodeInfo` objects with char indices. Foundation for the mapping builder.
- **`word_to_legal_para`**: A parameter already present in `highlight_spans.py` that accepts a `dict[int, int | None]` mapping char offsets to paragraph numbers for PDF export. The design populates this rather than passing `None`.
- **`WorkspaceDocument`**: The SQLModel database record representing a single document within an annotation workspace. Gains two new columns: `auto_number_paragraphs` and `paragraph_map`.
- **CRDT**: Conflict-free replicated data type — the real-time collaboration layer (via pycrdt) used to synchronise annotation state across users. User edits to `para_ref` are stored through this layer.
- **`data-para` attribute**: An HTML attribute injected onto block elements before rendering, carrying the paragraph number. A CSS `::before` pseudo-element reads this to display the number in the left margin.
- **`<br><br>+` heuristic**: The rule that two or more consecutive `<br>` elements are treated as a paragraph boundary (creating a new paragraph number), while a single `<br>` is a line break within the same paragraph.
- **`detect_source_numbering()`**: A utility function that inspects pasted HTML and returns `True` if it contains two or more `<li value>` elements, triggering source-number mode automatically.
- **JSON key type coercion**: PostgreSQL stores JSON object keys as strings, so a `dict[int, int]` stored and retrieved via SQLModel will have string keys on read. Consumers must apply `int(key)` conversion.

## Architecture

Two paragraph numbering modes controlled by a per-document boolean on `WorkspaceDocument`:

- **Auto-number (ON, default):** Sequential numbering on non-header block elements. Every `<p>`, `<li>`, `<blockquote>`, text-bearing `<div>`, and `<br><br>+`-delimited chunk gets a number.
- **Source-number (OFF):** Extract existing paragraph numbers from `<li value="N">` attributes in legal documents (AustLII pattern). Only numbered list items get entries.

A **mapping builder** (pure function) walks the document HTML using the same traversal logic as `extract_text_from_html()` in `src/promptgrimoire/input_pipeline/html_input.py:149` to guarantee char-offset alignment. It produces a `dict[int, int]` mapping char-offset-of-block-start to paragraph number.

The mapping is **stored on `WorkspaceDocument`** as a JSON column and built at document save time. It is rebuilt when the toggle changes. Three surfaces consume it:

1. **Document left margin** — server-side injection of `data-para` attributes onto block elements before rendering via `ui.html()` in `src/promptgrimoire/pages/annotation/document.py:242`. CSS `::before` pseudo-element displays the number.
2. **Annotation cards** — `para_ref` string (e.g. `"[3]"`) baked into highlights at creation time by looking up `start_char` in the stored mapping. Displayed in `src/promptgrimoire/pages/annotation/cards.py:351-354`. User-editable after creation.
3. **PDF export** — stored mapping passed as `word_to_legal_para` to `compute_highlight_spans()` in `src/promptgrimoire/export/highlight_spans.py:462`, replacing the current `None`.

**Auto-detection on paste-in:** When HTML is captured in `src/promptgrimoire/pages/annotation/content_form.py:553-599`, count `<li>` elements with explicit `value` attributes. If 2+ found, set `auto_number_paragraphs = False`. Otherwise `True`.

## Existing Patterns

Investigation found the existing char-offset system is well-established:

- `extract_text_from_html()` in `src/promptgrimoire/input_pipeline/html_input.py:149-225` defines the canonical character walk. The mapping builder must use identical traversal logic.
- `walk_and_map()` in `src/promptgrimoire/input_pipeline/html_input.py:254-319` already provides a DOM walk that returns both characters and `TextNodeInfo` objects with char indices. This is the foundation for the mapping builder.
- The `word_to_legal_para` parameter in `src/promptgrimoire/export/highlight_spans.py:247` already defines the expected mapping shape (`dict[int, int | None]`). The design follows this contract exactly.
- `para_ref` display on cards in `src/promptgrimoire/pages/annotation/cards.py:308,351-354` already conditionally renders paragraph references. No structural change needed — just populate the field.
- Per-document metadata follows the `WorkspaceDocument` column pattern (existing: `type`, `source_type`, `title`). Adding `auto_number_paragraphs` and `paragraph_map` is consistent.

No divergence from existing patterns.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Data Model and Migration

**Goal:** Add paragraph numbering columns to `WorkspaceDocument` and migrate existing data.

**Components:**
- `WorkspaceDocument` model in `src/promptgrimoire/db/models.py:362-387` — add `auto_number_paragraphs: bool` (NOT NULL, default `True`) and `paragraph_map: dict[int, int]` (JSON, NOT NULL, default `{}`)
- Alembic migration — adds both columns with defaults (`True` and `'{}'`). Existing rows get empty `paragraph_map`; backfill deferred to a one-time script run after Phase 2 (avoids calling application code from migrations).

**Dependencies:** None (first phase)

**Done when:** Migration applies cleanly, model round-trips correctly through SQLModel. Existing documents have `paragraph_map = {}` (backfilled after Phase 2).
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Mapping Builder

**Goal:** Pure function that walks document HTML and produces a char-offset-to-paragraph-number mapping.

**Components:**
- `build_paragraph_map()` in `src/promptgrimoire/input_pipeline/` — takes HTML string and `auto_number: bool`, returns `dict[int, int]`
- Auto-number mode: walks HTML using same traversal as `extract_text_from_html()` (in `html_input.py:149-225`). Numbers `<p>`, `<li>`, `<blockquote>`, text-bearing `<div>`. Skips `<h1>`-`<h6>`. Treats `<br><br>+` sequences as paragraph breaks.
- Source-number mode: walks HTML looking for `<li>` elements with `value` attributes, extracts integer, maps char-offset to that number.
- `detect_source_numbering()` — takes HTML, returns `True` if 2+ `<li value>` elements found.

**Dependencies:** Phase 1 (model exists to store the mapping)

**Done when:** Builder produces correct mappings for auto-numbered prose, AustLII-style legal documents, and `<br><br>`-delimited content (pasted markdown). Char offsets align exactly with `extract_text_from_html()` output.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Document Save Integration

**Goal:** Build and store the paragraph map when documents are created or the toggle changes.

**Components:**
- Paste-in path in `src/promptgrimoire/pages/annotation/content_form.py:553-599` — after `process_input()`, run `detect_source_numbering()` to set `auto_number_paragraphs`, then `build_paragraph_map()` to populate `paragraph_map`. Pass both to `add_document()`.
- File upload path in `src/promptgrimoire/pages/annotation/content_form.py:604-647` — same integration, with auto-detect informing the upload dialog default.
- `add_document()` in `src/promptgrimoire/db/workspace_documents.py:20-62` — accept and store the two new fields.
- Workspace cloning path (if it exists by then) — copy `auto_number_paragraphs` and `paragraph_map` from source document.

**Dependencies:** Phase 2 (mapping builder exists)

**Done when:** New documents created via paste-in or upload have populated `paragraph_map`. Auto-detect correctly identifies AustLII documents. Cloned documents preserve paragraph settings.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Document Left Margin Display

**Goal:** Paragraph numbers visible in the left margin of the rendered document.

**Components:**
- HTML injection function in `src/promptgrimoire/input_pipeline/` or `src/promptgrimoire/pages/annotation/document.py` — takes document HTML and `paragraph_map`, injects `data-para="N"` attributes onto the corresponding block elements.
- CSS in `src/promptgrimoire/static/` — `::before` pseudo-element on `[data-para]` elements, positioned in the left margin. Small, grey, monospace.
- Rendering integration in `src/promptgrimoire/pages/annotation/document.py:242` — inject paragraph attributes into HTML before passing to `ui.html()`.

**Dependencies:** Phase 3 (documents have stored paragraph maps)

**Done when:** Opening an annotation workspace shows paragraph numbers in the left margin. Auto-numbered documents show sequential numbers. AustLII documents show source paragraph numbers.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Highlight para_ref Population

**Goal:** Annotation cards display paragraph references.

**Components:**
- Highlight creation in `src/promptgrimoire/pages/annotation/highlights.py:220-238` — look up `start_char` in the document's `paragraph_map` to compute `para_ref` string. Pass to `add_highlight()`.
- Lookup logic: find the largest key in `paragraph_map` that is `<= start_char`. If highlight spans multiple paragraphs (different para for `end_char`), format as `"[3]-[5]"`.
- Card display in `src/promptgrimoire/pages/annotation/cards.py:351-354` — already works, just needs non-empty `para_ref`.
- User-editable `para_ref` — small edit affordance on the card's `para_ref` label (NiceGUI binding, click-to-edit or inline input). Update stored in CRDT.

**Dependencies:** Phase 4 (margin display validates the mapping is correct), Phase 3 (documents have maps)

**Done when:** Creating a highlight on a numbered paragraph populates `para_ref` on the annotation card. Multi-paragraph highlights show range. Users can edit the `para_ref` value.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: PDF Export Integration

**Goal:** Paragraph numbers appear in PDF export margin notes.

**Components:**
- Export call site in `src/promptgrimoire/pages/annotation/pdf_export.py:154-162` — pass document's `paragraph_map` as `word_to_legal_para` instead of `None`.
- `_build_span_tag()` in `src/promptgrimoire/export/highlight_spans.py:274-280` — already consumes the mapping. No change needed unless `paragraph_map` key types differ (JSON deserialises keys as strings; may need `int()` conversion).

**Dependencies:** Phase 5 (highlights have para_ref), Phase 3 (documents have maps)

**Done when:** PDF export shows paragraph references in annotation margin notes. Both auto-numbered and source-numbered documents produce correct output.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Toggle UI

**Goal:** Users can view and change the auto-number setting after document creation.

**Components:**
- Workspace header control in `src/promptgrimoire/pages/annotation/header.py:70-183` — add a small toggle or chip in the header row (alongside existing placement chip, copy protection lock, sharing controls). NiceGUI `ui.switch` or `ui.chip` bound to `auto_number_paragraphs`.
- Upload dialog enhancement in `src/promptgrimoire/pages/annotation/content_form.py` — add checkbox to file upload confirmation dialog, pre-set by auto-detect result. Show hint when source numbering detected.
- Toggle change handler — rebuilds `paragraph_map` via `build_paragraph_map()`, updates the database, re-renders margin numbers. Does NOT modify existing `para_ref` values on highlights.

**Dependencies:** Phase 6 (all display surfaces working), Phase 4 (margin display to re-render)

**Done when:** Toggle visible in workspace header. Changing it rebuilds paragraph map and updates margin numbers. Upload dialog shows auto-detect result with override. Existing highlight `para_ref` values preserved on toggle change.
<!-- END_PHASE_7 -->

## Additional Considerations

**Char-offset alignment is the critical correctness constraint.** The mapping builder MUST use the same HTML traversal as `extract_text_from_html()`. If these diverge, paragraph numbers will be wrong for all highlights. Tests should verify alignment by building a map and then checking that `extract_text_from_html()[offset]` falls within the expected block element.

**`<br><br>+` heuristic:** Two or more consecutive `<br>` elements are treated as a paragraph break. A single `<br>` is a line break within a paragraph. This handles pasted markdown that converts to `<br>`-heavy HTML. Acceptance test: paste in markdown, verify sensible numbering.

**JSON key types:** PostgreSQL JSON stores dict keys as strings. The mapping builder returns `dict[int, int]`, but after database round-trip keys will be strings. Consumers must handle `int(key)` conversion, or the lookup function should accept both.

**Chat log documents:** Chat log parsers are responsible for setting `auto_number_paragraphs` appropriately when creating documents. The mapping builder doesn't need special chat log logic.

**Stale `para_ref` after toggle change:** When the numbering mode is toggled post-creation, margin numbers update but existing `para_ref` values on highlights do not. This is intentional (preserves user edits), but means margin and card numbers can diverge. Acceptable for MVP — users chose to toggle and can edit `para_ref` manually. A "refresh all para_ref" bulk action could be added as a follow-up if needed.

**Migration backfill ordering:** The Alembic migration (Phase 1) sets `paragraph_map = {}` for existing rows. A backfill script runs after Phase 2 delivers `build_paragraph_map()`. This avoids calling application code from migrations.
