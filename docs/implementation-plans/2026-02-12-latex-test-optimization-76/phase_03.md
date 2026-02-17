# LaTeX Test Optimisation — Phase 3: Dynamic Font Loading

**Goal:** Load only the fonts needed for each document's actual Unicode content — English-only exports skip the 4.4s luaotfload overhead.

**Architecture:** A `FONT_REGISTRY` maps each fallback font to its OpenType script tag and Unicode detection ranges. `detect_scripts()` scans document text and returns needed script tags. `build_font_preamble()` emits a minimal `\directlua{}` fallback chain containing only matched fonts. The `.sty` keeps `fontspec` and `emoji` (always needed) but delegates font chain construction to Python. `\cjktext` uses a `\providecommand` / `\renewcommand` split: the `.sty` provides a safe pass-through default, and the font preamble overrides it when CJK fonts are loaded.

**Tech Stack:** Python 3.14, LuaLaTeX (fontspec, luatexja-fontspec, luaotfload), OpenType script tags

**Scope:** 5 phases from original design (phase 3 of 5)

**Codebase verified:** 2026-02-12

**Key files to read before implementing:**
- `src/promptgrimoire/export/unicode_latex.py` — `is_cjk()`, `escape_unicode_latex()`, other functions (UNICODE_PREAMBLE deleted by Phase 2)
- `src/promptgrimoire/export/promptgrimoire-export.sty` — created by Phase 2, contains full font setup that this phase makes dynamic
- `src/promptgrimoire/export/preamble.py` — `build_annotation_preamble()` (modified by Phase 2 to emit `\usepackage{promptgrimoire-export}`)
- `src/promptgrimoire/export/pdf_export.py` — `export_annotation_pdf()`, `generate_tex_only()` (created by Phase 1)
- `tests/integration/conftest.py` — `compile_mega_document()` (created by Phase 1)
- `scripts/setup_latex.py` — `REQUIRED_SYSTEM_FONTS` (lines 77+) for font name reference

---

## Acceptance Criteria Coverage

This phase implements and tests:

### latex-test-optimization.AC3: Dynamic font loading (DoD items 3, 6)

- **latex-test-optimization.AC3.1 Success:** `detect_scripts("שלום")` returns `frozenset({"hebr"})` (and similar for each supported script)
- **latex-test-optimization.AC3.2 Success:** `detect_scripts()` can detect every script tag in `_REQUIRED_SCRIPTS` — Guard 2 test iterates all entries and verifies detection
- **latex-test-optimization.AC3.3 Success:** `build_font_preamble(frozenset())` emits a fallback chain with only Latin base fonts (Gentium Plus, Charis SIL, Noto Serif) and no `luatexja-fontspec` loading
- **latex-test-optimization.AC3.4 Success:** `build_font_preamble(frozenset({"cjk"}))` emits `luatexja-fontspec`, CJK font setup (`\setmainjfont{Noto Serif CJK SC}`), and CJK entries in fallback chain
- **latex-test-optimization.AC3.5 Success:** An English-only document compiles in under 2 seconds (vs ~5s with full Unicode preamble)
- **latex-test-optimization.AC3.6 Success:** A document containing all `_REQUIRED_SCRIPTS` text renders without U+FFFD replacement characters
- **latex-test-optimization.AC3.7 Failure:** Adding a font to `FONT_REGISTRY` without a corresponding `detect_scripts()` range causes Guard 4 test to fail
- **latex-test-optimization.AC3.8 Edge:** `\cjktext{}` command works as pass-through when `luatexja-fontspec` is not loaded (no undefined command error)

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
## Subcomponent A: Font Registry and Script Detection

<!-- START_TASK_1 -->
### Task 1: Create font registry data structures

**Verifies:** None (infrastructure for Tasks 2-5)

**Files:**
- Modify: `src/promptgrimoire/export/unicode_latex.py` (add after imports, before existing functions)

**Implementation:**
Add four data structures to `unicode_latex.py`:

