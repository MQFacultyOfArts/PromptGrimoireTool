# Experiment Artefacts for Issue #134

All experiments compiled with LuaLaTeX via latexmk. PDFs verified with `mutool draw -F trace` for pixel-level highlight rectangle detection.

## Two Approaches Tested

### Approach 1: HTML Pre-Split + Pandoc Lua Filter (RECOMMENDED)

Split highlight spans at HTML block boundaries _before_ Pandoc. Each block gets its own `<span class="hl">`. A Pandoc Lua filter converts these spans to `\highLight[color]{...}` commands during LaTeX generation.

**Eliminates the entire post-Pandoc pipeline** (Lark tokenizer, region builder, pylatexenc walker, marker system).

| Experiment | What it tests | Result |
|-----------|---------------|--------|
| `e5-presplit-proof/` | Pre-split spans survive Pandoc; cross-block spans are silently destroyed | PASS |
| `e2b-section-headings/` | Pre-split spans across real `\section{}`, `\subsection{}`, `\subsubsection{}` | PASS |
| `e6a-overlap-comma-sep/` | "One, two, many" stacking via comma-separated `data-colors` attribute | PASS |
| `e6b-overlap-nested-spans/` | Same stacking via nested HTML spans (Approach B, not recommended) | PASS |
| `nesting-order-test/` | Proves `\underLine`/`\highLight` nesting order doesn't matter to lua-ul | PASS |
| `e7-perverse-overlap/` | Full pipeline with 4 overlapping highlights across heading boundary; all stacking tiers | PASS |

### Approach 2: Lua Environment (FALLBACK — single colour only)

Uses `\begin{hlenv}[color]...\end{hlenv}` custom LaTeX environment that can span paragraph breaks and section boundaries without pre-splitting. Uses `\@highLight` (setter form) and `\LuaULResetUnderline*` with a `\leavevmode\par` trick.

| Experiment | What it tests | Result |
|-----------|---------------|--------|
| `e4-lua-environment/` | Environment spanning paragraphs, sections, sequential, and single-para | PASS (0.7pt extra spacing) |

## Key Findings

1. **Pandoc strips `data-` prefix** from HTML attributes unless the base name collides with a standard HTML attribute. Use `data-hl` (becomes `hl`), `data-colors` (becomes `colors`). Avoid `data-color` (stays `data-color`).

2. **Cross-block `<span>` is silently destroyed** by Pandoc's HTML parser. No error, no warning. Pre-splitting is mandatory.

3. **Pandoc auto-wraps highlighted headings** in `\texorpdfstring{<formatted>}{<plain>}` for PDF bookmark safety.

4. **`\underLine`/`\highLight` nesting order doesn't matter** to lua-ul. Both "underlines outside, highlights inside" and "interleaved" produce identical PDF output.

5. **Approach A (comma-separated) is strongly preferred** for overlapping highlights. The "one, two, many" stacking logic lives entirely in the Lua filter. The DOM walker just emits flat spans with `data-colors="yellow,cyan"`.

6. **The region model is reliable.** E7 exercised all stacking tiers (0, 1, 2, 3+) with 4 overlapping highlights crossing a heading boundary. 9 regions correctly identified, all rendered correctly.

7. **`\label{}` debris and `\texorpdfstring{}` are non-issues.** Labels are unwanted (can be stripped). `\texorpdfstring` is already handled by `_strip_texorpdfstring()` in the production pipeline, and the Lua filter approach eliminates it entirely.

8. **The environment approach cannot handle overlapping highlights.** LaTeX environments must nest properly. Overlapping highlights are structurally non-nesting. `\begin{hlenv}` is only viable for single-colour, non-overlapping use.
