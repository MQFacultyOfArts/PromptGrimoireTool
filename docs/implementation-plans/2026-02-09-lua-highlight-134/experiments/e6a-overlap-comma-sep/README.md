# E6A: Overlapping Highlights — Comma-Separated Attributes (RECOMMENDED)

Tests the "one, two, many" stacking model with all logic in the Lua filter.
The DOM walker emits flat spans: `<span data-hl="1,2" data-colors="yellow,cyan">`.
The Lua filter parses the comma-separated values and generates nested wrapping.

## Files

- `e6a_doc.tex` - Generated LaTeX with all stacking tiers
- `e6a_doc.pdf` - Compiled PDF verified with mutool

## Stacking output

**1 highlight:**
```latex
\underLine[color=yellow!70!black, height=1pt, bottom=-3pt]{
  \highLight[yellow]{One highlight only. }}
```

**2 highlights (overlap):**
```latex
\underLine[color=yellow!70!black, height=2pt, bottom=-5pt]{
  \underLine[color=cyan!70!black, height=1pt, bottom=-3pt]{
    \highLight[yellow]{\highLight[cyan]{Two highlights overlap. }}}}
```

**3 highlights ("many"):**
```latex
\underLine[color=many-dark, height=4pt, bottom=-5pt]{
  \highLight[yellow]{\highLight[cyan]{\highLight[pink]{Three overlap. }}}}
```

## Why this approach wins

1. DOM walker is simple: flat spans, no nesting, just lists active highlights
2. "One, two, many" logic lives in ONE place (the Lua filter)
3. Heading-safe: Pandoc wraps in `\texorpdfstring{}` automatically
4. Adding new stacking tiers = change only the Lua filter