1. **`FallbackFont`** frozen dataclass:
   - `name: str` — font name for `\directlua` (e.g., `"Ezra SIL"`)
   - `script_tag: str` — OpenType script tag (e.g., `"hebr"`, `"latn"` for base fonts)
   - `options: str = ""` — luaotfload feature options (e.g., `"script=hebr"`)

2. **`FONT_REGISTRY`** — tuple of all 32 fallback fonts, mapped to script tags. Copy font names and options EXACTLY from the `.sty` file's `\directlua` block (which Phase 2 copied verbatim from the original `UNICODE_PREAMBLE`).

   The `options` field is the text after the colon and `mode=node;` prefix in the original Lua entry. For example, `"Ezra SIL:mode=node;script=hebr;"` becomes `FallbackFont("Ezra SIL", "hebr", "script=hebr")`. Base fonts have empty options.

   Font-to-tag mapping (32 fonts total):

   | Tag | Fonts |
   |-----|-------|
   | `latn` (base, always included) | Gentium Plus, Charis SIL, Noto Serif |
   | `hebr` | Ezra SIL, Noto Serif Hebrew |
   | `arab` | Scheherazade, Noto Naskh Arabic |
   | `deva` | Annapurna SIL, Noto Serif Devanagari |
   | `beng` | Noto Serif Bengali |
   | `taml` | Noto Serif Tamil |
   | `thai` | Noto Serif Thai |
   | `geor` | Noto Serif Georgian |
   | `armn` | Noto Serif Armenian |
   | `ethi` | Abyssinica SIL, Noto Serif Ethiopic |
   | `khmr` | Khmer Mondulkiri, Noto Serif Khmer |
   | `lao` | Noto Serif Lao |
   | `mymr` | Padauk, Noto Serif Myanmar |
   | `sinh` | Noto Serif Sinhala |
   | `tavt` | Tai Heritage Pro |
   | `copt` | Sophia Nubian |
   | `yiii` | Nuosu SIL |
   | `grek` | Galatia SIL |
   | `dsrt` | Noto Sans Deseret |
   | `osge` | Noto Sans Osage |
   | `shaw` | Noto Sans Shavian |
   | `zsym` | Noto Sans Symbols, Noto Sans Symbols2 |
   | `zmth` | Noto Sans Math |

3. **`SCRIPT_TAG_RANGES`** — dict mapping script tags to Unicode code point ranges for detection:

   ```python
   SCRIPT_TAG_RANGES: dict[str, list[tuple[int, int]]] = {
       "hebr": [(0x0590, 0x05FF), (0xFB1D, 0xFB4F)],
       "arab": [(0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF),
                (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
       "deva": [(0x0900, 0x097F), (0xA8E0, 0xA8FF)],
       "beng": [(0x0980, 0x09FF)],
       "taml": [(0x0B80, 0x0BFF)],
       "thai": [(0x0E00, 0x0E7F)],
       "geor": [(0x10A0, 0x10FF), (0x2D00, 0x2D2F)],
       "armn": [(0x0530, 0x058F), (0xFB00, 0xFB06)],
       "ethi": [(0x1200, 0x137F), (0x1380, 0x139F), (0x2D80, 0x2DDF),
                (0xAB00, 0xAB2F)],
       "khmr": [(0x1780, 0x17FF), (0x19E0, 0x19FF)],
       "lao":  [(0x0E80, 0x0EFF)],
       "mymr": [(0x1000, 0x109F), (0xAA60, 0xAA7F)],
       "sinh": [(0x0D80, 0x0DFF)],
       "cjk":  [(0x2E80, 0x2EFF), (0x3000, 0x303F), (0x3040, 0x309F),
                (0x30A0, 0x30FF), (0x31F0, 0x31FF), (0x3400, 0x4DBF),
                (0x4E00, 0x9FFF), (0xAC00, 0xD7AF), (0xF900, 0xFAFF),
                (0x20000, 0x2A6DF)],
       "grek": [(0x0370, 0x03FF), (0x1F00, 0x1FFF)],
       "cyrl": [(0x0400, 0x04FF), (0x0500, 0x052F), (0x2DE0, 0x2DFF),
                (0xA640, 0xA69F)],
       "tavt": [(0xAA80, 0xAADF)],
       "copt": [(0x2C80, 0x2CFF)],
       "yiii": [(0xA000, 0xA48F), (0xA490, 0xA4CF)],
       "dsrt": [(0x10400, 0x1044F)],
       "osge": [(0x104B0, 0x104FF)],
       "shaw": [(0x10450, 0x1047F)],
       "zsym": [(0x2600, 0x26FF), (0x2700, 0x27BF),
                (0x1F300, 0x1F5FF), (0x1F680, 0x1F6FF)],
       "zmth": [(0x2200, 0x22FF), (0x27C0, 0x27EF),
                (0x2980, 0x29FF), (0x1D400, 0x1D7FF)],
   }
   ```

   **Note:** `"cyrl"` is included for detection completeness — base Latin fonts (Gentium Plus, Charis SIL) already cover Cyrillic, so detecting Cyrillic adds no extra fonts from the registry. This is correct behaviour.

