# CSS Custom Highlight API Migration Design

## Summary

PromptGrimoire's annotation page currently wraps every text character in a `<span class="char" data-char-index="N">` element to enable collaborative highlighting — this multiplies HTML size by ~55x and creates brittle DOM coupling. This design replaces char-span rendering with the CSS Custom Highlight API, which paints highlights directly on text ranges without DOM modification. Text selection detection moves from querying `data-char-index` attributes to a JavaScript text walker that converts `Range` objects to character offsets, matching the existing Python `extract_text_from_html()` logic. Remote presence (cursors and selections) migrates from an in-memory `_connected_clients` dict to the pycrdt Awareness protocol, which provides automatic disconnect cleanup and network-level sync.

The migration removes ~800 lines from `annotation.py` (embedded JS modules move to `static/annotation-highlight.js`, presence state moves to pycrdt), deletes three obsolete functions from `input_pipeline` (`inject_char_spans`, `strip_char_spans`, `extract_chars_from_spans`), and gates unsupported browsers at login (requires Chrome 105+, Firefox 140+, Safari 17.2+). PDF export continues unchanged — char offsets remain the data model, only the rendering layer shifts. JS/Python text walker parity is unit-tested across all fixtures to prevent offset drift.

## Definition of Done

- The annotation page renders highlights via CSS Custom Highlight API — no char-span injection, no DOM modification for highlighting
- Text selection detection uses a JS text walker + Range-to-char-offset conversion (no `[data-char-index]` queries)
- Remote cursors and selections are synced via pycrdt Awareness protocol — the in-memory `_connected_clients` dict and NiceGUI callback mechanism are deleted
- Unsupported browsers are blocked at login with a "please upgrade" message (feature detection for `CSS.highlights`)
- `inject_char_spans()`, `strip_char_spans()`, and `extract_chars_from_spans()` are removed from the public API
- PDF export continues to work unchanged (same char offsets feed `export_annotation_pdf()`)
- JS text walker and Python `extract_text_from_html()` maintain parity (unit tested)
- Scroll-sync annotation card positioning works without char-span DOM queries

## Acceptance Criteria

### css-highlight-api.AC1: Highlights render via CSS Custom Highlight API
- **css-highlight-api.AC1.1 Success:** Annotation highlights paint with coloured background and underline on the correct text ranges without any `<span class="char">` elements in the DOM
- **css-highlight-api.AC1.2 Success:** Multiple annotation tags (e.g. jurisdiction, legal_issues) render simultaneously with distinct colours via separate `CSS.highlights` entries
- **css-highlight-api.AC1.3 Success:** Highlights spanning across block element boundaries (p, h2, li, blockquote, table cells) render as a single continuous highlight without splitting
- **css-highlight-api.AC1.4 Failure:** Creating a highlight with invalid char offsets (start >= end, negative, beyond document length) logs a warning and is silently skipped — no crash
- **css-highlight-api.AC1.5 Edge:** Overlapping highlights from different tags render with correct priority (both visible through layered opacity)

### css-highlight-api.AC2: Text selection uses JS text walker
- **css-highlight-api.AC2.1 Success:** Selecting text with the mouse produces correct `{start_char, end_char}` offsets matching the server's `document_chars` array
- **css-highlight-api.AC2.2 Success:** Selection across block element boundaries (paragraph into list item, heading into body text) produces correct contiguous char offsets
- **css-highlight-api.AC2.3 Failure:** Selection outside the document container (e.g. in sidebar or toolbar) is ignored — no event emitted
- **css-highlight-api.AC2.4 Edge:** Collapsed selection (click without drag) does not emit a selection event

### css-highlight-api.AC3: Remote presence via pycrdt Awareness
- **css-highlight-api.AC3.1 Success:** A second user's cursor appears as a coloured vertical line with name label at the correct character position
- **css-highlight-api.AC3.2 Success:** A second user's text selection appears as a coloured background highlight (via `CSS.highlights`) distinct from annotation highlights
- **css-highlight-api.AC3.3 Success:** When a remote user disconnects, their cursor and selection are removed within 30 seconds (Awareness timeout)
- **css-highlight-api.AC3.4 Success:** The local user's own cursor/selection is not rendered as a remote indicator
- **css-highlight-api.AC3.5 Failure:** `_connected_clients` dict, `_ClientState` class, `_build_remote_cursor_css()`, and `_build_remote_selection_css()` no longer exist in `pages/annotation.py`

### css-highlight-api.AC4: Browser feature gate
- **css-highlight-api.AC4.1 Success:** Browser with `CSS.highlights` support proceeds to the annotation page normally
- **css-highlight-api.AC4.2 Failure:** Browser without `CSS.highlights` support sees an "upgrade your browser" message and cannot access the annotation page

