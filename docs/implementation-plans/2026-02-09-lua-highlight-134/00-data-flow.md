# PDF Export — Data Flow Diagrams

**Date:** 2026-02-09
**Source:** Traced from actual function bodies, not issue descriptions.

## Level 0: Context Diagram

```mermaid
flowchart LR
    User([User])
    Pandoc([Pandoc])
    LuaLaTeX([LuaLaTeX])

    User -- "html_content<br>highlights[]<br>tag_colours{}<br>general_notes" --> P0((PDF Export<br>System))
    P0 -- "PDF file" --> User
    P0 -- "marked HTML file" --> Pandoc
    Pandoc -- "marked LaTeX string" --> P0
    P0 -- ".tex file" --> LuaLaTeX
    LuaLaTeX -- ".pdf file" --> P0
```

**External entities:**

| Entity | Role |
|--------|------|
| User | Provides document content, highlights, colours, notes. Receives PDF. |
| Pandoc | Converts HTML to LaTeX. Treats markers as opaque text. |
| LuaLaTeX | Compiles .tex to .pdf. lua-ul interprets `\highLight` at node level. |

## Level 1: PDF Export System

```mermaid
flowchart TD
    %% External entities
    User([User])
    Pandoc([Pandoc])
    LuaLaTeX([LuaLaTeX])

    %% Data stores
    D1[(D1: Platform<br>Handler Registry)]
    D2[(D2: Filesystem<br>temp dir)]

    %% Processes
    P1((1<br>Preprocess<br>HTML))
    P2((2<br>Insert<br>Markers))
    P3((3<br>Convert<br>to LaTeX))
    P4((4<br>Replace Markers<br>with Highlights))
    P5((5<br>Assemble<br>Document))
    P6((6<br>Compile<br>to PDF))

    %% Data flows
    User -- "raw_html<br>platform_hint" --> P1
    D1 -- "platform_handlers" --> P1
    P1 -- "preprocessed_html<br>(chrome stripped,<br>speaker labels)" --> P2

    User -- "highlight_list<br>(start_char, end_char,<br>tag, author)" --> P2
    P2 -- "marked_html<br>(HTML + HLSTART/HLEND/<br>ANNMARKER text)" --> P3

    P3 -- "marked_html_file" --> Pandoc
    Pandoc -- "marked_latex<br>(LaTeX + marker text<br>preserved verbatim)" --> P3
    P3 -- "marked_latex<br>(post-processed)" --> P4

    User -- "highlight_metadata<br>(tag, author, comments,<br>para_ref)" --> P4
    P4 -- "highlighted_latex<br>(LaTeX body with<br>highLight + underLine<br>+ annot commands)" --> P5

    User -- "tag_colours{}<br>general_notes" --> P5
    P5 -- "complete_tex<br>(.tex document)" --> P6
    P5 -- ".tex file" --> D2

    D2 -- ".tex file" --> P6
    P6 -- ".tex file" --> LuaLaTeX
    LuaLaTeX -- ".pdf file" --> P6
    P6 -- "PDF file" --> User
```

**Data dictionary — Level 1 flows:**

| Flow | Content | Format |
|------|---------|--------|
| raw_html | Document content from CRDT doc.content | HTML string (no char spans) |
| highlight_list | User's annotation selections | list[dict] with start_char, end_char, tag |
| highlight_metadata | Per-highlight details for margin notes | tag, author, created_at, comments, para_ref |
| preprocessed_html | Platform chrome stripped, speaker labels injected | HTML string |
| marked_html | HTML with marker sentinels at highlight boundaries | HTML + literal text `HLSTART{n}ENDHL` etc. |
| marked_latex | LaTeX with marker sentinels surviving pandoc | LaTeX string with marker text |
| highlighted_latex | LaTeX body with `\highLight`, `\underLine`, `\annot` | LaTeX string |
| complete_tex | Full `.tex` document with preamble, body, notes | LaTeX document string |
| tag_colours | Mapping of tag names to hex colour codes | dict[str, str] |

---

## Level 2: Process 1 — Preprocess HTML

