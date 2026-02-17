# E5: Pre-split Span Proof

Proves that pre-split `<span>` elements survive Pandoc's HTML parser and can be
wrapped by a Lua filter. Also proves that cross-block `<span>` is silently destroyed.

## Files

- `e5_test1_presplit.html` - Valid HTML: 3 separate `<span>` elements, one per block
- `e5_test2_crossblock.html` - Invalid HTML: one `<span>` crossing block boundaries
- `e5_filter.lua` - Diagnostic Lua filter that dumps AST and wraps hl spans
- `e5_test1_stderr.txt` - AST dump showing 3 Span nodes detected
- `e5_test2_stderr.txt` - AST dump showing ZERO Span nodes (silent destruction)

## How to reproduce

```bash
# Test 1: Pre-split (works)
pandoc -f html -t latex --lua-filter=e5_filter.lua e5_test1_presplit.html 2>stderr.txt

# Test 2: Cross-block (silently destroyed)
pandoc -f html -t latex --lua-filter=e5_filter.lua e5_test2_crossblock.html 2>stderr.txt
```

## Result

Test 1 output:
```latex
Some text \highLight[yellow]{highlighted text before heading}
\subsection{...}\highLight[yellow]{Grounds of Appeal}...
\highLight[yellow]{Mr Lawlis sought leave} to rely on three grounds.
```

Test 2 output: Zero `\highLight` commands. Text reorganised, attributes lost, no warning.