### css-highlight-api.AC5: Char-span functions removed from public API
- **css-highlight-api.AC5.1 Success:** `inject_char_spans`, `strip_char_spans`, and `extract_chars_from_spans` are not in `input_pipeline.__all__`
- **css-highlight-api.AC5.2 Success:** `from promptgrimoire.input_pipeline import inject_char_spans` raises `ImportError`
- **css-highlight-api.AC5.3 Success:** `extract_text_from_html()` remains available and functional

### css-highlight-api.AC6: PDF export unchanged
- **css-highlight-api.AC6.1 Success:** Highlights created via CSS Custom Highlight API with char offsets produce identical PDF output when fed to `export_annotation_pdf()` as highlights created via the old char-span system
- **css-highlight-api.AC6.2 Success:** Existing PDF export tests pass without modification (char offset data shape is unchanged)

### css-highlight-api.AC7: JS/Python text walker parity
- **css-highlight-api.AC7.1 Success:** For every `tests/fixtures/workspace_*.html` fixture, JS `walkTextNodes()` total char count equals Python `extract_text_from_html()` char count
- **css-highlight-api.AC7.2 Edge:** Fixtures containing `<br>` elements, nested tables, empty `<p>` tags, and `&nbsp;` entities produce matching counts
- **css-highlight-api.AC7.3 Edge:** Fixture with zero text content (empty HTML) produces 0 chars from both JS and Python

### css-highlight-api.AC8: Scroll-sync and card interaction without char-span DOM queries
- **css-highlight-api.AC8.1 Success:** Annotation cards in the sidebar track the vertical position of their corresponding highlight text on scroll
- **css-highlight-api.AC8.2 Success:** Hovering an annotation card paints a temporary highlight on the corresponding text via `CSS.highlights`
- **css-highlight-api.AC8.3 Success:** Clicking an annotation card's target button scrolls the document to the highlight position and pulses/throbs the highlight (visual feedback confirming which text is targeted)
- **css-highlight-api.AC8.4 Success:** No `querySelector('[data-char-index]')` calls exist in the annotation page JS
- **css-highlight-api.AC8.5 Success:** The throb animation uses only CSS properties available in `::highlight()` (background-color opacity transition) or a brief temporary CSS class on the container

## Glossary

- **CSS Custom Highlight API**: A web standard (`CSS.highlights`) that paints styled regions on arbitrary text ranges without modifying the DOM. Highlights are rendered via `::highlight()` pseudo-elements with `background-color` and `text-decoration` support.
- **Char offset / character offset**: A zero-indexed integer representing a position in the flattened text content of an HTML document. Used throughout PromptGrimoire as the coordinate system for highlights, cursors, and selections.
- **Text walker**: An algorithm that traverses DOM text nodes in document order, assigning character offsets to each node's text range. Implemented in both JavaScript (for browser selection) and Python (for server-side text extraction).
- **pycrdt Awareness**: A pycrdt feature for syncing transient presence data (cursor, selection, user name/colour) across connected clients. Automatically cleans up disconnected clients after 30 seconds.
- **Char-span injection**: The old approach of wrapping each text character in `<span class="char" data-char-index="N">`. Removed by this design.
- **`::highlight()` pseudo-element**: CSS syntax for styling text ranges registered in `CSS.highlights`. Only supports `background-color`, `color`, `text-decoration`, and `text-shadow` properties.
- **NiceGUI**: Python web UI framework used by PromptGrimoire. Page components render on the server and communicate with the browser via websockets.
- **Scroll-sync**: The feature where annotation cards in the sidebar track the vertical scroll position of their corresponding highlighted text in the document.
- **StaticRange**: A browser DOM API representing a fixed start and end point in the document tree. Used by the CSS Custom Highlight API to define highlight regions (unlike `Range`, does not update when the DOM changes).

## Architecture

Three rendering layers share a single character-offset data model.

**Layer 1 — Text Walker (shared foundation).** A JS module (`static/annotation-highlight.js`) walks DOM text nodes to build a `{node, startChar, endChar}[]` map. This is the sole bridge between DOM positions and flat character offsets. Python `extract_text_from_html()` in `input_pipeline/html_input.py` produces identical offsets server-side — parity is unit-tested across all fixtures.

**Layer 2 — CSS Custom Highlight API.** Annotation highlights and remote selections are rendered as named `Highlight` objects registered in `CSS.highlights`. Each annotation tag gets an entry (e.g. `hl-jurisdiction`), each remote user's selection gets one (e.g. `hl-sel-{clientId}`). Styled via `::highlight()` pseudo-elements with `background-color` and `text-decoration`. No DOM modification.

