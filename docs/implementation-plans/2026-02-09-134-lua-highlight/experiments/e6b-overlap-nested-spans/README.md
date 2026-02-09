# E6B: Overlapping Highlights — Nested HTML Spans (NOT RECOMMENDED)

Tests the alternative: one HTML `<span>` per highlight layer, physically nested.
The DOM walker must decide which span gets which underline mode.

## Files

- `e6b_doc.tex` - Generated LaTeX with interleaved nesting
- `e6b_doc.pdf` - Compiled PDF (renders identically to E6A)

## Why this approach loses

The LaTeX output is _functionally identical_ to E6A (confirmed by nesting-order-test),
but the complexity burden shifts to the DOM walker:

1. DOM walker must generate nested `<span>` elements (not flat)
2. DOM walker must assign `data-ul="outer2pt"` / `data-ul="inner1pt"` / `data-ul="many"` — duplicating the stacking logic
3. Two places to maintain stacking rules (DOM walker + Lua filter)
4. Harder to debug: must trace nested spans to understand state
