---
source: https://ctan.org/pkg/subfiles
fetched: 2026-02-12
library: subfiles
summary: LaTeX package for multi-file projects with standalone compilation
---

# subfiles Package Reference

**Version:** 2.2 (2020-11-14)
**Authors:** Federico Garcia-De Castro, Gernot Salzer
**License:** LPPL 1.3
**Repository:** https://github.com/gsalzer/subfiles

## Overview

The `subfiles` package enables multi-file LaTeX projects where each file can be
compiled both standalone and as part of a main document, without modifications.

## Core Syntax

### Main document

```latex
\documentclass{article}
\usepackage{subfiles}
% ... preamble ...

\begin{document}
\subfile{chapter1}        % includes content of chapter1.tex
\subfileinclude{chapter2} % like \include but for subfiles (adds \clearpage)
\end{document}
```

### Subfile

```latex
\documentclass[main.tex]{subfiles}
\begin{document}
Content here — inherits main.tex preamble when compiled standalone.
\end{document}
```

## How It Works

- **When compiled standalone:** The subfile loads `main.tex`'s preamble (everything
  before `\begin{document}`), then typesets the subfile's own content.
- **When included via `\subfile{}`:** Everything outside `\begin{document}` /
  `\end{document}` in the subfile is ignored. Only the body content is included.

## Key Commands

| Command | Behaviour |
|---------|-----------|
| `\subfile{file}` | Include subfile body inline |
| `\subfileinclude{file}` | Like `\include{}` — adds `\clearpage` before and after |
| `\subfix{path}` | Fix relative paths for graphics/imports in subfiles |

## Path Resolution

Paths in subfiles are relative to the *main document's directory* when included,
but relative to the *subfile's directory* when compiled standalone. When all files
are in the same directory (our case), this is not an issue.

For files in different directories, use `\subfix{}` or the `import` package.

## Compatibility

- Works with LuaLaTeX, pdfLaTeX, XeLaTeX
- Works with latexmk (tracks subfile dependencies automatically)
- No known issues with fontspec, lua-ul, or other LuaLaTeX packages

## Installation

```bash
# TinyTeX
tlmgr install subfiles

# Or via setup_latex.py (add to REQUIRED_PACKAGES list)
```

## Our Use Case

For test mega-documents: all `.tex` files in the same `tmp_path` directory.
Main document uses `\subfile{body_name}` to include each test section.
Each subfile uses `\documentclass[mega_test.tex]{subfiles}` so it can be
compiled independently for debugging if the mega-doc fails.
