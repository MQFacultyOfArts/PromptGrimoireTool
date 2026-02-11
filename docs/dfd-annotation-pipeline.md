# Data Flow Diagram: Annotation Pipeline (Status Quo)

> **Purpose:** Document the current data flows in the annotation-to-PDF pipeline
> to identify where the system depends on client-side JavaScript and DOM manipulation,
> in preparation for migrating to a NiceGUI backend-heavy rendering approach.
>
> **Methodology:** Yourdon-DeMarco DFD notation. Atemporal (shows data movement,
> not sequence). Functional decomposition from Level 0 context diagram through
> Level 2 detail on JS-dependent processes.
>
> **Notation (Mermaid conventions):**
> - `(( ))` circles = Processes (numbered hierarchically)
> - `[ ]` rectangles = External Entities
> - `[( )]` cylinders = Data Stores
> - Arrows = Data Flows (labelled with data package name)
>
> **Date:** 2026-02-11
>
> **Trigger:** NiceGUI 3.7.x [destroys client-side DOM modifications](https://github.com/zauberzeug/nicegui/issues/5749#issuecomment-3879588127).
> Maintainer confirms this is by design: "NiceGUI is frontend-light backend-heavy,
> maintaining frontend behaviour to facilitate client-side DOM modifications
> frankly isn't top priority."

---

## Level 0: Context Diagram

The entire system as a single process. Shows what crosses the system boundary.

```mermaid
flowchart LR
    User["User<br/>(student/instructor)"]
    Collab["Collaborator(s)<br/>(other session clients)"]

    User -->|"Raw content<br/>(HTML, text, file)"| P0
    User -->|"Text selections,<br/>tags, comments,<br/>draft text"| P0
    P0 -->|"Rendered annotatable<br/>document (live)"| User
    P0 -->|"Annotated PDF"| User

    Collab -->|"Highlight edits,<br/>cursor positions,<br/>selections"| P0
    P0 -->|"Live annotation<br/>updates, remote<br/>cursors"| Collab

    P0(("0<br/>Annotate,<br/>Comment,<br/>and Reflect"))
```

**System boundary includes:** NiceGUI server, browser client, PostgreSQL, Pandoc, LuaLaTeX.
Pandoc and LuaLaTeX are *internal* tools, not external entities — the user never interacts with them directly.

---

## Level 1: Major Functional Areas

Decomposes Process 0 into six sub-processes. Balanced against Level 0: all inputs/outputs of Process 0 are preserved.

```mermaid
flowchart TB
    %% External Entities
    User["User"]
    Collab["Collaborator(s)"]

    %% Data Stores
    D1[("D1: Document Store<br/>(WorkspaceDocument.content:<br/>clean HTML)")]
    D2[("D2: Annotation State<br/>(CRDT: highlights, comments,<br/>tag order, notes, draft)")]
    D3[("D3: Browser DOM<br/>(rendered HTML +<br/>char spans + CSS)")]

    %% Process 1: Ingest Content
    User -->|"Raw content<br/>(HTML, text, file)"| P1(("1<br/>Ingest<br/>Content"))
    P1 -->|"Clean HTML +<br/>source_type"| D1

    %% Process 2: Render & Annotate (Tab 1)
    D1 -->|"Clean HTML"| P2(("2<br/>Render &<br/>Annotate"))
    D2 -->|"Highlight list<br/>(char ranges + tags)"| P2
    P2 -->|"HTML + char spans<br/>+ highlight CSS"| D3
    D3 -->|"Rendered annotatable<br/>document"| User
    User -->|"Text selections<br/>(char indices),<br/>tags, comments"| P2
    P2 -->|"New/updated<br/>highlights"| D2

    %% Process 3: Organise & Comment (Tab 2)
    D2 -->|"Highlights grouped<br/>by tag"| P3(("3<br/>Organise &<br/>Comment"))
    P3 -->|"Reordered tags,<br/>comments"| D2
    User -->|"Tag reordering,<br/>comment text"| P3
    P3 -->|"Organised<br/>annotation view"| User

    %% Process 4: Reflect & Draft (Tab 3)
    D2 -->|"Highlight references,<br/>general notes,<br/>draft markdown"| P4(("4<br/>Reflect<br/>& Draft"))
    User -->|"Draft text<br/>(markdown)"| P4
    P4 -->|"Updated notes<br/>+ draft"| D2
    P4 -->|"Writing interface<br/>with references"| User

    %% Process 5: Synchronise State
    D2 -->|"CRDT update bytes"| P5(("5<br/>Synchronise<br/>State"))
    P5 -->|"Remote updates<br/>applied"| D2
    P5 -->|"CRDT state bytes<br/>(debounced)"| D1
    D1 -->|"Persisted CRDT<br/>state (on load)"| P5
    Collab -->|"Highlight edits,<br/>cursors, selections"| P5
    P5 -->|"Broadcast updates,<br/>remote cursors"| Collab
    P5 -->|"Remote highlight<br/>CSS + cursor CSS"| D3

    %% Process 6: Export to PDF
    User -->|"Export request"| P6(("6<br/>Export<br/>to PDF"))
    D1 -->|"Clean HTML"| P6
    D2 -->|"Highlights +<br/>notes + draft"| P6
    P6 -->|"Annotated PDF"| User
```

### Process Descriptions (Level 1)

| # | Process | Tab | Summary |
|---|---------|-----|---------|
| 1 | Ingest Content | — | Detect content type, clean HTML (strip chrome, attrs, empties), store |
| 2 | Render & Annotate | Annotate | Serve HTML, inject char spans (JS), apply highlight CSS, capture selections |
| 3 | Organise & Comment | Organise | Group highlights by tag, reorder, add comments, cross-reference |
| 4 | Reflect & Draft | Respond | Write response with highlight references, general notes |
| 5 | Synchronise State | — | CRDT broadcast, remote cursors/selections, debounced DB persistence |
| 6 | Export to PDF | — | Compute highlight regions, Pandoc HTML→LaTeX, Lua filter, LuaLaTeX compile |

### Data Store Descriptions

| Store | Technology | Contents | Persistence |
|-------|-----------|----------|-------------|
| D1: Document Store | PostgreSQL `WorkspaceDocument` | Clean HTML, source_type, title | Durable |
| D2: Annotation State | pycrdt `Doc` (in-memory) + PostgreSQL `Workspace.crdt_state` (serialised) | Highlights, comments, tag order, general notes, response draft | In-memory + debounced persist |
| D3: Browser DOM | Browser `#doc-container` | Rendered HTML with `<span class="char" data-char-index="N">` wrappers + CSS | Ephemeral (rebuilt on page load) |

---

## Level 2: Process 2 — Render & Annotate

This is the **JS-dependent core** that the NiceGUI 3.7.x breakage affects. Decomposed to show exactly where client-side JavaScript is load-bearing.

```mermaid
flowchart TB
    %% External
    User["User"]

    %% Parent-level stores (from Level 1)
    D1[("D1: Document Store")]
    D2[("D2: Annotation State")]
    D3[("D3: Browser DOM")]

    %% Sub-processes
    D1 -->|"Clean HTML"| P2_1(("2.1<br/>Extract<br/>Document<br/>Characters"))
    P2_1 -->|"document_chars:<br/>list[str]<br/>(index = position)"| D2_local[("D2a: Page State<br/>(server memory:<br/>document_chars)")]

    D1 -->|"Clean HTML<br/>(~20 KB)"| P2_2(("2.2<br/>Serve HTML<br/>to Browser"))
    P2_2 -->|"Clean HTML via<br/>WebSocket<br/>(ui.html)"| D3

    D3 -->|"Clean DOM<br/>(post-render)"| P2_3(("2.3<br/>Inject Char<br/>Spans"))
    P2_3 -->|"DOM with<br/>55x char spans<br/>(~1.1 MB)"| D3

    D2 -->|"Highlight list"| P2_4(("2.4<br/>Compute<br/>Highlight CSS"))
    P2_4 -->|"CSS rules targeting<br/>data-char-index<br/>selectors"| D3

    D3 -->|"User mouseup /<br/>selectionchange"| P2_5(("2.5<br/>Detect Text<br/>Selection"))
    P2_5 -->|"Selection event:<br/>{start, end}<br/>char indices"| P2_6

    User -->|"Tag choice<br/>(keyboard / menu)"| P2_6(("2.6<br/>Create<br/>Highlight"))
    D2_local -->|"document_chars<br/>[start:end]"| P2_6
    P2_6 -->|"New highlight:<br/>{id, start_char, end_char,<br/>tag, text, author}"| D2

    D2 -->|"Updated<br/>highlights"| P2_4
```

### Where JavaScript Lives (Process 2)

| Sub-process | Runs on | JS-dependent? | What JS does |
|-------------|---------|---------------|--------------|
| 2.1 Extract Chars | Server (Python) | No | — |
| 2.2 Serve HTML | Server (NiceGUI) | No | — |
| **2.3 Inject Char Spans** | **Browser (JS)** | **Yes** | Walks DOM, wraps each text character in `<span class="char" data-char-index="N">`. 55x HTML expansion. |
| **2.4 Compute Highlight CSS** | **Server → Browser** | **Partial** | Server computes CSS rules like `[data-char-index="42"] { background: #ff0 }`. Rules depend on char spans existing in DOM. |
| **2.5 Detect Text Selection** | **Browser (JS)** | **Yes** | Listens to `selectionchange`/`mouseup`, finds intersecting char spans, emits `{start, end}` indices to server. |
| 2.6 Create Highlight | Server (Python) | No | — |

**Processes 2.3, 2.4, and 2.5 form the JS-dependent triad.** The char-span injection (2.3) is the foundation: both highlight rendering (2.4) and selection detection (2.5) depend on `data-char-index` attributes being present in the DOM.

---

## Level 2: Process 5 — Synchronise State

Decomposed to show how CRDT state moves between clients and persistence.

```mermaid
flowchart TB
    Collab["Collaborator(s)"]
    D2[("D2: Annotation State<br/>(CRDT in-memory)")]
    D1[("D1: Document Store<br/>(PostgreSQL)")]
    D3[("D3: Browser DOM")]

    D2 -->|"doc.observe()<br/>update bytes"| P5_1(("5.1<br/>Broadcast<br/>CRDT Update"))
    P5_1 -->|"Update bytes"| Collab
    Collab -->|"Update bytes"| P5_2(("5.2<br/>Apply Remote<br/>Update"))
    P5_2 -->|"Merged state"| D2

    Collab -->|"Cursor position<br/>(char index)"| P5_3(("5.3<br/>Render Remote<br/>Cursors"))
    P5_3 -->|"Remote cursor CSS<br/>(box-shadow on<br/>data-char-index)"| D3

    Collab -->|"Selection range<br/>(start, end)"| P5_4(("5.4<br/>Render Remote<br/>Selections"))
    P5_4 -->|"Remote selection CSS<br/>(background on<br/>data-char-index)"| D3

    D2 -->|"Dirty flag"| P5_5(("5.5<br/>Debounced<br/>Persist"))
    P5_5 -->|"CRDT state bytes<br/>(5s debounce)"| D1
    D1 -->|"Stored CRDT bytes<br/>(on page load)"| P5_2
```

### JS Dependencies in Process 5

| Sub-process | JS-dependent? | Why |
|-------------|---------------|-----|
| 5.1 Broadcast | No | Server-side pycrdt observer |
| 5.2 Apply Remote | No | Server-side pycrdt merge |
| **5.3 Remote Cursors** | **Yes** | CSS targets `[data-char-index="N"]` — requires char spans in DOM |
| **5.4 Remote Selections** | **Yes** | CSS targets `[data-char-index="N"]` range — requires char spans in DOM |
| 5.5 Debounced Persist | No | Server-side async save |

---

## Level 2: Process 6 — Export to PDF

Decomposed to show the data transformation chain. This process is **server-side only** — no JS dependency — but it must maintain character index parity with the browser's char-span injection.

```mermaid
flowchart TB
    User["User"]
    D1[("D1: Document Store")]
    D2[("D2: Annotation State")]

    User -->|"Export request"| P6_1

    D1 -->|"Clean HTML"| P6_1(("6.1<br/>Preprocess<br/>HTML"))
    P6_1 -->|"Stripped HTML<br/>(no chrome,<br/>no heavy attrs)"| P6_2

    D2 -->|"Highlights:<br/>[{start_char, end_char,<br/>tag, text, comments}]"| P6_2(("6.2<br/>Insert<br/>Highlight<br/>Markers"))
    P6_2 -->|"HTML with<br/>HLSTART/HLEND/<br/>ANNMARKER text<br/>markers"| P6_2a

    P6_2a(("6.2a<br/>Compute<br/>Highlight<br/>Spans")) -->|"HTML with<br/>data-hl, data-colors,<br/>data-annots spans<br/>(pre-split at<br/>block boundaries)"| P6_3

    P6_3(("6.3<br/>Pandoc<br/>HTML → LaTeX"))
    P6_3 -->|"Raw LaTeX<br/>with \\highLight{}<br/>\\annot{} commands"| P6_4

    D2 -->|"Tag → colour map"| P6_5(("6.5<br/>Build LaTeX<br/>Preamble"))
    P6_5 -->|"Preamble:<br/>colour defs, macros,<br/>packages"| P6_6

    D2 -->|"General notes +<br/>response draft"| P6_4(("6.4<br/>Post-process<br/>LaTeX"))
    P6_4 -->|"Fixed LaTeX body<br/>(annots moved outside<br/>restricted contexts)"| P6_6

    P6_6(("6.6<br/>Assemble &<br/>Compile")) -->|"Complete .tex"| P6_6
    P6_6 -->|"Annotated PDF"| User
```

### Character Index Parity Requirement

Process 6.2 (Insert Highlight Markers) uses character indices from D2 (Annotation State). These indices were created by Process 2.5 (Detect Text Selection) in the browser, which counts characters based on the char-span DOM.

**The export pipeline reimplements the same character extraction algorithm server-side** (`extract_text_from_html()`) to find byte offsets in the HTML. Both implementations must agree on:

- Whitespace-only text nodes in block containers → skip
- Whitespace runs (including `\u00a0`) → collapse to single space
- `<br>` → newline (counts as 1 character)
- `<script>`, `<style>`, `<noscript>`, `<template>` → skip entirely

If the algorithms diverge, highlights appear at wrong positions in the PDF.

---

## JS Dependency Summary

All processes that depend on client-side JavaScript or the char-span DOM:

| Process | Dependency | What Breaks Without It |
|---------|-----------|----------------------|
| **2.3 Inject Char Spans** | JS DOM manipulation | No character-level addressing at all |
| **2.4 Compute Highlight CSS** | CSS `[data-char-index]` selectors | Highlights not visible |
| **2.5 Detect Text Selection** | JS `selectionchange` + char span lookup | Cannot determine which characters were selected |
| **5.3 Remote Cursors** | CSS `[data-char-index]` selectors | Remote cursors not visible |
| **5.4 Remote Selections** | CSS `[data-char-index]` selectors | Remote selections not visible |
| **6.2 Insert Highlight Markers** | Parity with JS char extraction | Highlights at wrong positions in PDF |

### The Core Problem

The char-span injection (Process 2.3) is the **single point of fragility**. It:

1. **Modifies the DOM client-side** — which NiceGUI 3.7.x actively destroys on server updates
2. **Expands HTML 55x** — must happen client-side to avoid WebSocket limits
3. **Creates the addressing scheme** that five other processes depend on
4. **Must be reimplemented server-side** for PDF export (character index parity)

The system has two parallel implementations of character indexing:
- **Browser JS** (`window._injectCharSpans()`) — for live annotation
- **Server Python** (`extract_text_from_html()`) — for PDF export

Both must produce identical indices. Any divergence is a bug (cf. Issues #129, #143).

---

## Balancing Verification

### Level 0 ↔ Level 1

| Level 0 Flow | Direction | Level 1 Mapping |
|-------------|-----------|-----------------|
| Raw content | User → P0 | User → P1 (Ingest) |
| Selections, tags, comments | User → P0 | User → P2 (Annotate), P3 (Organise), P4 (Reflect) |
| Rendered document | P0 → User | P2 → D3 → User |
| Annotated PDF | P0 → User | P6 → User |
| Highlight edits, cursors | Collab → P0 | Collab → P5 (Sync) |
| Live updates, cursors | P0 → Collab | P5 → Collab |

All Level 0 flows accounted for. No orphan flows introduced at Level 1.

### Level 1 ↔ Level 2 (Process 2)

| Level 1 Flow | Level 2 Mapping |
|-------------|-----------------|
| D1 → P2 (Clean HTML) | D1 → P2.1 (extract chars) + D1 → P2.2 (serve HTML) |
| D2 → P2 (Highlight list) | D2 → P2.4 (compute CSS) |
| P2 → D3 (HTML + spans + CSS) | P2.2 → D3 + P2.3 → D3 + P2.4 → D3 |
| User → P2 (Selections, tags) | D3 → P2.5 (selection events) + User → P2.6 (tag choice) |
| P2 → D2 (New highlights) | P2.6 → D2 |

Balanced.