```mermaid
flowchart TD
    %% External
    Input(["preprocessed_html<br>(from raw_html)"])
    Output(["preprocessed_html"])
    D1[(D1: Platform<br>Handler Registry)]

    %% Processes
    P1_1((1.1<br>Parse HTML<br>to DOM))
    P1_2((1.2<br>Platform-specific<br>preprocessing))
    P1_3((1.3<br>Remove common<br>chrome))
    P1_4((1.4<br>Serialise<br>DOM to string))
    P1_5((1.5<br>Inject speaker<br>labels))

    %% Flows
    Input -- "raw_html" --> P1_1
    P1_1 -- "DOM tree<br>(LexborHTMLParser)" --> P1_2
    D1 -- "matched handler<br>(or none)" --> P1_2
    P1_2 -- "DOM tree<br>(platform chrome<br>removed)" --> P1_3
    P1_3 -- "DOM tree<br>(common chrome<br>removed)" --> P1_4
    P1_4 -- "html_string" --> P1_5
    P1_5 -- "preprocessed_html<br>(with data-speaker<br>attributes)" --> Output
```

**Data transforms:**

| Process | Input data | Transform | Output data |
|---------|-----------|-----------|-------------|
| 1.1 | raw_html (string) | selectolax parse | DOM tree (mutable) |
| 1.2 | DOM tree + handler | Handler removes platform-specific elements | DOM tree (modified) |
| 1.3 | DOM tree | Strips buttons, navs, footers | DOM tree (modified) |
| 1.4 | DOM tree | Serialise | html_string |
| 1.5 | html_string | Regex inject `data-speaker` divs | preprocessed_html |

---

## Level 2: Process 2 — Insert Markers

```mermaid
flowchart TD
    %% External
    InHTML(["preprocessed_html"])
    InHL(["highlight_list"])
    Output(["marked_html"])

    %% Processes
    P2_1((2.1<br>Strip scripts<br>and styles))
    P2_2((2.2<br>Fix mid-word<br>font splits))
    P2_3((2.3<br>Walk DOM<br>and map chars))
    P2_4((2.4<br>Compute marker<br>byte positions))
    P2_5((2.5<br>Splice markers<br>into HTML))
    P2_6((2.6<br>Strip control<br>chars))

    %% Flows
    InHTML -- "preprocessed_html" --> P2_1
    P2_1 -- "sanitised_html<br>(no script/style)" --> P2_2
    P2_2 -- "clean_html<br>(font splits fixed)" --> P2_3

    P2_3 -- "text_nodes[]<br>(tag, text, char_offset)" --> P2_4
    P2_3 -- "char_to_node_map" --> P2_4

    InHL -- "highlight_list<br>(sorted by start_char)" --> P2_4

    P2_4 -- "insertion_list[]<br>(byte_pos, marker_string)" --> P2_5
    P2_2 -- "clean_html" --> P2_5

    P2_5 -- "marked_html<br>(markers spliced in)" --> P2_6
    P2_6 -- "marked_html<br>(control chars stripped)" --> Output
```

**Data transforms:**

| Process | Input data | Transform | Output data |
|---------|-----------|-----------|-------------|
| 2.1 | preprocessed_html | lxml DOM: remove `<script>`, `<style>`, `<noscript>` | sanitised_html |
| 2.2 | sanitised_html | Regex: merge split font tags at word boundaries | clean_html |
| 2.3 | clean_html | DOM walk matching `extract_text_from_html` logic | text_nodes[], char_to_node_map |
| 2.4 | text_nodes + highlight_list | Map char positions to byte offsets in serialised HTML | insertion_list[(byte_pos, marker_text)] |
| 2.5 | clean_html + insertion_list | String splice back-to-front (preserves offsets) | marked_html |
| 2.6 | marked_html | Strip 0x01-0x1F non-whitespace control chars | marked_html (clean) |

**Marker format:** Literal text strings in the HTML text stream:

- `HLSTART{n}ENDHL` — before first char of highlight n
- `HLEND{n}ENDHL` — after last char of highlight n
- `ANNMARKER{n}ENDMARKER` — after HLEND (annotation placement point)

---

## Level 2: Process 3 — Convert to LaTeX

```mermaid
flowchart TD
    %% External
    InHTML(["marked_html"])
    Pandoc([Pandoc])
    Output(["marked_latex"])

    %% Data store
    D2[(D2: Filesystem<br>temp .html file)]

    %% Processes
    P3_1((3.1<br>Normalise<br>HTML lists))
    P3_2((3.2<br>Wrap styled<br>paragraphs))
    P3_3((3.3<br>Write temp<br>HTML file))
    P3_4((3.4<br>Run Pandoc))
    P3_5((3.5<br>Fix invalid<br>newlines))
    P3_6((3.6<br>Strip<br>texorpdfstring))

    %% Flows
    InHTML -- "marked_html" --> P3_1
    P3_1 -- "list_normalised_html<br>(ol start= attrs)" --> P3_2
    P3_2 -- "normalised_html<br>(styled p wrapped in div)" --> P3_3
    P3_3 -- "html_file_path" --> D2
    D2 -- "html_file_path" --> P3_4

    P3_4 -- "html_file_path<br>+ pandoc flags:<br>-f html+native_divs<br>-t latex<br>--no-highlight<br>[--lua-filter]" --> Pandoc
    Pandoc -- "latex_stdout<br>(markers survive<br>as literal text)" --> P3_4

    P3_4 -- "raw_pandoc_latex" --> P3_5
    P3_5 -- "newline_fixed_latex" --> P3_6
    P3_6 -- "marked_latex" --> Output
```

