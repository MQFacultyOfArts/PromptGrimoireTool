---
source: https://pandoc.org/lua-filters.html
fetched: 2026-01-26
library: pandoc
summary: Lua filter API for AST manipulation during conversion
---

# Pandoc Lua Filters

## Element Types and Field Access

Pandoc's AST consists of block and inline elements. Key block types:

- **Para**: Paragraph with `content` field containing Inlines
- **Div**: Generic block container with `content`, `attr`, `identifier`, `classes`, `attributes` fields
- **Table**: Complex structure with `attr`, `caption`, `colspecs`, `head`, `bodies`, `foot` fields
- **CodeBlock**: Has `text`, `attr`, `identifier`, `classes`, `attributes` fields

Inline elements (Str, Emph, Strong, Span, etc.) follow similar patterns with `content` and optional `attr` fields.

## Attribute Access and Modification

Elements with attributes expose three convenient aliases:

- `identifier`: Direct access to `attr.identifier`
- `classes`: List of element classes via `attr.classes`
- `attributes`: Key-value pairs accessed via `attr.attributes`

```lua
local span = pandoc.Span('text', {id = 'text', class = 'a b'})
span.attr = {id = 'text', class = 'a b', other_attribute = '1'}
```

## RawBlock and RawInline for Custom LaTeX

Create raw LaTeX content:

```lua
pandoc.RawBlock('latex', '\\hfill\\break{\\centering')
pandoc.RawInline('latex', '\\par}')
```

These elements preserve format-specific code that bypasses normal processing.

## Table Element Structure

The **Table** type contains:

- `caption`: Caption object with `long` (Blocks) and `short` (Inlines) fields
- `colspecs`: List of ColSpec pairs—each pair contains alignment and optional width
- `head`: TableHead with rows
- `bodies`: List of TableBody objects
- `foot`: TableFoot with rows

**Cell** structure:

- `contents`: Block content
- `alignment`: Individual cell alignment
- `col_span`, `row_span`: Dimensions
- `attr`: Cell attributes (including HTML width attribute)

**ColSpec** is a pair: `{alignment, width_fraction}` where width is optional.

## Traversing and Modifying AST

Use the `walk()` method:

```lua
return pandoc.Para('Hi'):walk {
  Str = function (_) return 'Bye' end,
}
```

Document-level traversal order controlled by `traverse` field: `'topdown'` or `'typewise'` (default).

Special filter functions for sequences:

- `Inlines(inlines)`: Called on all inline lists
- `Blocks(blocks)`: Called on all block lists

Return `nil` to leave unchanged, a matching element to replace, or a list to splice.

## Examples

### Reading HTML width attributes

```lua
function Table(tbl)
  for _, body in ipairs(tbl.bodies) do
    for _, row in ipairs(body.content) do
      for _, cell in ipairs(row.cells) do
        local width = cell.attr.attributes['width']
        if width then
          print("Cell width: " .. width)
        end
      end
    end
  end
  return tbl
end
```

### Modifying column widths

```lua
function Table(tbl)
  -- Set first column to 30%, second to 70%
  tbl.colspecs = {
    {pandoc.AlignDefault, 0.30},
    {pandoc.AlignDefault, 0.70}
  }
  return tbl
end
```

### Replacing LineBreak with LaTeX newline

```lua
function LineBreak()
  return pandoc.RawInline('latex', '\\newline{}')
end
```

### Handling Div margin-left

```lua
function Div(elem)
  local style = elem.attr.attributes['style']
  if style and style:match('margin%-left') then
    local margin = style:match('margin%-left:%s*([%d%.]+)in')
    if margin then
      local hspace = string.format('\\hspace{%sin}', margin)
      return {
        pandoc.RawBlock('latex', '\\noindent' .. hspace),
        elem
      }
    end
  end
  return elem
end
```

## Key Global Variables

- `FORMAT`: Target output format (e.g., `'html5'`, `'latex'`)
- `PANDOC_READER_OPTIONS`, `PANDOC_WRITER_OPTIONS`: Format configuration
- `PANDOC_VERSION`, `PANDOC_API_VERSION`: Version objects

## Important: Return Modified Elements

A filtered element will only be updated if the filter function returns a new element. Modifying in-place without returning has no effect.
