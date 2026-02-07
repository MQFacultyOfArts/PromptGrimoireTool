# PDF Export Implementation - Resume Point

## Current State (2026-01-26)

### Pipeline

```
RTF → HTML (LibreOffice) → LaTeX (Pandoc standalone) → PDF (latexmk/TinyTeX)
```

### What Works

1. **RTF to HTML**: LibreOffice headless conversion preserves structure
2. **Pandoc standalone**: Generates complete LaTeX document with all packages
3. **`<ol start="N">`**: Pandoc correctly generates `\setcounter{enumi}{N-1}`
4. **PDF compilation**: TinyTeX/latexmk produces 12-page PDF from test document
5. **Chat clipboard capture**: `scripts/save_chat.sh` captures HTML from browser clipboard

### What's Broken

See GitHub issues for details:

| Issue | Problem | Impact |
|-------|---------|--------|
| #73 | Table column widths not preserved | 50/50 split instead of original proportions |
| #74 | Table cells not wrapping | 1476pt overflow, `\vtop{\hbox{}}` from `<br/>` tags |
| #75 | CSS `margin-left` lost | Indented paragraphs render flush-left |
| #76 | No automated CSS fidelity tests | Manual inspection required |

### Key Decision

**Annotations are out of scope until baseline conversion works.**

### CSS Property Analysis

#### LibreOffice HTML (183.rtf) - 18 properties, simple

**Must preserve:**
- `margin-left` (0.94in, 0.42in, 0.08in)
- `margin-top`, `margin-bottom`
- `line-height` (100%, 110%, 115%, 150%)
- `page-break-after: avoid`
- `text-transform: uppercase`
- `border`, `border-top/bottom/left/right`
- `padding`, `padding-top/bottom/left/right`
- Table `width` attributes (HTML, not CSS)

**Lower priority:**
- `font-size` (11pt, 14pt)
- `background`

#### AI Chat Sources - VERY DIFFERENT

Captured samples from 5 sources via `scripts/save_chat.sh`:

| Source | Files | Size | CSS Nature |
|--------|-------|------|------------|
| OpenAI | 5 | 188KB-519KB | Tailwind + computed DOM |
| Claude | 2 | 340KB-3.4MB | Tailwind + computed DOM |
| AI Studio | 2 | 208KB-6.8MB | Angular Material |
| Gemini | 1 | 152KB | Material + computed |
| ScienceOS | 1 | 94KB | Mantine + computed |

**Key insight:** AI chat clipboard gives us **full DOM snapshots with computed styles**, including:
- UI chrome (sidebars, buttons, headers)
- 500+ CSS framework variables (Tailwind, Material, Mantine)
- Every browser-computed property

This is fundamentally different from LibreOffice's semantic HTML. Preserving ALL CSS from these sources is **unwise**.

#### Recommended Approach for AI Chats

1. Extract **message content only** (strip UI chrome)
2. Apply **consistent PDF styling** (not source styling)
3. Preserve only **structure**: paragraphs, lists, code blocks, headings

### Technical Findings

1. **Quarto is Pandoc under the hood** - No additional HTML processing for our use case
2. **Lua filters are the solution** - Need to translate CSS to LaTeX for LibreOffice HTML
3. **AI chats need pre-processing** - Extract content before Pandoc, don't try to preserve their CSS

## Files

```
src/promptgrimoire/export/
├── __init__.py
├── latex.py              # Current (annotation-focused, needs refactor)
├── pdf.py                # LaTeX → PDF via latexmk
└── filters/
    └── legal.lua         # Redundant - Pandoc already handles ol start

scripts/
├── save_chat.sh          # Capture clipboard HTML: ./scripts/save_chat.sh <name>
└── anonymise_chats.py    # Replace message content with labelled lorem ipsum

output/
├── 183_raw.html              # LibreOffice HTML output (49KB, clean)
├── 183_standalone.tex        # Pandoc standalone LaTeX
├── 183_standalone.pdf        # Current output (tables broken)
├── chat_openai_simple.html   # 188KB - German translation
├── chat_openai_shopping.html # 274KB
├── chat_openai_copyedit.html # 519KB
├── chat_openai_dh.html       # 390KB
├── chat_openai_codeblock.html# 311KB
├── chat_claude_cooking.html  # 3.4MB - Eggplant recipes (17 turns)
├── chat_claude_question.html # 340KB
├── chat_aistudio_character.html # 208KB - Ars Magica character
├── chat_aistudio_image.html  # 6.8MB - Contains images
├── chat_gemini_translate.html# 152KB - German translation
└── chat_scienceos_1.html     # 94KB - Rubber Hand Illusion
```

