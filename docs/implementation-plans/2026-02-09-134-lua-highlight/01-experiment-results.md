# Issue #134 — Experiment Results

**Date:** 2026-02-09
**Branch:** `134-lua-highlight`
**Purpose:** Falsify assumptions from previous sessions before designing a solution.

## Hypothesis Table

| ID | Hypothesis | Result | Evidence |
|----|-----------|--------|----------|
| H1 | `\}` appears in Pandoc output and breaks pylatexenc | **PARTIALLY CONFIRMED** | Zero `\}` in the *Lawlis* fixture (no literal braces in source HTML). But Pandoc's LaTeX writer DOES produce `\}` for any literal `}` in input text — this is standard, correct LaTeX escaping. The `escape_latex` function in `libreoffice.lua` is dead code (never called) and was never the source. pylatexenc's walker chokes on `\}` during post-processing; with a Lua filter approach (no post-processing), `\}` ceases to be a problem. |
| H2 | Headings produce `\section{}` commands that break highlighting | **FALSIFIED** (for Lawlis) | Pandoc renders AustLII headings as `\textbf{}`, not `\section{}`. Other fixtures may differ. |
| H3 | The problem is `\section{}` moving arguments | **FALSIFIED** | Real problem is **environment boundaries** (`\begin{enumerate}`, `\end{enumerate}`, `\begin{quote}`, etc.) |
| H4 | lua-ul `\highLight{}` command cannot span `\par` | **CONFIRMED** | `\highLight{}` is a command taking `+m` argument. While it can contain `\par`, crossing environment boundaries is structurally impossible with braces. |
| H5 | lua-ul environment approach can span paragraphs and sections | **CONFIRMED** | `\@highLight` (setter form) + `\LuaULResetUnderline*` + empty paragraph trick works. Zero leaks. |
| H6 | Pandoc Lua filters can see `<span>` attributes | **CONFIRMED** | Attributes visible but `data-` prefix is stripped: `data-hl="5"` becomes `hl="5"`. |
| H7 | Cross-block `<span>` survives Pandoc HTML parsing | **FALSIFIED** | Silently destroyed. No Span nodes in AST, all attributes lost, no warning. |
| H8 | Pre-split spans work through Pandoc Lua filters | **CONFIRMED** | Three separate `<span>` elements → three `Span` AST nodes → correct `\highLight[color]{...}` output. |

## E1: Does `\}` Exist in Pandoc Output?

**Method:** Ran Pandoc on the Lawlis v R HTML fixture (same pipeline as production), grep'd for `\}`.

**Result:** Zero `\}` in the *Lawlis fixture* output. The "Copyright" context from WIP notes is actually `Copyright \&` (escaped ampersand).

However, further testing showed Pandoc's LaTeX writer DOES produce `\}` — for any literal `}` character in input HTML:
```
$ echo '<p>Text with {braces}</p>' | pandoc -f html -t latex
Text with \{braces\}
```

The Lawlis fixture has no literal braces, so E1 found zero. Other user content (code snippets, JSON, etc.) will produce `\}`. This is standard, correct LaTeX escaping.

The `escape_latex` function in `libreoffice.lua` was **dead code** (never called by any filter callback) and was never the source. Removed in this branch to prevent future confusion.

