# E4: Lua Environment Approach (Fallback)

Custom `\begin{hlenv}[color]...\end{hlenv}` LaTeX environment that can span
paragraph breaks and section boundaries. Uses lua-ul's internal `\@highLight`
setter form rather than the braced `\highLight{...}` command.

## Files

- `e4_luaul_final.tex` - Complete test document with 4 test cases (A-D)
- `e4_luaul_final.pdf` - Compiled PDF, all tests clean

## Environment definition

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

## Why `\leavevmode\par` is required

lua-ul uses a `pre_append_to_vlist_filter` callback that processes each paragraph
as it enters the vertical list. When `\LuaULResetUnderline*` clears the attribute
register, the *next* paragraph has already started building with the old value.
`\leavevmode\par` creates a zero-height empty paragraph that gets processed by
the callback, absorbing the lingering attribute.

Without it, highlighting leaks exactly one paragraph past `\end{hlenv}`.

## Test matrix

| Test | Scenario | Result | Extra spacing |
|------|----------|--------|---------------|
| A | 3 paragraph breaks | CLEAN | 0.7pt |
| B | Section boundary crossing | CLEAN | 0.7pt |
| C | Sequential yellow + cyan | CLEAN | 0.7pt each |
| D | Single paragraph | CLEAN | 0.7pt |

## Limitation

Adds ~0.7pt extra vertical space at environment end due to the empty paragraph.
Acceptable for our use case but this is the tradeoff vs the pre-split approach.
