---
source: https://pandoc.org/MANUAL.html
fetched: 2026-01-26
library: pandoc
summary: Template syntax for standalone document generation
---

# Pandoc Templates

## Overview

Templates enable custom document styling with `-s/--standalone` flag. View defaults with `pandoc -D FORMAT`. Custom templates via `--template FILE` or in `templates/default.FORMAT`.

## Template Syntax

### Variables

Delimiters: `$...$` or `${...}`. Variable names begin with letter, can contain letters, numbers, `_`, `-`, `.`.

```
$title$
${author.name}$
```

### Conditionals

```
$if(variable)$
content when variable is truthy
$endif$

$if(foo)$
true section
$else$
false section
$endif$
```

### For Loops

```
$for(items)$
$it$
$sep$, $endfor$
```

Array values iterate with `variable` set to each value. Use `sep` for delimiters between items.

### Partials

Subtemplates: `${ filename() }` for modular templates.

## Key LaTeX Variables

Pass via `-V KEY=VALUE` or in YAML metadata.

### Preamble/Structure

- `header-includes`: Custom LaTeX in preamble (packages, commands)
- `include-before-body`: After `\begin{document}`
- `include-after-body`: Before `\end{document}`

### Page Layout

- `geometry`: Page dimensions/margins (passed to geometry package)
- `papersize`: e.g., `a4`, `letter`
- `fontsize`: e.g., `11pt`, `12pt`
- `linestretch`: Line spacing multiplier

### Document Class

- `documentclass`: Default `article`, can be `report`, `book`, `memoir`, etc.
- `classoption`: Additional class options

## Workflow

1. Export default: `pandoc -D latex > custom.latex`
2. Modify as needed
3. Apply: `pandoc --template custom.latex input.md -o output.pdf`

## Example: Adding Custom Packages

```bash
pandoc -s input.html -o output.pdf \
  -V header-includes='\usepackage{longtable}' \
  -V geometry='margin=1in'
```

Or in YAML metadata block:

```yaml
---
header-includes:
  - \usepackage{longtable}
  - \usepackage{booktabs}
geometry: margin=1in
---
```
