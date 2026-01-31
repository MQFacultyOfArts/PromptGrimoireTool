# CSS Fidelity for PDF Export Design

## Summary

Define explicit CSS handling rules for the HTML-to-PDF export pipeline. Ensures all 11 conversation fixtures render to PDF satisfactorily (readable, complete, content images preserved, UI chrome discarded) using a three-tier classification: Essential, Nice-to-have, Discard.

## Definition of Done

**Success criteria:**
1. Unit handling: `em`, `rem`, `px` supported in Lua filter (`libreoffice.lua`)
2. Speaker pre-processing: Platform detection + label injection + visual styling
3. UI chrome removal: BeautifulSoup pre-processor strips avatars, icons, buttons
4. All 11 fixtures compile without LaTeX errors (automated test)
5. Visual review: PDFs eyeballed and satisfactory (manual, one-time)

**Out of scope:**
- Annotation layer integration (that's #100)
- Faithful-to-source styling (goal is readable & complete)
- Platform-specific edge cases beyond the 11 fixtures

## Glossary

| Term | Definition |
|------|------------|
| **Essential tier** | CSS properties that must work for readable output; test fails if broken |
| **Nice-to-have tier** | CSS properties with best-effort handling; graceful degradation if they fail |
| **Discard tier** | CSS properties actively stripped; they break LaTeX or serve no PDF purpose |
| **Speaker distinction** | Visual differentiation between user and assistant turns in chatbot exports |
| **UI chrome** | Interface elements (avatars, icons, buttons) that aren't document content |

## Problem Statement

Issue #76: PDF export needs to handle CSS from arbitrary HTML sources (chatbot exports, legal documents) without human visual inspection of every output.

**Constraints:**
- HTML treated as faithful and correct (arbitrary sources)
- Must respect original document structure
- PDF rendering trusted to LaTeX once LaTeX is correct
- "Readable & complete" goal, not "faithful to source styling"

## Architecture

### Pipeline Overview

```
HTML (chatbot export, legal doc, etc.)
       ↓
[Pre-processor: Speaker detection + label injection]  ← NEW
       ↓
[Pre-processor: UI chrome removal]  ← NEW
       ↓
[Pandoc + Lua filter]  ← ENHANCED (unit handling)
       ↓
LaTeX
       ↓
[latexmk]
       ↓
PDF
```

### Tiered CSS Classification

| Tier | Properties | Handling | Failure Mode |
|------|------------|----------|--------------|
| **Essential** | Tables, lists, margins, speaker distinction, rendered markdown | Must produce correct LaTeX | Test fails |
| **Nice-to-have** | Images, code blocks, font weights, borders | Best effort | Warning logged, continue |
| **Discard** | UI chrome, interactive elements, layout hacks | Strip entirely | Silent removal |

## Essential Tier Detail

### Tables with Column Widths (already working)
- Extract `width` attributes from `<col>` or `<td>`
- Convert to proportional `\textwidth` fractions
- Output: `\begin{longtable}{p{0.3\textwidth}p{0.7\textwidth}}`

### Lists (partially working)
- `<ol start="N">` → `\setcounter{enumi}{N-1}` ✓
- Nested lists → LaTeX nested `enumerate`/`itemize` (Pandoc handles)
- Custom markers → best effort via Pandoc

### Margins/Indentation (partially working)
- `margin-left: Xin/cm` → `\begin{adjustwidth}{X}{}` ✓
- **TODO**: Add `em`, `rem`, `px` unit handling

### Speaker Visual Distinction (TODO)

**Platform detection heuristics:**
| Platform | Detection Pattern | User Marker | Assistant Marker |
|----------|------------------|-------------|------------------|
| Claude | `font-user-message` | `font-user-message` | `font-claude-response` |
| Gemini | `chat-turn-container` | `.user` on container | `.model` on container |
| OpenAI | `agent-turn` | `items-end`, `user-message-bubble-color` | `agent-turn` |
| ScienceOS | `tabler-icon-robot` | `tabler-icon-medal` | `tabler-icon-robot` |
| AustLII | `the-document` | N/A (legal document) | N/A |

**Implementation:**
1. Detect platform from HTML structure
2. Find turn boundaries using platform-specific selectors
3. Inject text labels: `<strong>User:</strong>` / `<strong>Assistant:</strong>`
4. Convert speaker CSS classes to inline `background-color` style

**LaTeX output:**
- User turns: light grey background via `\colorbox{userbg}{...}` or left border
- Assistant turns: white/default background
- Fallback: If detection fails, content still renders (labels ensure readability)

### Rendered Markdown
- Pandoc handles natively (headers, bold, italic, links)
- Blockquotes → LaTeX `quote` environment
- No raw markdown should appear in output

## Nice-to-have Tier Detail

### Content Images
- Pandoc passes `<img>` through to LaTeX `\includegraphics`
- Supported: PNG, JPG, PDF
- Challenge: Base64 data URIs need extraction to temp files
- Fallback: `[Image: alt-text]` placeholder if image fails

### Code Blocks
- Pandoc converts `<pre><code>` to LaTeX `verbatim` or `listings`
- Syntax highlighting via `--highlight-style` flag
- Background color: Best effort via `\colorbox` wrapping
- Fallback: Monospace text without background

### Font Weights
- Bold/italic: Pandoc handles natively
- `font-weight: 500-700`: Map to bold
- `font-weight: 300-400`: Map to normal
- Fallback: Normal weight

### Borders
- `border-left` on blockquotes: Convert to `\vrule` or `mdframed`
- Table borders: Pandoc's default `longtable` styling
- Fallback: No border

### Unit Conversion

| CSS Unit | LaTeX Conversion | Status |
|----------|------------------|--------|
| `in` | Pass through | ✓ Done |
| `cm` | Pass through | ✓ Done |
| `em` | LaTeX `em` (native) | TODO |
| `rem` | Convert to `em` (1:1) | TODO |
| `px` | Convert to `pt` (×0.75) | TODO |

## Discard Tier Detail

### UI Chrome Images
| Pattern | Platform | Element |
|---------|----------|---------|
| `avatar`, `profile-pic` | All | User/AI avatars |
| `tabler-icon-*` | ScienceOS | Icon fonts |
| `copy-button`, `share-button` | All | Action buttons |
| `logo`, `brand` | All | Platform branding |
| `<img>` with dimensions <32px | All | Icons, bullets |

### Interactive Elements
- `onclick`, `onmouseover` attributes → strip
- `<button>`, `<input>` → remove entirely
- `cursor: pointer` → ignore

### Layout Hacks
- `position: fixed/absolute` → strip
- `display: none` → remove element
- `visibility: hidden` → remove element
- `z-index`, `overflow` → ignore

### Animations
- `transition`, `animation` → ignore
- `transform` (except simple scaling) → ignore

### Platform Cruft
- Tailwind utility classes with no semantic meaning
- Minified/hashed class names (e.g., `m_1b7284a3`)
- JS framework data attributes (`data-reactid`, `ng-*`)

## Testing Strategy

### Layer 1: LaTeX Correctness (automated)
Existing `test_css_fidelity.py` pattern:
```python
def test_speaker_labels_injected():
    html = load_fixture("openai_chat.html")
    latex = convert_html_to_latex(html)
    assert "\\textbf{User:}" in latex
```

### Layer 2: PDF Compilation (automated)
```python
@pytest.mark.requires_latexmk
def test_fixture_compiles(fixture_name):
    html = load_fixture(fixture_name)
    latex = convert_html_to_latex(html)
    pdf_bytes = compile_latex_to_pdf(latex)
    assert pdf_bytes  # Non-empty = success
```

### Layer 3: Visual Inspection (manual, one-time)
PDFs are generated by `TestChatbotFixturesToPdf` in `tests/integration/test_chatbot_fixtures.py` to `output/test_output/chatbot_*/`. Human review for:
- Speaker distinction visible
- Content images present
- No obvious layout breakage
- Text readable

## Fixture Test Matrix

| Fixture | Platform | Speaker Detection | Images | Code |
|---------|----------|-------------------|--------|------|
| claude_cooking.html | Claude | `font-user-message` / `font-claude-response` | ? | ? |
| claude_maths.html | Claude | `font-user-message` / `font-claude-response` | ? | ✓ |
| gemini_crdt_discussion.html | Gemini | `.user` / `.model` | ✓ | ? |
| gemini_gemini.html | Gemini | `.user` / `.model` | ✓ | ? |
| gemini_images.html | Gemini | `.user` / `.model` | ✓ | ? |
| openai_chat.html | OpenAI | `items-end` / `agent-turn` | ✓ | ? |
| openai_dr.html | OpenAI | `items-end` / `agent-turn` | ✓ | ? |
| openai_images.html | OpenAI | `items-end` / `agent-turn` | ✓ | ? |
| scienceos_locus.html | ScienceOS | `tabler-icon-medal` / `tabler-icon-robot` | ? | ? |
| scienceos_rubber.html | ScienceOS | `tabler-icon-medal` / `tabler-icon-robot` | ? | ? |
| austlii.html | AustLII | N/A (legal document) | ✗ | ✗ |

## Related Issues

- #76: PDF Export - Automated CSS fidelity testing at LaTeX level (this design)
- #100: Seam H - Export Integration (workspace integration, depends on this)
- #93: Seam A - Workspace Model (note added re: conversation turn segmentation)

## Implementation Phases

### Phase 1: Unit Handling
- Update `libreoffice.lua` to handle `em`, `rem`, `px`
- Add tests for each unit type

### Phase 2: Speaker Pre-processing
- Build platform detection in Python
- Implement label injection
- Implement visual styling preservation
- Add tests per platform

### Phase 3: UI Chrome Removal
- Build BeautifulSoup pre-processor
- Pattern matching for chrome elements
- Add tests for each pattern

### Phase 4: Fixture Validation
- Automated compilation tests for all 11 fixtures
- Manual visual review
- Sign-off and close #76

## Implementation Status (2026-01-31)

### Completed
- **Phase 1**: Unit handling (em/rem/px) in `libreoffice.lua` ✓
- **Phase 2**: Speaker preprocessor (`speaker_preprocessor.py`) ✓
- **Phase 3**: Chrome remover (`chrome_remover.py`) with ID-based removal ✓
- **Phase 4 (partial)**: All 11 fixtures compile to PDF without LaTeX errors ✓

### Packages Added to TinyTeX
- `luabidi` - Bidirectional text for LuaLaTeX (fixes `\begin{LTR}` environments)
- `fancyvrb` - Verbatim blocks

### Pandoc Changes
- Added `--no-highlight` to avoid undefined syntax highlighting macros

### LaTeX Post-processing
- `_fix_invalid_newlines()` removes `\newline{}` in invalid table contexts

### Progress (2026-01-31 Session 2)

**Fixed:**
- ✓ AustLII navigation chrome removed (ribbon, page-header, page-side, page-tertiary)
- ✓ Added `list_normalizer.py` - converts `<li value="N">` to `<ol start="N">` for Pandoc
- ✓ Paragraph numbering now preserved via `\setcounter{enumi}` in LaTeX
- ✓ Added `hidelinks` option to hyperref (removes blue link boxes)
- ✓ Generalized `parse_margin` in Lua filter for future margin-top/bottom support

**Verified working:**
- Chrome removal pipeline: `inject_speaker_labels()` → `remove_ui_chrome()` → `convert_html_to_latex()`
- AustLII HTML (113KB) → preprocessed (64KB, 44% reduction) → clean LaTeX

**Still broken:**
- Table structure: Pandoc mangles AustLII table cells (missing `&` delimiters)
- First table shows "Court of Criminal Appeal" / "Supreme Court" / "New South Wales" in wrong columns

### UAT Status

**austlii.html:**
- ~~Link menus at top still present~~ ✓ FIXED - chrome removed
- Decision column incorrectly placed (Pandoc table parsing issue)
- Tables structurally wrong (Pandoc issue, not preprocessing)
- ~~Paragraph numbering resets~~ ✓ FIXED - list_normalizer preserves numbering

**Blocking issue:**
- Database migration mismatch (`fe6d5d784dab` not found) - blocks pytest integration tests
- Unrelated to PDF export work, needs separate fix

### Next Steps
1. Fix Pandoc table parsing - investigate why cell structure is lost
2. Compare HTML table structure before/after preprocessing
3. Consider custom Lua filter for AustLII table structure
4. Fix database migration issue (separate task)