4. **`_REQUIRED_SCRIPTS`** — the set of all script tags that have font coverage:
   ```python
   _REQUIRED_SCRIPTS: frozenset[str] = frozenset(
       f.script_tag for f in FONT_REGISTRY if f.script_tag != "latn"
   )
   ```
   This is derived from FONT_REGISTRY, ensuring consistency. If a font is added with a new tag, `_REQUIRED_SCRIPTS` automatically includes it.

**Verification:**
Run: `uv run python -c "from promptgrimoire.export.unicode_latex import FONT_REGISTRY, SCRIPT_TAG_RANGES, _REQUIRED_SCRIPTS; print(len(FONT_REGISTRY), 'fonts,', len(_REQUIRED_SCRIPTS), 'required scripts,', len(SCRIPT_TAG_RANGES), 'detection ranges')"`
Expected: `32 fonts, <N> required scripts, <M> detection ranges` where N is the number of unique non-latn tags in FONT_REGISTRY and M >= N

**Commit:** `feat: add font registry and script tag ranges for dynamic font loading`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create detect_scripts() function

**Verifies:** latex-test-optimization.AC3.1, latex-test-optimization.AC3.2 (partial)

**Files:**
- Modify: `src/promptgrimoire/export/unicode_latex.py` (add function after data structures)

**Implementation:**
Add `detect_scripts()` that scans text for Unicode code points and returns the set of script tags needed:

```python
def detect_scripts(text: str) -> frozenset[str]:
    """Scan text and return OpenType script tags for detected non-Latin scripts.

    Latin/ASCII is always assumed present and not included in the result.
    An empty frozenset means only Latin base fonts are needed.
    """
    found: set[str] = set()
    for ch in text:
        cp = ord(ch)
        if cp < 0x0370:  # ASCII + Latin Extended — fast skip
            continue
        for tag, ranges in SCRIPT_TAG_RANGES.items():
            if tag in found:
                continue  # Already detected this script
            for start, end in ranges:
                if start <= cp <= end:
                    found.add(tag)
                    break
        if found >= _REQUIRED_SCRIPTS:
            break  # All possible scripts found, stop scanning
    return frozenset(found)
```

Key performance characteristics:
- O(n) where n = text length, but with early exit when all scripts found
- `cp < 0x0370` fast path skips ASCII/Latin-1/Latin Extended without checking any ranges (~99% of English text)
- Per-character, only checks script tags not yet found (shrinking inner loop)

**Verification:**
Run: `uv run python -c "from promptgrimoire.export.unicode_latex import detect_scripts; print(detect_scripts('Hello')); print(detect_scripts('שלום')); print(detect_scripts('Hello 你好 שלום'))"`
Expected: `frozenset()`, `frozenset({'hebr'})`, `frozenset({'cjk', 'hebr'})`

**Commit:** `feat: add detect_scripts() for Unicode script detection`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Write tests for detection and registry consistency

**Verifies:** latex-test-optimization.AC3.1, latex-test-optimization.AC3.2, latex-test-optimization.AC3.7