**Critical data invariant:** Markers (`HLSTART{n}ENDHL` etc.) are plain text characters. Pandoc treats them as document content and preserves them verbatim in the LaTeX output. They appear in the LaTeX text stream alongside the converted content.

**Data transforms:**

| Process | Input data | Transform | Output data |
|---------|-----------|-----------|-------------|
| 3.1 | marked_html | `<li value="N">` to `<ol start="N">` | list_normalised_html |
| 3.2 | list_normalised_html | lxml: wrap `<p style="...">` in `<div style="...">` | normalised_html |
| 3.3 | normalised_html | Write to temp file | html_file_path |
| 3.4 | html_file_path | Pandoc subprocess | raw_pandoc_latex |
| 3.5 | raw_pandoc_latex | Fix `<br>ewline{}` in table contexts | newline_fixed_latex |
| 3.6 | newline_fixed_latex | Strip `\texorpdfstring` for luatexja | marked_latex |

---

## Level 2: Process 4 — Replace Markers with Highlights

This is where the known problem lives. Decomposed in detail.

```mermaid
flowchart TD
    %% External
    InLatex(["marked_latex"])
    InMeta(["highlight_metadata"])
    Output(["highlighted_latex"])

    %% Processes
    P4_1((4.1<br>Tokenize<br>markers))
    P4_2((4.2<br>Build<br>regions))
    P4_3((4.3<br>Wrap<br>regions))
    P4_4((4.4<br>Emit annot<br>commands))
    P4_5((4.5<br>Move annots<br>outside restricted<br>contexts))

    %% Flows
    InLatex -- "marked_latex" --> P4_1

    P4_1 -- "marker_tokens[]<br>(TEXT, HLSTART,<br>HLEND, ANNMARKER<br>with index + position)" --> P4_2

    P4_2 -- "regions[]<br>(text, active_set,<br>annot_indices)" --> P4_3

    InMeta -- "highlight_metadata<br>(colours, tags)" --> P4_3
    P4_3 -- "wrapped_regions[]<br>(LaTeX with<br>highLight/underLine)" --> P4_4

    InMeta -- "highlight_metadata<br>(tag, author, comments)" --> P4_4
    P4_4 -- "latex_with_annots" --> P4_5

    P4_5 -- "highlighted_latex<br>(annots at brace<br>depth 0)" --> Output
```

### Level 3: Process 4.3 — Wrap Regions (the problem area)

```mermaid
flowchart TD
    %% External
    InRegion(["region<br>(text, active_set)"])
    InMeta(["highlight_metadata"])
    Output(["wrapped_region"])

    %% Decision
    Check{active_set<br>empty?}

    %% Processes
    P4_3_1((4.3.1<br>Parse region<br>with pylatexenc))
    P4_3_2((4.3.2<br>Walk AST<br>classify segments))
    P4_3_3((4.3.3<br>Generate<br>wrappers))
    P4_3_4((4.3.4<br>Apply wrapping<br>per segment))
    PassThru((4.3.0<br>Pass through<br>unchanged))

    %% Flows
    InRegion -- "region" --> Check
    Check -- "yes" --> PassThru
    PassThru -- "region.text<br>(unchanged)" --> Output

    Check -- "no" --> P4_3_1
    P4_3_1 -- "latex_ast_nodes<br>(pylatexenc AST)" --> P4_3_2

    P4_3_2 -- "segments[]<br>(type: text|boundary,<br>content: string)" --> P4_3_4

    InMeta -- "colours for<br>active highlights" --> P4_3_3
    P4_3_3 -- "highlight_wrap()<br>underline_wrap()<br>(closure functions)" --> P4_3_4

    P4_3_4 -- "wrapped_region<br>text segs: \\highLight[c]{\\underLine[c]{text}}<br>boundary segs: pass through" --> Output
```

**This is the failure point for hl5/hl9.**

The problem: when a region's text spans a structural boundary (e.g. contains a `\section{...}` command), process 4.3.1 must parse that LaTeX correctly and 4.3.2 must identify the boundary so 4.3.4 can close and reopen the highlight wrapping around it.