**Implication:** `\}` is a real concern for pylatexenc-based post-processing (it can't parse `\}` correctly). With a Lua filter approach that wraps highlights DURING Pandoc conversion (before `\}` escaping occurs in the LaTeX writer), the problem is eliminated entirely — `\}` only exists in the final LaTeX output which LuaLaTeX handles correctly.

## E2: hl5 and hl9 Marked LaTeX Structure

**Method:** Dumped the full `marked_latex` string after Pandoc conversion, before marker replacement, for the Lawlis fixture.

### hl5 (jurisdiction) — Lines 128-145

```latex
\textbf{HLSTART5ENDHLGrounds of Appeal}

\begin{enumerate}
\setcounter{enumi}{3}
\tightlist
\item
  Mr Lawlis sought leave to rely on three grounds of appeal:
\end{enumerate}

\begin{quote}
``Ground 1 -- ...
Ground 3 -- The sentence imposed was manifestly
excessive.''HLEND5ENDHLANNMARKER5ENDMARKER
\end{quote}
```

**Key observations:**
- HLSTART is *inside* `\textbf{...}`
- Spans 3 environment boundaries: `\end{enumerate}`, `\begin{enumerate}/\end{enumerate}`, `\begin{quote}`
- No `\section{}` commands

### hl9 (legal_issues) — Lines 232-271

```latex
  in company, being committed in the hHLSTART9ENDHLomes of the victims
  ...
\end{enumerate}

\textbf{Subjective factors}

\begin{enumerate}
...
\end{enumerate}

\begin{quote}
...
\end{quote}

\begin{enumerate}
...
  medicationHLEND9ENDHLANNMARKER9ENDMARKERs, but they caused him
```

**Key observations:**
- HLSTART is mid-word inside `\item` body
- Crosses 6 environment boundaries
- Includes a `\textbf{Subjective factors}` heading between environments

## E4: lua-ul Environment Approach

**Method:** Iterative LaTeX experiments (v1-v7) testing custom environment definitions, verified with mutool PDF analysis for pixel-level highlight detection.

### Working Definition

```latex
\makeatletter
\newenvironment{hlenv}[1][yellow]{%
  \@highLight[#1]%
}{%
  \par
  \LuaULResetUnderline*%
  \nointerlineskip
  {\parskip=0pt\relax\leavevmode\par}%
}
\makeatother
```

### Why `\leavevmode\par` is Required

lua-ul uses a `pre_append_to_vlist_filter` callback that processes each paragraph as it enters the vertical list. When `\LuaULResetUnderline*` clears the attribute register, the *next* paragraph has already started building with the old attribute value. The `\leavevmode\par` creates a zero-height empty paragraph that gets processed by the callback, absorbing the lingering attribute.

Without it, highlighting leaks exactly one paragraph past `\end{hlenv}`.

### What Was Tried and Failed

| Approach | Result |
|----------|--------|
| `\LuaULResetUnderline` (single) | LEAK |
| `\LuaULResetUnderline*` (all) | LEAK |
| `\begingroup...\endgroup` | LEAK |
| `\par` before/after reset | LEAK |
| `\setbox0=\vbox{\leavevmode}` | LEAK (boxed away from vertical list) |
| `\hbox{}` | LEAK (doesn't trigger callback) |

### Test Matrix

| Test | Scenario | Result | Extra spacing |
|------|----------|--------|---------------|
| A | 3 paragraph breaks | CLEAN | 0.7pt |
| B | Section boundary crossing | CLEAN | 0.7pt |
| C | Sequential yellow + cyan environments | CLEAN | 0.7pt each |
| D | Single paragraph | CLEAN | 0.7pt |

Zero errors, zero warnings, zero overfull/underfull boxes.

## E5: Pandoc Lua Filter AST Access

**Method:** Created two test HTML files — pre-split spans and cross-block span — with a diagnostic Lua filter that dumps AST structure and wraps `hl` spans.

### Test 1: Pre-split spans (valid HTML)

```html
<p>Some text <span class="hl" data-hl="5">highlighted text before heading</span></p>
<h2><span class="hl" data-hl="5">Grounds of Appeal</span></h2>
<p><span class="hl" data-hl="5">Mr Lawlis sought leave</span> to rely on three grounds.</p>
```

**Pandoc AST:** 3 separate `Span` nodes, each with `hl="5"` attribute (note: `data-` prefix stripped).

**LaTeX output:**
```latex
Some text \highLight[yellow]{highlighted text before heading}

\subsection{\texorpdfstring{\highLight[yellow]{Grounds of
Appeal}}{Grounds of Appeal}}\label{grounds-of-appeal}

\highLight[yellow]{Mr Lawlis sought leave} to rely on three grounds.
```

Pandoc auto-wraps heading content in `\texorpdfstring{}{}` for PDF bookmarks.

### Test 2: Cross-block span (invalid HTML)

```html
<p>Some text <span class="hl" data-hl="7">highlighted across</p>
<h2>A Heading</h2>
<p>multiple blocks</span> and more text.</p>
```

**Pandoc AST:** Zero `Span` nodes. Text reorganised into new paragraphs. All attributes lost. No error, no warning. **Total silent destruction.**

## E2b: Real Section Headings with Pre-Split Spans

**Method:** Created HTML with two highlights (yellow, cyan) crossing `<h1>`, `<h2>`, `<h3>` boundaries. Pre-split at block boundaries. Processed through Pandoc with a Lua filter that wraps `hl` spans in `\highLight[color]{...}`.

**Result:** All headings rendered as real `\section{}`, `\subsection{}`, `\subsubsection{}` commands. Pandoc auto-wrapped highlighted heading content in `\texorpdfstring{}`:

```latex
\subsection{\texorpdfstring{\highLight[yellow]{Highlighted
Heading}}{Highlighted Heading}}\label{highlighted-heading}
```

PDF bookmarks get plain text while typeset headings get highlights. Zero special handling needed in the Lua filter.

**Artefacts:** `experiments/e2b-section-headings/`

## E6A: Overlapping Highlights — Comma-Separated Attributes (RECOMMENDED)

**Method:** Hand-crafted LaTeX demonstrating the "one, two, many" stacking model. DOM walker emits flat spans: `<span data-hl="1,2" data-colors="yellow,cyan">`. Lua filter parses comma-separated values and generates nested wrapping.

**Stacking tiers:**

| Active count | Highlights | Underlines |
|-------------|-----------|------------|
| 1 | `\highLight[yellow]{text}` | 1pt, colour-matched |
| 2 | `\highLight[yellow]{\highLight[cyan]{text}}` | 2pt outer + 1pt inner, colour-matched |
| 3+ | `\highLight[y]{\highLight[c]{\highLight[p]{text}}}` | 4pt many-dark (single thick bar) |

**Why this wins:** All stacking logic in ONE place (Lua filter). DOM walker stays simple — flat spans, no nesting, just comma-separated lists of active highlights.

**Artefacts:** `experiments/e6a-overlap-comma-sep/`

## E6B: Overlapping Highlights — Nested HTML Spans (NOT RECOMMENDED)

**Method:** One HTML `<span>` per highlight layer, physically nested.

**Result:** Functionally identical LaTeX output to E6A (confirmed by nesting-order-test), but complexity shifts to DOM walker: must generate nested elements, assign stacking roles, and duplicate the stacking logic. Two places to maintain stacking rules.

**Artefacts:** `experiments/e6b-overlap-nested-spans/`

## Nesting Order Test

**Method:** Two test cases — "underlines grouped outside highlights" vs "underlines interleaved with highlights" — compiled and compared with `mutool draw -F trace`.

**Result:** Pixel-identical output. lua-ul renders based on accumulated node attributes, not nesting order. This means Approach A's grouped nesting and any other ordering are visually equivalent.

**Artefacts:** `experiments/nesting-order-test/`

## E7: Perverse Overlapping Highlights — Full Pipeline

**Method:** Exercised the FULL existing pipeline end-to-end with 4 overlapping highlights crossing a heading boundary. All stacking tiers exercised (0, 1, 2, 3+ active highlights).

**Test case:**

```
Heading: "This is demo. With silly header."
Paragraph: "Foo bar the test text is going here but is very mixed up."

hl0 (jurisdiction): chars 5-61  — heading into paragraph
hl1 (legal_issues):  chars 19-71 — heading into paragraph
hl2 (ratio):         chars 54-78 — paragraph only, overlaps hl0+hl1
hl3 (obiter):        chars 68-70 — just "but", nested inside hl1+hl2
```

**Pipeline stages run:** `_insert_markers_into_html()` → Pandoc → `tokenize_markers()` → `build_regions()` → `_replace_markers_with_annots()` / `walk_and_wrap()` → LuaLaTeX compilation.

**Result:** 9 regions correctly identified. PDF compiled (17,196 bytes, 1 page). 18 coloured rectangles verified via `mutool`. All stacking tiers rendered correctly — single underlines for 1-hl regions, stacked doubles for 2-hl, thick many-dark bar for 3+.

**Warnings (all non-issues):**

| Warning | Count | Status |
|---------|-------|--------|
| hyperref Token | 6 | Non-issue: `\texorpdfstring` already stripped by `_strip_texorpdfstring()` in production pipeline. Lua filter approach eliminates entirely (E2b proved). |
| `\label{}` marker debris | 1 | Non-issue: labels are unwanted; can be stripped or suppressed via Pandoc flag. |
| Overfull hbox | 4 | Cosmetic: margin notes exceed right margin. Known, expected. |

**Artefacts:** `experiments/e7-perverse-overlap/`

---

## Synthesis: What We Now Know

### The region model is reliable

E7 proves the core algorithm — tokenize markers, build regions with constant active-highlight sets, wrap each region — handles arbitrarily perverse overlap patterns correctly. 9 regions, 4 annotations, all stacking tiers, zero logic errors.

### The problems are all in the pipeline around it

1. **Cross-block `<span>` silently destroyed by Pandoc** (H7, E5) — this is why the marker-in-text approach exists
2. **`\}` breaks pylatexenc** (H1) — only matters because post-Pandoc processing uses pylatexenc
3. **Environment boundaries break `\highLight{}`** (H3, H4) — but `walk_and_wrap()` handles this correctly

### The path forward: Pre-split + Lua filter

**Pre-split highlights at HTML block boundaries before Pandoc.** This eliminates the root cause (H7) and enables a Lua filter approach that sidesteps all downstream problems.

1. **DOM walker pre-splits** highlight spans at block boundaries → each block gets its own `<span class="hl" data-colors="yellow,cyan">`
2. **Pandoc sees valid HTML** → `Span` nodes survive in AST (E5 proved)
3. **Lua filter** wraps each span in `\highLight[color]{...}` with "one, two, many" stacking (E6A design)
4. **Pandoc auto-wraps headings** in `\texorpdfstring{}` for bookmark safety (E2b proved)

### What this eliminates

The entire Process 4 pipeline from the DFD:
- `tokenize_markers()` (Lark grammar)
- `build_regions()` (state machine)
- `walk_and_wrap()` / `_wrap_region_ast()` (pylatexenc walker)
- `generate_highlighted_latex()` (region wrapper)
- `_move_annots_outside_restricted()` (brace depth tracking)
- `_strip_texorpdfstring()` (Lua filter handles heading wrapping natively)
- The entire marker system (`HLSTART/HLEND/ANNMARKER`)
- `pylatexenc` dependency (no more post-Pandoc LaTeX parsing)

### What the environment approach (E4) is for

`\begin{hlenv}` **cannot** handle overlapping highlights — LaTeX environments must nest properly, and overlapping highlights are structurally non-nesting. The environment is only viable for single-colour block-spanning highlights where no overlap exists. Given that pre-splitting handles all cases, the environment approach is documented but not needed.

### Remaining decisions

1. **Where to pre-split:** In the existing `_insert_markers_into_html()` (P2), or as a new HTML processing step before Pandoc (P3)?
2. **Annotation markers:** How do margin notes (`\annot{}`) work with the Lua filter approach? Currently they're text markers placed at HLEND positions. The Lua filter could emit them as `RawInline("latex", "\\annot{...}")` at span boundaries.
3. **`\label{}` suppression:** Strip via post-processing or suppress via Pandoc flag (`-V header-attributes=false` or a Lua filter that removes labels)?
4. **Stacking colour definitions:** The "one, two, many" model needs colour definitions in the preamble. Currently handled by `_build_colour_definitions()`. The Lua filter approach needs the same colours available.

### Hypothesis status update

| ID | Hypothesis | Final Status |
|----|-----------|-------------|
| H1 | `\}` in Pandoc output breaks pylatexenc | **CONFIRMED** but **IRRELEVANT** — Lua filter approach eliminates pylatexenc |
| H2 | Headings produce `\section{}` that breaks highlighting | **FALSIFIED** for Lawlis; **HANDLED** for other fixtures by pre-splitting + `\texorpdfstring{}` |
| H3 | `\section{}` moving arguments is the problem | **FALSIFIED** — real problem is environment boundaries, and `walk_and_wrap()` handles them |
| H4 | `\highLight{}` cannot span `\par` | **CONFIRMED** but **IRRELEVANT** — pre-splitting means it doesn't need to |
| H5 | lua-ul environment can span paragraphs/sections | **CONFIRMED** — but cannot handle overlapping highlights |
| H6 | Pandoc Lua filters see `<span>` attributes | **CONFIRMED** — `data-` prefix stripped (`data-hl` → `hl`), use plural names to avoid collisions |
| H7 | Cross-block `<span>` survives Pandoc | **FALSIFIED** — silently destroyed, pre-splitting mandatory |
| H8 | Pre-split spans work through Lua filters | **CONFIRMED** — three spans → three Span nodes → correct `\highLight` output |
| H9 | `\underLine`/`\highLight` nesting order matters | **FALSIFIED** — lua-ul renders identically regardless of nesting order |
| H10 | Region model handles perverse overlaps | **CONFIRMED** — E7 exercised all tiers (0, 1, 2, 3+) with 4 overlapping highlights |
| H11 | `\label{}` marker debris is a problem | **FALSIFIED** — labels unwanted, already suppressible |
| H12 | `\texorpdfstring{}` in headings is a problem | **FALSIFIED** — already stripped by `_strip_texorpdfstring()`; Lua filter approach eliminates entirely |
