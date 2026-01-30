---
source: https://ctan.org/pkg/lua-ul, https://github.com/zauguin/luaul
fetched: 2026-01-28
library: lua-ul
summary: LuaLaTeX package for underlines, strikethrough, and highlighting
---

# Lua-UL LaTeX Package Reference

Lua-UL provides underlining, strikethrough, and highlighting for LuaLaTeX without breaking ligatures, kerning, or restricting input.

## Requirements

- LuaTeX >= 1.12.0
- `luacolor` package (for `\highLight` colour support)

## Basic Commands

### `\underLine`

**Syntax:** `\underLine[options]{text}`

**Options (keyval format):**
| Option | Description |
|--------|-------------|
| `color` | Underline colour (xcolor syntax) |
| `textcolor` | Use current text colour (default, no value needed) |
| `height` | Line thickness |
| `top` | Height of upper edge |
| `bottom` | Height of lower edge |

**Constraint:** At most two of {top, bottom, height} should be set.

**Examples:**
```latex
\underLine{default underline}
\underLine[color=red]{red underline}
\underLine[color=blue, height=1pt]{thick blue underline}
\underLine[color=green, height=2pt, bottom=-3pt]{green with bottom offset}
```

### `\highLight`

**Syntax:** `\highLight[color]{text}`

**Options:**
- `[color]` - Optional colour specification (defaults to yellow)

**Examples:**
```latex
\highLight{yellow highlight}
\highLight[green]{green highlight}
\highLight[cyan!30]{light cyan highlight}
```

### `\strikeThrough`

**Syntax:** `\strikeThrough{text}`

Draws a line through the text at approximately half x-height.

## Colour Specification

Colours use xcolor syntax:
- Named colours: `red`, `blue`, `green`
- Custom defined: `\definecolor{mycolor}{HTML}{1f77b4}` then `mycolor`
- Mixed colours: `red!50!blue` (50% red, 50% blue)
- Tints: `blue!30` (30% blue, 70% white)

## Nesting Commands

Commands can be nested:

```latex
\highLight[yellow]{\underLine[color=red]{nested text}}
```

For multiple underlines at different heights (stacking effect):

```latex
\underLine[color=red, height=2pt, bottom=-3pt]{%
  \underLine[color=blue, height=1pt, bottom=-3pt]{stacked underlines}}
```

## Custom Commands with `\newunderlinetype`

For advanced customization:

```latex
\newunderlinetype\myUnderline{%
  \leaders\hbox{...}\hfill
}
```

## Integration Notes for PromptGrimoire

For nested highlights with stacked underlines showing overlap count:

```latex
% 1 highlight: single 1pt underline
\highLight[tag-alpha-light]{%
  \underLine[color=tag-alpha-dark, height=1pt, bottom=-3pt]{text}}

% 2 highlights: stacked 2pt + 1pt underlines
\highLight[tag-alpha-light]{\highLight[tag-beta-light]{%
  \underLine[color=tag-alpha-dark, height=2pt, bottom=-3pt]{%
    \underLine[color=tag-beta-dark, height=1pt, bottom=-3pt]{text}}}}

% 3+ highlights: single 4pt "many" underline
\highLight[tag-alpha-light]{\highLight[tag-beta-light]{\highLight[tag-gamma-light]{%
  \underLine[color=many-dark, height=4pt, bottom=-5pt]{text}}}}
```

Colour definitions needed:
```latex
\definecolor{many-dark}{HTML}{333333}
\colorlet{tag-alpha-dark}{tag-alpha!70!black}  % or explicit dark colour
```
