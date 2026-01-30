---
source: https://lark-parser.readthedocs.io/en/latest/
fetched: 2026-01-28
library: lark
summary: Using Lark as a standalone lexer (tokenizer only, no parsing)
---

# Lark Lexer-Only Usage

## Installation

```bash
uv add lark
```

## Lexer-Only Mode

To use Lark as a pure lexer without parsing:

```python
from lark import Lark, Token

grammar = '''
    // Terminal definitions
    TRUE: "true"
    FALSE: "false"
    NUMBER: /[0-9]+/
'''

# parser=None + lexer='basic' = lexer-only mode
lexer = Lark(grammar, parser=None, lexer='basic')

# Tokenize text
for token in lexer.lex("true 42 false"):
    print(token.type, token.value)
```

## Token Attributes

The `Token` class has these attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `type` | `str` | Terminal name (e.g., 'NUMBER', 'TRUE') |
| `value` | `str` | The matched string value |
| `start_pos` | `int` | Starting byte position in input |
| `end_pos` | `int` | Ending byte position in input |
| `line` | `int` | Line number (1-indexed) |
| `column` | `int` | Column number (1-indexed) |
| `end_line` | `int` | Ending line number |
| `end_column` | `int` | Ending column number |

## Terminal Definition Syntax

```lark
// Literal string match
KEYWORD: "exact"

// Case-insensitive literal
SQL_SELECT: "select"i

// Regular expression
NUMBER: /[0-9]+/

// Character range (equivalent to regex)
DIGIT: "0".."9"

// Concatenation
DECIMAL: NUMBER "." NUMBER

// Alternation (use | in regex or multiple rules)
BOOL: "true" | "false"
```

## Terminal Priority

Higher priority terminals are matched first. Use `.N` suffix:

```lark
// DECIMAL (priority 2) matches before INTEGER (default priority 1)
INTEGER: /[0-9]+/
DECIMAL.2: /[0-9]+\.[0-9]+/
```

Literal strings automatically have higher priority than regex patterns.

## Handling Whitespace

```lark
// Import and ignore whitespace
%import common.WS
%ignore WS

// Or define custom whitespace handling
WS: /[ \t\n\r]+/
%ignore WS
```

## Catch-All Terminal

For a terminal that matches "everything else", use a low-priority regex:

```lark
// Specific markers (higher priority - literals)
HLSTART: "HLSTART{" /[0-9]+/ "}ENDHL"
HLEND: "HLEND{" /[0-9]+/ "}ENDHL"

// Catch-all with lowest priority
TEXT.0: /[^H]+|H(?!LSTART\{|LEND\{)/
```

**Note:** Lark's basic lexer requires all input to be consumed by some terminal. If no terminal matches, `UnexpectedCharacters` is raised.

## Common Imports

Lark provides common terminals:

```lark
%import common.INT           // Integer
%import common.SIGNED_NUMBER // Signed float/int
%import common.ESCAPED_STRING // Double-quoted string with escapes
%import common.WS            // Whitespace
%import common.NEWLINE       // Newline
%import common.CNAME         // C-style identifier
```

## Complete Lexer Example

```python
from lark import Lark, Token

GRAMMAR = r'''
    // Markers - literals have higher priority than regex
    HLSTART: "HLSTART{" /[0-9]+/ "}ENDHL"
    HLEND: "HLEND{" /[0-9]+/ "}ENDHL"
    ANNMARKER: "ANNMARKER{" /[0-9]+/ "}ENDMARKER"

    // Everything else - low priority catch-all
    // Matches any character that isn't the start of a marker
    TEXT: /(?:(?!HLSTART\{|HLEND\{|ANNMARKER\{).)+/s
'''

lexer = Lark(GRAMMAR, parser=None, lexer='basic')

text = "Hello HLSTART{1}ENDHL world HLEND{1}ENDHL!"
tokens = list(lexer.lex(text))

for t in tokens:
    print(f"{t.type}: {t.value!r} at {t.start_pos}-{t.end_pos}")
```

## Error Handling

```python
from lark.exceptions import UnexpectedCharacters

try:
    tokens = list(lexer.lex(text))
except UnexpectedCharacters as e:
    print(f"Unexpected character at line {e.line}, column {e.column}")
    print(f"Character: {e.char!r}")
```

## Important Notes

1. **Lexer 'basic' vs 'contextual'**: Use `lexer='basic'` for standalone lexing. The 'contextual' lexer requires a parser.

2. **All input must match**: Unlike some lexers, Lark requires every character to be consumed by some terminal. Use a catch-all TEXT terminal.

3. **Unicode**: Lark handles Unicode strings natively.

4. **Regex flags**: Use `/pattern/flags` syntax:
   - `/pattern/i` - case insensitive
   - `/pattern/s` - dot matches newline
   - `/pattern/m` - multiline mode

5. **Greedy matching**: Terminals match greedily by default.