**Data at each step for a cross-heading region:**

| Step | Data | Example for hl5 |
|------|------|-----------------|
| Input | region.text | `"...end of previous para<br><br>\\section{Grounds of Appeal}<br><br>Mr Lawlis sought..."` |
| 4.3.1 | pylatexenc AST | Nodes: [chars, group, macro(section), chars, ...] — **UNVERIFIED** |
| 4.3.2 | segments | `[("text", "...end"), ("boundary", "\\section{...}"), ("text", "Mr Lawlis...")]` — **UNVERIFIED** |
| 4.3.4 | wrapped | `\highLight{...end}<br><br>\section{Grounds of Appeal}<br><br>\highLight{Mr Lawlis...}` — **DESIRED** |

---

## Level 2: Process 5 — Assemble Document

```mermaid
flowchart TD
    %% External
    InBody(["highlighted_latex"])
    InColours(["tag_colours{}"])
    InNotes(["general_notes"])
    Output(["complete_tex"])

    %% Processes
    P5_1((5.1<br>Build colour<br>definitions))
    P5_2((5.2<br>Build<br>preamble))
    P5_3((5.3<br>Convert notes<br>to LaTeX))
    P5_4((5.4<br>Format document<br>template))

    %% Flows
    InColours -- "tag_colours{}" --> P5_1
    P5_1 -- "colour_defs<br>(\\definecolor commands)" --> P5_2
    P5_2 -- "preamble<br>(packages + colours<br>+ custom commands)" --> P5_4

    InNotes -- "general_notes<br>(HTML or markdown)" --> P5_3
    P5_3 -- "notes_latex<br>(\\section*{General Notes}...)" --> P5_4

    InBody -- "highlighted_latex" --> P5_4
    P5_4 -- "complete_tex<br>(\\documentclass...\\end{document})" --> Output
```

---

## Level 2: Process 6 — Compile to PDF

```mermaid
flowchart TD
    %% External
    InTex(["complete_tex"])
    LuaLaTeX([LuaLaTeX])
    Output(["PDF file"])
    D2[(D2: Filesystem)]

    %% Processes
    P6_1((6.1<br>Write .tex<br>to disk))
    P6_2((6.2<br>Resolve<br>latexmk path))
    P6_3((6.3<br>Run latexmk<br>-lualatex))
    P6_4((6.4<br>Verify PDF<br>exists + non-empty))

    %% Flows
    InTex -- "complete_tex" --> P6_1
    P6_1 -- ".tex file path" --> D2
    P6_2 -- "latexmk_path" --> P6_3
    D2 -- ".tex file" --> P6_3
    P6_3 -- ".tex file +<br>latexmk flags" --> LuaLaTeX
    LuaLaTeX -- ".pdf file +<br>.log file" --> D2
    D2 -- ".pdf file" --> P6_4
    P6_4 -- "PDF file<br>(verified)" --> Output
```

**Inside LuaLaTeX (opaque to us currently):**

The LuaLaTeX engine processes the .tex internally as:

1. **Macro expansion** — `\highLight[colour]{text}` expands
2. **Node list construction** — text becomes glyph nodes, `\highLight` sets lua-ul attributes
3. **lua-ul callback** (`pre_append_to_vlist_filter`) — scans for attribute boundaries, injects `\leaders\vrule` for backgrounds
4. **Line breaking, page breaking** — standard TeX
5. **PDF output** — rendered pages

We have **no visibility** into steps 1-5 from the Python side. The only feedback is: PDF exists (success) or compilation error in .log (failure).

---

## Summary: Where We Can Read and Write Data

| Point | Can Read? | Can Write/Modify? | Tool |
|-------|-----------|-------------------|------|
| raw_html | Yes | Yes | Python |
| preprocessed_html | Yes | Yes | Python (selectolax) |
| marked_html | Yes | Yes | Python |
| marked_latex (after Pandoc) | Yes | Yes | Python string ops |
| marked_latex (before P4) | Yes | Yes | Python |
| Pandoc conversion | No (black box) | Partially (Lua filters, flags) | Pandoc CLI |
| pylatexenc AST | Yes (read AST) | No (not round-trip safe) | pylatexenc |
| highlighted_latex | Yes | Yes | Python string ops |
| complete_tex | Yes | Yes | Python |
| LuaTeX node list | **Not currently** | **Not currently** | Lua callbacks (potential) |
| PDF output | Yes (file) | No | - |

**Key gap:** We cannot currently observe the LuaTeX node list. Experiment E4 would open this up.