**Files:**
- Create: `tests/unit/export/test_font_detection.py`

**Testing:**

- **AC3.1:** Test `detect_scripts()` with representative text for each script. Use subtests for per-script iteration:
  - English/ASCII `"Hello world"` → `frozenset()` (empty — Latin is assumed)
  - Hebrew `"שלום"` → `frozenset({"hebr"})`
  - Arabic `"مرحبا"` → `frozenset({"arab"})`
  - CJK `"你好"` → `frozenset({"cjk"})`
  - Devanagari `"नमस्ते"` → `frozenset({"deva"})`
  - Greek `"αβγ"` → `frozenset({"grek"})`
  - Mixed `"Hello 你好 שלום"` → `frozenset({"cjk", "hebr"})`
  - Empty string `""` → `frozenset()`

- **AC3.2 (Guard 2):** For each `tag` in `_REQUIRED_SCRIPTS`, take the first code point from `SCRIPT_TAG_RANGES[tag][0][0]`, construct a single-character string via `chr(cp)`, call `detect_scripts()`, assert `tag` is in the result. This proves every registered font CAN be activated by detection.

- **AC3.7 (Guard 4 — data consistency):**
  - Assert `_REQUIRED_SCRIPTS` is a subset of `SCRIPT_TAG_RANGES.keys()` — every font tag has detection ranges
  - Assert every non-`"latn"` `script_tag` in `FONT_REGISTRY` appears in `SCRIPT_TAG_RANGES` — no font lacks a detection path
  - Construct text with one character from EVERY script in `_REQUIRED_SCRIPTS` (same approach as Guard 2 but combined). Call `detect_scripts()` and assert the result equals `_REQUIRED_SCRIPTS`.

**Verification:**
Run: `uv run pytest tests/unit/export/test_font_detection.py -v`
Expected: All tests pass

**Commit:** `test: guard tests for script detection and font registry consistency`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->
## Subcomponent B: Font Preamble Builder

<!-- START_TASK_4 -->
### Task 4: Create build_font_preamble()

**Verifies:** latex-test-optimization.AC3.3, latex-test-optimization.AC3.4

**Files:**
- Modify: `src/promptgrimoire/export/unicode_latex.py` (add function)

**Implementation:**
Add `build_font_preamble()` that generates a LaTeX font preamble with only the fonts needed:

```python
def build_font_preamble(scripts: frozenset[str]) -> str:
    """Build LaTeX font preamble with only fonts needed for detected scripts.

    Args:
        scripts: Script tags from detect_scripts(). Empty = Latin-only.

    Returns:
        LaTeX string for insertion between \\usepackage{promptgrimoire-export}
        and colour definitions in the document preamble.
    """
```

Logic:

**Step 1: Filter fonts.** Select all `"latn"` fonts (always) plus fonts whose `script_tag` is in `scripts`.

**Step 2: Build `\directlua` block.** For each selected font, format as `"{name}:mode=node;{options}"` — append `options` with trailing semicolon only if non-empty. Wrap in:
```latex
\directlua{
  luaotfload.add_fallback("mainfallback", {
    % ... entries ...
  })
}
```

**Step 3: CJK conditional block.** If `"cjk"` is in `scripts`, prepend (before `\directlua`):
```latex
\usepackage{luatexja-fontspec}
\ltjsetparameter{jacharrange={-2}}
```
And append (after `\directlua`):
```latex
\setmainjfont{Noto Serif CJK SC}[
  UprightFont = *,
  BoldFont = * Bold,
  ItalicFont = *,
  BoldItalicFont = * Bold,
]
\setsansjfont{Noto Sans CJK SC}[
  UprightFont = *,
  BoldFont = * Bold,
  ItalicFont = *,
  BoldItalicFont = * Bold,
]
\newjfontfamily\notocjk{Noto Serif CJK SC}
\renewcommand{\cjktext}[1]{{\notocjk #1}}
```

**CRITICAL:** Copy the CJK font face specifications EXACTLY from the `.sty` file (which has them from the original UNICODE_PREAMBLE). The `UprightFont`, `BoldFont`, `ItalicFont`, `BoldItalicFont` entries are required for luatexja compatibility.

