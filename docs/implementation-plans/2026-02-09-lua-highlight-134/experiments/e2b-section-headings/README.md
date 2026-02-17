# E2b: Real Section Headings

Pre-split highlight spans across `<h1>`, `<h2>`, `<h3>` producing real LaTeX
`\section{}`, `\subsection{}`, `\subsubsection{}` commands.

## Files

- `e2b_test.html` - Input: two highlights (yellow, cyan) crossing heading boundaries
- `e2b_filter.lua` - Simple Lua filter wrapping hl spans in `\highLight[color]{...}`
- `e2b_doc.tex` - Generated LaTeX showing `\texorpdfstring{}` wrapping
- `e2b_doc.pdf` - Compiled PDF with 3 yellow + 3 cyan highlight rectangles

## Key observation

Pandoc wraps highlighted heading content in `\texorpdfstring{}` automatically:
```latex
\subsection{\texorpdfstring{\highLight[yellow]{Highlighted
Heading}}{Highlighted Heading}}\label{highlighted-heading}
```

This means PDF bookmarks get plain text while the typeset heading gets the highlight.
No special handling needed in the Lua filter.

## How to reproduce

```bash
pandoc -f html -t latex --lua-filter=e2b_filter.lua e2b_test.html -o e2b_doc.tex
# Then wrap in document preamble and compile with lualatex
```

## Verification

```bash
mutool draw -F trace e2b_doc.pdf 2>/dev/null | grep 'fill_path.*color='
# Shows 3 yellow (0 0 1 0) + 3 cyan (1 0 0 0) rectangles
```