## ast-grep for HTML Analysis

### What Works

The ast-grep MCP server is functional. **Key finding:** Simple pattern syntax like `style="$S"` does NOT work for HTML attributes. Must use YAML rules with `kind` matching.

### HTML AST Structure

```
attribute
├── attribute_name        # e.g., "style"
├── =
└── quoted_attribute_value
    ├── "
    ├── attribute_value   # e.g., "margin-left: 0.5in"
    └── "
```

### Working YAML Rule for Style Attributes

```yaml
id: find-style-attrs
language: html
rule:
  kind: attribute
  has:
    kind: attribute_name
    regex: ^style$
```

### MCP Tool Usage

```python
# Dump AST to understand structure
mcp__ast-grep__dump_syntax_tree(
    code='<p style="margin-left: 0.5in">Hello</p>',
    language="html",
    format="cst"
)

# Test YAML rule before running on files
mcp__ast-grep__test_match_code_rule(
    code='<p style="margin-left: 0.5in">Hello</p>',
    yaml="""id: find-style-attrs
language: html
rule:
  kind: attribute
  has:
    kind: attribute_name
    regex: ^style$"""
)

# Run on project folder (WARNING: large files can cause connection timeout)
mcp__ast-grep__find_code_by_rule(
    project_folder="/path/to/output",
    yaml="...",
    max_results=20
)
```

### Caveat

Large HTML files (3MB+ chat captures) can cause MCP connection timeouts. Target specific files or use CLI directly for bulk analysis.

## Commands

```bash
# Generate HTML from RTF
uv run python -c "
from pathlib import Path
from promptgrimoire.parsers import parse_rtf
parsed = parse_rtf(Path('tests/fixtures/183.rtf'))
Path('output/183_raw.html').write_text(parsed.html)
"

# Capture AI chat from clipboard
./scripts/save_chat.sh openai_example  # → output/chat_openai_example.html

# Convert to standalone LaTeX
pandoc -s -f html -t latex output/183_raw.html -o output/183_standalone.tex

# Compile to PDF
PATH="$HOME/.TinyTeX/bin/x86_64-linux:$PATH"; cd output; latexmk -pdf 183_standalone.tex

# ast-grep CLI (pattern syntax doesn't work for HTML - use YAML rules instead)
uv run ast-grep scan --rule rule.yaml output/183_raw.html
```

## Next Steps