**Step 4: Always emit `\setmainfont`.** Regardless of detected scripts:
```latex
\setmainfont{TeX Gyre Termes}[RawFeature={fallback=mainfallback}]
```

**Assembly order within the font preamble:**
1. `\usepackage{luatexja-fontspec}` + `\ltjsetparameter` (CJK only)
2. `\directlua{...}` fallback chain (always)
3. CJK font setup (CJK only)
4. `\setmainfont{TeX Gyre Termes}` (always)
5. `\renewcommand{\cjktext}` (CJK only)

**Verification:**
Run: `uv run python -c "from promptgrimoire.export.unicode_latex import build_font_preamble; print('=== LATIN ONLY ==='); print(build_font_preamble(frozenset())); print('=== WITH CJK ==='); print(build_font_preamble(frozenset({'cjk'})))"`
Expected: Latin-only output has 3 fonts in chain and no luatexja-fontspec. CJK output has luatexja-fontspec, CJK setup, and \renewcommand\cjktext.

**Commit:** `feat: add build_font_preamble() for dynamic font chain generation`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Write tests for font preamble output

**Verifies:** latex-test-optimization.AC3.3, latex-test-optimization.AC3.4

**Files:**
- Create: `tests/unit/export/test_font_preamble.py`

**Testing:**

- **AC3.3:** Call `build_font_preamble(frozenset())`. Assert:
  - Contains `Gentium Plus`, `Charis SIL`, `Noto Serif` in `\directlua` block
  - Contains `\setmainfont{TeX Gyre Termes}`
  - Does NOT contain `luatexja-fontspec`
  - Does NOT contain `\setmainjfont`
  - Does NOT contain `\renewcommand` with `cjktext`
  - Does NOT contain any non-base font names (`Ezra SIL`, `Scheherazade`, `Annapurna SIL`, etc.)

- **AC3.4:** Call `build_font_preamble(frozenset({"cjk"}))`. Assert:
  - Contains `\usepackage{luatexja-fontspec}`
  - Contains `\ltjsetparameter{jacharrange={-2}}`
  - Contains `\setmainjfont{Noto Serif CJK SC}`
  - Contains `\setsansjfont{Noto Sans CJK SC}`
  - Contains `\\newjfontfamily\\notocjk`
  - Contains `\renewcommand` with `cjktext` and `notocjk`
  - Contains `\setmainfont{TeX Gyre Termes}`
  - Still contains base fonts (Gentium Plus, etc.)

- **Mixed scripts:** Call `build_font_preamble(frozenset({"hebr", "arab"}))`. Assert:
  - Contains `Ezra SIL`, `Noto Serif Hebrew`, `Scheherazade`, `Noto Naskh Arabic`
  - Does NOT contain `luatexja-fontspec` or CJK fonts
  - Contains base fonts (Gentium Plus, Charis SIL, Noto Serif)

- **Full chain (Guard 4 end-to-end):** Call `build_font_preamble(_REQUIRED_SCRIPTS)`. Assert output contains every font name from `FONT_REGISTRY` (all 32). This verifies that detecting all scripts activates all fonts.

**Verification:**
Run: `uv run pytest tests/unit/export/test_font_preamble.py -v`
Expected: All tests pass

**Commit:** `test: guard tests for font preamble builder output`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 6-8) -->
## Subcomponent C: Pipeline Integration

<!-- START_TASK_6 -->
### Task 6: Update .sty — remove dynamic font content

**Verifies:** latex-test-optimization.AC3.8 (partial — .sty side of `\providecommand` split)

**Files:**
- Modify: `src/promptgrimoire/export/promptgrimoire-export.sty`

**Implementation:**
Modify the `.sty` file (created by Phase 2) to remove all dynamic font content. After this task, the `.sty` handles static setup only; fonts are generated dynamically by `build_font_preamble()`.

**Changes to make:**

