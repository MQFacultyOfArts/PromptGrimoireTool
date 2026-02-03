# Live Annotation Spike - Implementation Plan

**Goal:** Build `/demo/live-annotation` page to prove pycrdt-based live annotation with inline comment positioning and live cursor sharing.

## Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────┐
│                    NiceGUI Server                               │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │               AnnotationDocument (new)                      │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │ │
│  │  │ pycrdt Map   │  │ pycrdt Map   │  │ pycrdt Map      │  │ │
│  │  │ highlights   │  │ cursors      │  │ selections      │  │ │
│  │  │ {id: data}   │  │ {clientId:   │  │ {clientId:      │  │ │
│  │  │              │  │  position}   │  │  {start,end}}   │  │ │
│  │  └──────────────┘  └──────────────┘  └─────────────────┘  │ │
│  │       │                   │                  │             │ │
│  │       └───────────────────┼──────────────────┘             │ │
│  │                     doc.observe()                          │ │
│  │                           │                                │ │
│  │                    _broadcast()                            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│           ┌──────────────────┼──────────────────┐               │
│           ▼                  ▼                  ▼               │
│    ┌──────────┐       ┌──────────┐       ┌──────────┐          │
│    │ Client A │       │ Client B │       │ Client C │          │
│    │ Tab 1    │       │ Tab 2    │       │ Tab 3    │          │
│    └──────────┘       └──────────┘       └──────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## Files to Create/Modify

### 1. New: `src/promptgrimoire/crdt/annotation_doc.py`

Extends SharedDocument pattern for annotation-specific CRDT structure:

```python
class AnnotationDocument:
    """CRDT document for live annotation collaboration."""

    def __init__(self, doc_id: str):
        self.doc = Doc()
        self.doc["highlights"] = Map()      # {highlight_id: HighlightData}
        self.doc["cursors"] = Map()         # {client_id: CursorPosition}
        self.doc["selections"] = Map()      # {client_id: SelectionRange}
        self.doc["client_meta"] = Map()     # {client_id: {name, color}}
        # ...
```

### 2. New: `src/promptgrimoire/pages/live_annotation_demo.py`

Route: `/demo/live-annotation`

**Layout:** Single scroll area with:

- Document text (static HTML from fixture RTF)
- Inline annotation blocks positioned after each annotated paragraph
- Live cursor/selection overlays

### 3. Modify: `src/promptgrimoire/crdt/__init__.py`

Export new AnnotationDocument class

## Implementation Steps

### Step 1: AnnotationDocument CRDT Class

Create the pycrdt wrapper with:

- `Map` for highlights: `{id: {start_word, end_word, tag, text, author, created_at, comments: Array}}`
- `Map` for live cursors: `{client_id: {word_index, name, color}}`
- `Map` for live selections: `{client_id: {start_word, end_word, name, color}}`
- `Array` inside each highlight for comments: `[{id, author, text, created_at}, ...]`
- Observer callbacks for broadcasting changes
- Methods: `add_highlight()`, `remove_highlight()`, `update_cursor()`, `update_selection()`, `add_comment()`, `delete_comment()`

### Step 2: Demo Page Layout

Build the NiceGUI page with:

- **Single scroll container** with two columns (70% document, 30% annotations)
- **Document column**: Each word wrapped in `<span data-w="N">` for CSS-based highlighting
- **Annotation column**: Cards stacked vertically, ordered by source paragraph
- **Top-anchored alignment**: The annotation at the top of the viewport aligns with its source paragraph; others stack below naturally
- **Word spans created once** at page load, never re-rendered - highlights applied via `.classes()`

Layout behavior:
- Both columns scroll together (single scroll container)
- Annotation column position calculated so topmost annotation aligns with its paragraph
- As you scroll, the "anchor" annotation changes to whichever is at the top

### Step 3: Live Selection Broadcasting

Minimal JavaScript (event handling only, no DOM manipulation):

1. On `selectionchange` event → emit word indices to Python via NiceGUI `.on()` handler
2. Python updates `selections` Map in pycrdt with client_id and word range
3. Observer broadcasts to other clients
4. Other clients apply CSS class to word spans (e.g., `selection-user-abc` with semi-transparent background)

### Step 4: Live Cursor Sharing

Minimal JavaScript (event handling only):

1. Track which word span the mouse is over (via `mouseover` on container)
2. Throttled emit of word index to Python (every 100ms)
3. Other clients apply CSS class to that word span (e.g., `cursor-user-abc` with colored underline + ::after pseudo-element for name)

### Step 5: Inline Annotation Rendering

When highlights Map changes (pycrdt observer fires):

1. Apply CSS highlight class to word spans in range (e.g., `highlight-jurisdiction`)
2. Group highlights by paragraph (based on word indices)
3. For each paragraph with highlights, update annotation cards in the margin container
4. Cards are NiceGUI elements (ui.card, ui.label) - show tag color, quoted text, author, timestamp, thread

### Step 5b: Comment Threading (pycrdt)

Each highlight in the Map contains a `comments` Array:

1. Click annotation card → expand comment thread UI
2. Type comment → updates pycrdt Array inside the highlight's data
3. Observer broadcasts change → other clients see new comment live
4. Support typing indicators: when user is focused on comment input, broadcast to others

### Step 6: Floating Tag Menu

On text selection:

1. JS emits selected word range + bounding rect coordinates to Python
2. Python shows NiceGUI floating element (ui.menu or absolute-positioned ui.card) near selection
3. Tag buttons click → create highlight in pycrdt Map → CSS classes applied to word spans
4. Auto-syncs to all clients via pycrdt observer

### Step 7: Responsive Layout

Two layout modes:

1. **Two-column (desktop default)**: Document 70%, annotation margin 30%, top-anchored alignment
2. **Stacked/salami (mobile default)**: Single column, annotations as colored blocks below each paragraph, tap to expand

Mode switching:
- Mobile defaults to stacked mode (CSS media query)
- Desktop can auto-switch to stacked if annotation density gets too high (too many cards fighting for alignment)
- Manual toggle button available to switch modes

## Key Technical Decisions

1. **pycrdt Map for highlights** - Full conflict resolution for concurrent additions
2. **Word-level spans with CSS highlighting** - Each word wrapped in `<span data-w="N">`, highlights applied via CSS classes (no DOM clobbering)
3. **Client-side JS for events only** - Selection detection, cursor tracking emit to Python, but don't manipulate DOM structure
4. **Server updates CSS classes** - NiceGUI `.classes(add/remove)` on span elements, structure stays stable
5. **pycrdt stores word ranges** - `{start_word: 5, end_word: 12, tag: 'jurisdiction'}` instead of character offsets

## Test Data

Use existing fixture: `tests/fixtures/183.rtf` (Carlill v Carbolic Smoke Ball Co)

## Verification

1. Open `/demo/live-annotation` in two browser tabs
2. Select text in Tab A → floating menu appears
3. Tab B should show Tab A's selection as a colored overlay with name label
4. Click tag in Tab A → highlight commits
5. Tab B should immediately show the new highlight (inline annotation card appears)
6. Create highlight in Tab B → Tab A sees it
7. Verify no data loss when both tabs highlight simultaneously (CRDT merge)
8. Click annotation card in Tab A → expand comment thread
9. Type comment in Tab A → Tab B sees comment appear live
10. Tab B replies to same thread → Tab A sees reply immediately

## Out of Scope (for this spike)

- Persistence to PostgreSQL (CRDT is ephemeral for demo)
- Brief creation form / 11 tags WYSIWYG
- PDF export