### For LibreOffice/RTF sources (#73, #74, #75):
1. Write Lua filter for table column widths from HTML `width` attributes
2. Fix `\vtop{\hbox{}}` → proper paragraph wrapping
3. Write Lua filter for `margin-left` → `\hspace{}` or indented environment
4. Add unit tests for CSS→LaTeX translation (#76)

### For AI chat sources:
1. ~~**First**: Decide on content extraction strategy~~ **DONE** - Extract semantic content, apply our own styling
2. ~~Build extractors per-source~~ **DONE** - Patterns documented, anonymise script working
3. ~~Create test fixtures~~ **DONE** - `scripts/anonymise_chats.py` creates labelled lorem ipsum versions
4. **Next**: Implement production extractors in `src/promptgrimoire/export/chat_extractors.py`
5. Build content cleaner (strip UI, preserve semantic HTML)
6. Apply consistent PDF template styling

### Decision (2026-01-26)

**Extract semantic content, apply our own PDF styling.** Don't preserve CSS from AI chats.

UAT: User wants to see RTF semantically preserved, plus authentic representations of chats (preserving markdown formatting: paragraphs, lists, code blocks, headings).

## AI Chat Extraction Patterns

Analysed all 11 samples. Each source has different DOM structure for messages.

### OpenAI (ChatGPT)

**Samples:** 5 files (openai_simple, openai_shopping, openai_copyedit, openai_dh, openai_codeblock)

| Element | Selector | Content Path |
|---------|----------|--------------|
| User message | `div[data-message-author-role="user"]` | `.whitespace-pre-wrap` or innermost div |
| Assistant message | `div[data-message-author-role="assistant"]` | div containing "markdown" class |
| Message ID | `data-message-id` attribute | UUID |

**Sample counts:** 9 user + 9 assistant in openai_simple

### Claude

**Samples:** 2 files (claude_cooking, claude_question)

| Element | Selector | Content Path |
|---------|----------|--------------|
| User message | `div[data-testid="user-message"]` | Direct text content |
| Assistant message | `div.font-claude-response` | Nested content (may have thinking blocks) |

**Sample counts:** 17 user + 36 response containers in claude_cooking

### Gemini

**Samples:** 1 file (gemini_translate)

| Element | Selector | Content Path |
|---------|----------|--------------|
| User message | `div[class*="user-query"]` | `.query-text` or `.query-content` |
| Assistant message | `div[class*="response-container"]` | Nested markdown content |

**Sample counts:** 2 user-query containers, 17 response-containers

### AI Studio (Google)

**Samples:** 2 files (aistudio_character, aistudio_image)

| Element | Selector | Content Path |
|---------|----------|--------------|
| User message | `div.chat-turn-container.user` | `ms-cmark-node > span.ng-star-inserted` |
| Assistant message | `div.chat-turn-container.model` | `ms-cmark-node > span.ng-star-inserted` |

**Note:** Uses Angular custom elements (`ms-cmark-node`) for CommonMark rendering.

**Sample counts:** 5 user + 6 model turns in aistudio_character

### ScienceOS

**Samples:** 1 file (scienceos_1)

| Element | Selector | Content Path |
|---------|----------|--------------|
| User message | div without `prose` class, containing conversation text | Direct span content |
| Assistant message | `div.prose:not(.not-prose)` | Standard prose/markdown rendering |

**Note:** Uses Mantine UI with hashed class names (m_*). Message role distinguished by presence/absence of `prose` class on content container.

**Sample counts:** 2 user + 2 assistant

### Anonymised Test Files

`scripts/anonymise_chats.py` replaces message content with labelled lorem ipsum for testing:

```bash
uv run python scripts/anonymise_chats.py
# Creates chat_*_anon.html files with labels like [OPENAI_SIMPLE-USER-1]
```

| Source | User | Asst | Status |
|--------|------|------|--------|
| OpenAI (5 files) | ✓ | ✓ | Full extraction |
| Claude (2 files) | ✓ | ✓ | Full extraction |
| Gemini | ✓ | Partial | Some empty response containers |
| AI Studio | ✓ | Partial | Content lazy-loaded, mostly empty |
| ScienceOS | ✓ | ✓ | Full extraction |

**Known limitation:** AI Studio and some Gemini turns have empty content due to browser lazy-loading. The clipboard capture gets the DOM structure but not all dynamic content.

### Extraction Implementation Plan

```python
# src/promptgrimoire/export/chat_extractors.py

from dataclasses import dataclass
from enum import Enum
from bs4 import BeautifulSoup

class Role(Enum):
    USER = "user"
    ASSISTANT = "assistant"

@dataclass
class Message:
    role: Role
    content: str  # Cleaned HTML or markdown
    source: str   # e.g., "openai", "claude"

class ChatExtractor:
    """Base class for chat extractors."""

    def extract(self, html: str) -> list[Message]:
        raise NotImplementedError

class OpenAIExtractor(ChatExtractor):
    def extract(self, html: str) -> list[Message]:
        soup = BeautifulSoup(html, 'html.parser')
        messages = []
        for msg in soup.find_all(attrs={'data-message-author-role': True}):
            role = Role(msg['data-message-author-role'])
            # Extract content based on role
            if role == Role.USER:
                content_div = msg.find(class_=lambda c: c and 'whitespace-pre-wrap' in c)
            else:
                content_div = msg.find(class_=lambda c: c and 'markdown' in c)
            if content_div:
                messages.append(Message(role, str(content_div), "openai"))
        return messages

# Similar extractors for Claude, Gemini, AI Studio, ScienceOS
```

### Content Cleaning Strategy

After extraction, each message's HTML needs cleaning:

1. **Strip UI elements**: buttons, icons, action menus
2. **Preserve semantic HTML**: `<p>`, `<ul>/<ol>/<li>`, `<pre>/<code>`, `<h1>-<h6>`, `<strong>/<em>`
3. **Remove inline styles**: All `style=""` attributes
4. **Remove framework classes**: Tailwind, Material, Mantine class names
5. **Normalise whitespace**: Collapse excessive line breaks

Output: Clean HTML suitable for Pandoc conversion to LaTeX.

## References

- Pandoc Lua filters: https://pandoc.org/lua-filters
- Pandoc templates: https://pandoc.org/MANUAL.html#templates
- TinyTeX: https://yihui.org/tinytex/
- GitHub issues: #66 (parent), #73, #74, #75, #76