1. **Replace `\RequirePackage{luatexja-fontspec}` with `\RequirePackage{fontspec}`.**
   `fontspec` is always needed (by the `emoji` package and by `\setmainfont` emitted from `build_font_preamble()`). `luatexja-fontspec` is now conditional — loaded by `build_font_preamble()` only when CJK text is detected.

2. **Keep `\RequirePackage{emoji}` and `\setemojifont{Noto Color Emoji}`** unchanged. Emoji support is always available.

3. **Remove these lines entirely** (the font setup section):
   - `\ltjsetparameter{jacharrange={-2}}`
   - The entire `\directlua{luaotfload.add_fallback("mainfallback", {...})}` block (the 32-font fallback chain)
   - `\setmainjfont{Noto Serif CJK SC}[...]`
   - `\setsansjfont{Noto Sans CJK SC}[...]`
   - `\newjfontfamily\notocjk{Noto Serif CJK SC}`
   - `\setmainfont{TeX Gyre Termes}[RawFeature={fallback=mainfallback}]`

4. **Replace `\newcommand{\cjktext}[1]{{\notocjk #1}}` with:**
   ```latex
   \providecommand{\cjktext}[1]{#1}
   ```
   This provides a safe pass-through default. When CJK is detected, `build_font_preamble()` emits `\renewcommand{\cjktext}[1]{{\notocjk #1}}` to override.

5. **Keep `\newcommand{\emojifallbackchar}[1]{[#1]}`** unchanged — this is static.

**Summary of font-related content remaining in .sty:**
```latex
\RequirePackage{fontspec}
\RequirePackage{emoji}
\setemojifont{Noto Color Emoji}
\providecommand{\cjktext}[1]{#1}
\newcommand{\emojifallbackchar}[1]{[#1]}
```

**Summary of what moved to `build_font_preamble()`:**
- `luatexja-fontspec` loading (conditional on CJK)
- `\ltjsetparameter{jacharrange={-2}}` (conditional on CJK)
- `\directlua{...}` fallback chain (dynamic, filtered by detected scripts)
- CJK font setup — `\setmainjfont`, `\setsansjfont`, `\newjfontfamily\notocjk` (conditional on CJK)
- `\setmainfont{TeX Gyre Termes}[...]` (always emitted, but must come after `\directlua`)
- `\renewcommand{\cjktext}[1]{{\notocjk #1}}` (conditional on CJK)

**Verification:**
Open the `.sty` and confirm:
- Contains `\RequirePackage{fontspec}` (NOT `luatexja-fontspec`)
- Does NOT contain `\directlua`, `\setmainjfont`, `\ltjsetparameter`, or the fallback chain
- Contains `\providecommand{\cjktext}[1]{#1}`

**Commit:** `refactor: remove dynamic font content from .sty (delegated to build_font_preamble)`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Update build_annotation_preamble() and callers

**Verifies:** latex-test-optimization.AC3.3, latex-test-optimization.AC3.4 (integration)

**Files:**
- Modify: `src/promptgrimoire/export/preamble.py` (update function signature and body)
- Modify: `src/promptgrimoire/export/pdf_export.py` (pass body_text to build_annotation_preamble)

**Implementation:**

**Step 1: Update `build_annotation_preamble()` in `preamble.py`.**

Add `body_text` parameter and import the new functions:

```python
from promptgrimoire.export.unicode_latex import detect_scripts, build_font_preamble
```

New function body:
```python
def build_annotation_preamble(tag_colours: dict[str, str], body_text: str = "") -> str:
    """Build complete annotation preamble with dynamic font loading.

    Args:
        tag_colours: Dict of tag_name -> hex colour.
        body_text: Document body text for Unicode script detection.
                   Empty string = Latin-only fonts (fast compilation).
    """
    scripts = detect_scripts(body_text)
    font_preamble = build_font_preamble(scripts)
    colour_defs = generate_tag_colour_definitions(tag_colours)
    return f"\\usepackage{{promptgrimoire-export}}\n{font_preamble}\n{colour_defs}"
```