**Layer 3 — DOM cursor elements.** Remote cursors cannot use CSS Highlight API (`::highlight()` does not support `border`, `box-shadow`, or positioning). One absolutely-positioned `<div class="remote-cursor">` per connected user, positioned via `charOffsetToRange(textNodes, charIdx, charIdx+1).getBoundingClientRect()`. Contains a name label child. This follows the established pattern from Yjs/y-prosemirror.

**Data flow:** pycrdt Awareness broadcasts cursor/selection state → JS awareness listener receives updates → cursors update DOM positions, selections update `CSS.highlights` entries → annotation cards use `charOffsetToRange().getBoundingClientRect()` for scroll-sync positioning.

**Decomposition effect on annotation.py (3,027 lines):** JS modules currently embedded as Python string constants (~600 lines of JS) move to `static/annotation-highlight.js`. `_ClientState`, `_connected_clients`, `_build_remote_cursor_css()`, `_build_remote_selection_css()` are deleted (~200 lines). Awareness integration stays in `crdt/annotation_doc.py` where the methods already exist. Net effect: annotation.py shrinks by ~800 lines with no new code added to it.

## Existing Patterns

Investigation found the following patterns this design follows:

**JS-in-Python string constants** (`annotation.py:121–500`). Current pattern embeds JS as multi-line Python strings injected via `ui.add_body_html()`. This design moves JS to a standalone file in `static/` loaded via `ui.add_head_html('<script src="...">')`, matching the pattern used by `static/milkdown/`. The inline-string pattern is abandoned for this feature.

**`extract_text_from_html()` text walking** (`input_pipeline/html_input.py:381`). Existing Python text walker with whitespace collapse, `<br>` counting, and skip-tag rules. The JS text walker mirrors this logic exactly — validated by the demo page parity test (31,621 chars match).

**pycrdt Awareness methods** (`crdt/annotation_doc.py:511–576`). `update_cursor()`, `update_selection()`, `clear_cursor_and_selection()` already exist but are never called. Schema: `{client_id, name, color, cursor: int|None, selection: {start_char, end_char}|None}`. This design wires them up — no schema change needed.

**`::highlight()` pseudo-element styling** (CSS Custom Highlight API). New pattern for this codebase. Proven viable in demo page (`pages/highlight_api_demo.py`). Browser support: Chrome 105+, Firefox 140+, Safari 17.2+ (~92.5% global coverage).

**Divergence:** The in-memory `_connected_clients` dict (`annotation.py:115`) and `_ClientState` class (`annotation.py:75`) are deleted. Presence state moves entirely to pycrdt Awareness, which provides automatic disconnect cleanup (30s timeout) and network-level sync that the in-memory approach lacked.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Browser Feature Gate

**Goal:** Block unsupported browsers at login before any annotation code runs.

**Components:**
- Login page (`pages/auth.py`) — add `CSS.highlights` feature detection JS
- New "upgrade browser" route or inline message — displayed when detection fails

**Dependencies:** None (first phase).

**Done when:** A browser without `CSS.highlights` support sees an upgrade message and cannot proceed to annotation. Supported browsers pass through unchanged.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: JS Text Walker Module

**Goal:** Extract the validated JS text walker from the demo into a standalone static module.

**Components:**
- `static/annotation-highlight.js` — `walkTextNodes()`, `charOffsetToRange()`, `findLocalOffset()`, `countCollapsed()`, `rangePointToCharOffset()`
- Parity tests — parameterised across all `tests/fixtures/workspace_*.html` fixtures, comparing JS char count (via Playwright) against Python `extract_text_from_html()` char count

**Dependencies:** Phase 1 (browser gate ensures API exists).

**Done when:** `static/annotation-highlight.js` loads without error. Parity tests pass for every workspace fixture. Covers `css-highlight-api.AC7.*`.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Highlight Rendering Swap

**Goal:** Replace char-span-based highlight painting with CSS Custom Highlight API. Replace char-span-based text selection detection with text-walker-based detection.

**Components:**
- `static/annotation-highlight.js` — add `applyHighlights(container, highlightData)`, `setupSelection(container, emitCallback)`, CSS highlight management
- `pages/annotation.py` — delete `_CHAR_SPANS_JS`, `_TAB_REINJECT_JS`, `_HIGHLIGHT_CSS_JS`; replace with `<script src="...annotation-highlight.js">` load; update `_render_document_with_highlights()` to send clean HTML (no char spans); update selection event handler to receive text-walker-produced char offsets
- `input_pipeline/__init__.py` — remove `inject_char_spans`, `strip_char_spans` from `__all__` and public exports
- `input_pipeline/html_input.py` — delete `inject_char_spans()` (L160), `strip_char_spans()` (L329), `extract_chars_from_spans()` (L347); keep `extract_text_from_html()` (L381)

