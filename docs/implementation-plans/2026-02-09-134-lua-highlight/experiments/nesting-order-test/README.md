# Nesting Order Test

Proves that `\underLine` and `\highLight` nesting order doesn't matter to lua-ul.
Both "underlines outside, highlights inside" and "underlines interleaved with highlights"
produce pixel-identical PDF output.

## Files

- `nesting_test.tex` - Two test cases: grouped vs interleaved nesting
- `nesting_test.pdf` - Compiled output

## Test cases

**Test 1 (underlines grouped outside):**
```latex
\underLine[...2pt...]{\underLine[...1pt...]{\highLight[yellow]{\highLight[cyan]{text}}}}
```

**Test 2 (underlines interleaved):**
```latex
\underLine[...2pt...]{\highLight[yellow]{\underLine[...1pt...]{\highLight[cyan]{text}}}}
```

## Result

Identical highlight rectangles and underline bars in mutool trace output.
lua-ul renders based on accumulated attributes, not nesting order.

This means Approach A's grouped nesting (all underlines outside, all highlights inside)
and Approach B's interleaved nesting are visually equivalent.