The assembly order in the preamble is:
1. `\usepackage{promptgrimoire-export}` — .sty loads fontspec, emoji, static commands, `\providecommand{\cjktext}`
2. Font preamble — dynamic fallback chain, optional luatexja-fontspec + CJK setup, `\setmainfont`, optional `\renewcommand{\cjktext}`
3. Colour definitions — per-document tag colours

This ordering is required because:
- .sty loads `fontspec` → font preamble can use `\setmainfont`
- Font preamble defines `\notocjk` → can `\renewcommand{\cjktext}` to use it
- Colour definitions are independent of font setup

**Step 2: Update callers in `pdf_export.py`.**

In both `export_annotation_pdf()` and `generate_tex_only()` (created by Phase 1), the LaTeX body is available after the Pandoc conversion step. Pass it as `body_text`:

```python
# After the Pandoc conversion step produces latex_body:
preamble = build_annotation_preamble(tag_colours, body_text=latex_body)
```

The LaTeX body contains all original Unicode characters (Pandoc preserves them for LuaLaTeX). `detect_scripts()` correctly identifies scripts even in LaTeX-wrapped text because LaTeX commands are ASCII-only and don't trigger script ranges.

**The `body_text=""` default preserves backwards compatibility** — any caller that doesn't pass `body_text` gets Latin-only fonts. This is safe but slow for CJK documents. All production callers MUST pass the body text.