**Dependencies:** Phase 2 (text walker module).

**Done when:** Annotation page renders highlights via CSS Custom Highlight API. Text selection produces correct char offsets. `inject_char_spans` import raises `ImportError`. Covers `css-highlight-api.AC1.*`, `css-highlight-api.AC2.*`, `css-highlight-api.AC5.*`.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Scroll-Sync and Card Interaction

**Goal:** Restore annotation card positioning and card-hover highlighting without char-span DOM queries.

**Components:**
- `static/annotation-highlight.js` — add `charOffsetToRect(textNodes, charIdx)` convenience wrapper returning `getBoundingClientRect()` result
- `pages/annotation.py` — rewrite scroll-sync JS (`_SCROLL_SYNC_JS` at L1410–1499) to use `charOffsetToRange().getBoundingClientRect()` instead of `querySelector('[data-char-index]')`; rewrite card hover JS to add/remove temporary `CSS.highlights` entry instead of toggling class on char spans; rewrite go-to-highlight JS to use Range-based scrolling

**Dependencies:** Phase 3 (highlights rendering via CSS Highlight API).

**Done when:** Annotation cards track their highlight positions on scroll. Card hover paints temporary highlight. Click-to-scroll navigates to highlight. No `[data-char-index]` queries remain in JS. Covers `css-highlight-api.AC8.*`.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Remote Presence via pycrdt Awareness

**Goal:** Replace in-memory client state with pycrdt Awareness for cursor and selection sync. Render remote cursors as DOM elements, remote selections as CSS highlights.

**Components:**
- `crdt/annotation_doc.py` — wire up `update_cursor()` (L511), `update_selection()` (L531), `clear_cursor_and_selection()` (L561) to be called from annotation page event handlers; add awareness change observer that broadcasts to connected NiceGUI clients
- `static/annotation-highlight.js` — add `renderRemoteCursor(container, clientId, charIdx, name, color)` (positions DOM `<div>`), `renderRemoteSelection(textNodes, clientId, startChar, endChar, name, color)` (registers `CSS.highlights` entry)
- `pages/annotation.py` — delete `_ClientState` class (L75), `_connected_clients` dict (L115), `_build_remote_cursor_css()` (L568), `_build_remote_selection_css()` (L598), `_update_cursor_css()` (L1520), `_update_selection_css()` (L1532); replace with awareness-driven rendering path

**Dependencies:** Phase 4 (scroll-sync works, confirming `charOffsetToRange` is reliable).

**Done when:** Remote cursors appear as positioned `<div>` elements with name labels. Remote selections appear as coloured CSS highlights. `_connected_clients` dict is deleted. Disconnected clients are cleaned up automatically (Awareness 30s timeout). Covers `css-highlight-api.AC3.*`.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Cleanup and Verification

**Goal:** Remove all remaining char-span references. Verify PDF export. Update documentation.

**Components:**
- `pages/annotation.py` — remove any remaining `[data-char-index]` CSS selectors (L121–300 `_PAGE_CSS`), dead JS string constants, char-span-related helper functions
- `pages/text_selection.py` — remove or update if it depends on char-span DOM
- PDF export verification — run existing export tests confirming `export_annotation_pdf()` still works with same char offset data
- `CLAUDE.md` — update "HTML Input Pipeline" section to reflect removal of char-span injection; update "Key Design Decision" paragraph

**Dependencies:** Phase 5 (all new rendering works).

**Done when:** No references to `data-char-index`, `inject_char_spans`, `strip_char_spans`, or `_connected_clients` exist in `src/`. PDF export tests pass. Documentation updated. Covers `css-highlight-api.AC6.*`.
<!-- END_PHASE_6 -->

## Additional Considerations

**DOM mutation invalidation.** If NiceGUI re-renders the document container (e.g. on websocket reconnect), the text node map becomes stale. A `MutationObserver` on `#doc-container` must rebuild the map and re-apply all highlights. This is handled in the `static/annotation-highlight.js` module.

**`::highlight()` property limitations.** Only `background-color`, `color`, `text-decoration`, and `text-shadow` are supported. Firefox <146 does not support `text-decoration` in `::highlight()`. Design uses `background-color` as primary indicator with `text-decoration` as progressive enhancement.

**Pre-existing export bug.** `compute_highlight_spans()` in `export/highlight_spans.py` fails at inline element boundaries (`<b>`, `</b>`) — highlight spans that cross bold boundaries produce malformed HTML. This is a pre-existing bug unrelated to this migration and is being fixed separately.