**Verification:**
Run: `uv run test-all`
Expected: All tests pass. If mega-doc tests fail (because `compile_mega_document()` doesn't pass body_text yet), proceed to Task 8 immediately.

**Commit:** `refactor: build_annotation_preamble() uses dynamic font loading via body_text parameter`
<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Update compile_mega_document() to pass body_text

**Verifies:** latex-test-optimization.AC3.6 (mega-doc side)

**Files:**
- Modify: `tests/integration/conftest.py` (update `compile_mega_document()`)

**Implementation:**
After Phase 1, `compile_mega_document()` builds a shared preamble using `build_annotation_preamble(all_tag_colours)`. After this phase, it must also pass combined body text for script detection.

Update `compile_mega_document()`:
1. After processing all segments and collecting their LaTeX bodies, concatenate them:
   ```python
   combined_body = "\n".join(segment_bodies.values())
   ```
2. Pass to `build_annotation_preamble()`:
   ```python
   preamble = build_annotation_preamble(all_tag_colours, body_text=combined_body)
   ```

This ensures:
- **English mega-doc** (all Latin content) → `detect_scripts()` returns `frozenset()` → minimal fallback chain → fast compilation (~1-2s)
- **i18n mega-doc** (CJK + multilingual) → `detect_scripts()` returns CJK + other scripts → full fallback chain → same speed as before (~5s)

This is the key performance win of Phase 3: English-only mega-docs skip the 4.4s luaotfload overhead.

**Verification:**
Run: `uv run pytest tests/integration/test_mega_doc_infrastructure.py -v`
Expected: Infrastructure test passes

Run: `uv run test-all -m latex`
Expected: All LaTeX tests pass, including i18n mega-doc (CJK fonts loaded dynamically)

**Commit:** `fix: compile_mega_document() passes body_text for dynamic font detection`
<!-- END_TASK_8 -->
<!-- END_SUBCOMPONENT_C -->

<!-- START_SUBCOMPONENT_D (tasks 9-10) -->
## Subcomponent D: Integration Tests and Verification

<!-- START_TASK_9 -->
### Task 9: Integration tests for compilation time and cjktext pass-through

**Verifies:** latex-test-optimization.AC3.5, latex-test-optimization.AC3.6, latex-test-optimization.AC3.8

**Files:**
- Modify: `tests/integration/test_pdf_export.py` (add integration test class)

**Testing:**

- **AC3.5 (English-only compile time):** Compile a simple English-only document through the production pipeline. Measure wall clock time with `time.monotonic()`. Assert: completes in under 2 seconds. Use `@requires_latexmk`.

  Use `generate_tex_only()` with English-only HTML (e.g., `"<p>The quick brown fox jumps over the lazy dog.</p>"`) + 1 simple highlight. Then call `compile_latex()` and time the compilation step only (not the Pandoc conversion). The body text contains only ASCII → `detect_scripts()` returns empty → Latin-only fonts → fast compilation.

- **AC3.6 (Full Unicode renders without tofu):** Verify that the existing `test_unicode_preamble_compiles_without_tofu` test in `test_latex_packages.py` still passes after Phase 3 (it should, since it compiles a document with BLNS strings using the full production pipeline, which now dynamically detects scripts). If this test's preamble construction doesn't go through `build_annotation_preamble()`, it may need updating to pass `body_text`.

  Additionally, the i18n mega-doc (from Phase 1) serves as a comprehensive AC3.6 test — it contains CJK text and should compile without U+FFFD after dynamic font loading.

- **AC3.8 (cjktext pass-through):** Compile a minimal Latin-only document that includes `\cjktext{hello}` in the body. The `.sty` provides `\providecommand{\cjktext}[1]{#1}` (pass-through), and `build_font_preamble(frozenset())` does NOT emit `\renewcommand{\cjktext}`. Assert: compiles without error. Assert: output PDF contains "hello". Use `@requires_latexmk`.

  Implementation approach: use `generate_tex_only()` to produce a `.tex` file from English-only HTML, then modify the `.tex` content to insert `\cjktext{hello}` before `\end{document}`, then call `compile_latex()`.

**Verification:**
Run: `uv run pytest tests/integration/test_pdf_export.py -k "english_compile_time or cjktext_passthrough" -v`
Expected: All tests pass, English compile < 2s

**Commit:** `test: integration tests for dynamic font loading (compile time, cjktext pass-through)`
<!-- END_TASK_9 -->

<!-- START_TASK_10 -->
### Task 10: Full regression verification

**Verifies:** All AC3 criteria (regression check)

**Files:**
- No file changes (verification only)

**Implementation:**
Verify that dynamic font loading produces no regressions:

1. Run the full LaTeX test suite: `uv run test-all -m latex -v`
2. Run the full test suite: `uv run test-all`
3. Verify no test regressions
4. Run `uv run pytest -m latex --durations=0` — check timing:
   - English mega-doc should complete in ~1-2s (Latin-only fonts, no luaotfload overhead)
   - i18n mega-doc should complete in ~5s (full font chain, same as before Phase 3)
   - Total LaTeX test time should be measurably lower than before Phase 3

The mega-doc tests from Phase 1 are the primary regression guard. If they pass, the font preamble is functionally correct. The English mega-doc's faster compilation is the observable benefit.

**Verification:**
Run: `uv run test-all`
Expected: All tests pass, zero regressions
<!-- END_TASK_10 -->
<!-- END_SUBCOMPONENT_D -->

---

## UAT Steps

1. [ ] Open `src/promptgrimoire/export/unicode_latex.py` — verify `FONT_REGISTRY`, `SCRIPT_TAG_RANGES`, `detect_scripts()`, `build_font_preamble()` exist
2. [ ] Run `uv run test-all -m latex -v` — all LaTeX tests pass
3. [ ] Run `uv run test-all` — full suite passes
4. [ ] Run `uv run pytest -m latex --durations=0` — verify English mega-doc completes in <2s
5. [ ] Verify `.sty` contains `\RequirePackage{fontspec}` (NOT `luatexja-fontspec`)
6. [ ] Verify `.sty` does NOT contain `\directlua` or `\setmainjfont`
7. [ ] Verify `.sty` contains `\providecommand{\cjktext}[1]{#1}`
8. [ ] Verify `build_annotation_preamble()` has `body_text` parameter
9. [ ] Run `uv run python -c "from promptgrimoire.export.unicode_latex import build_font_preamble; print(build_font_preamble(frozenset()))"` — verify Latin-only output (3 fonts, no luatexja-fontspec)

## Evidence Required
- [ ] Test output showing all tests green
- [ ] Duration output showing per-test times (English mega-doc <2s)
- [ ] `build_font_preamble(frozenset())` output showing minimal chain
- [ ] `build_font_preamble(frozenset({"cjk"}))` output showing CJK setup
