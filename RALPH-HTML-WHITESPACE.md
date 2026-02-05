# Ralph Loop: Fix HTML Paste Whitespace and Indent Issues

## Status: ✅ COMPLETE

All 6 E2E tests pass. Final measurements (2026-02-05):
- **Gap**: 24px (was 126px, target <100px) ✅
- **Indent**: 90px (was 0px, target 60-120px) ✅
- **Table layout**: 0px Y-diff (same row) ✅
- **Paragraph numbering**: 48 ✅

## Task

Fix the HTML paste processing so that:
1. **No excessive whitespace** between paragraphs (gap <100px between "Case Name" and "Medium Neutral Citation")
2. **Margin-left indent preserved** on "Ground 1" text (~60-120px indent from 2.38cm CSS)

## Verification Command

```bash
uv run pytest tests/e2e/test_html_paste_whitespace.py -v
```

**Success criteria:** All 6 tests pass. ✅ ACHIEVED

## Completion Promise

When all tests pass, output:
```
<promise>HTML WHITESPACE FIXED</promise>
```

## Context

### The Problem

When pasting LibreOffice HTML into the annotation page:
1. **Whitespace bug**: Empty `<p><br/></p>` elements create huge vertical gaps
2. **Indent bug**: `margin-left: 2.38cm` style is stripped, leaving no indent

### File Locations

**Main code to fix:**
- `src/promptgrimoire/pages/annotation.py` lines 1549-1786 (`_render_add_content_form`)
- The paste handler JavaScript that strips CSS

**Test file:**
- `tests/e2e/test_html_paste_whitespace.py`

**Test fixture:**
- `tests/fixtures/conversations/183-clipboard.html.html.gz` (LibreOffice HTML)

### Current Paste Handler Architecture

The paste handler in `annotation.py` does:
1. Intercepts paste event in QEditor
2. Creates hidden iframe, writes full HTML to it
3. Tries to capture computed styles (margin-left, margin-top, etc.) via `getComputedStyle()`
4. Strips `<style>`, `<script>`, `<img>` tags
5. Removes empty containers (`<p>`, `<div>`, `<td>`, etc. with no text)
6. Stores cleaned HTML in `window._pastedHtml_{id}`

### What's Broken

1. **Computed margins show 0px** - The iframe approach isn't capturing the actual computed margins from the LibreOffice stylesheet. The styles are defined in a `<style>` block:
   ```css
   p { margin-bottom: 0.25cm }
   p.western { font-family: "Arial" }
   ```
   But `getComputedStyle()` on elements returns 0px for margins.

2. **Empty element removal incomplete** - `<p><br/></p>` paragraphs used for spacing aren't being fully removed. The check `el.textContent?.trim()` might be truthy for `<br>` content.

### HTML Structure (from fixture)

```html
<style type="text/css">
    p { margin-bottom: 0.25cm }
    p.western { font-family: "Arial" }
</style>
...
<table>
  <tr><td><p class="western">Case Name:</p></td>
      <td><p class="western">Lawlis v R</p></td></tr>
</table>
<p class="western"><br/><br/></p>  <!-- spacing paragraph -->
...
<ol start="4">
  <li><p>Mr Lawlis sought leave...</p></li>
</ol>
<p style="margin-left: 2.38cm">Ground 1 – The sentencing judge erred...</p>
```

### Potential Fix Approaches

1. **For margins**: Instead of trying to capture computed styles, apply a default base margin (e.g., `margin-bottom: 0.5em`) to all `<p>` elements after stripping
2. **For indents**: Preserve `style` attributes that contain `margin-left` or `text-indent`
3. **For empty elements**: Check `el.innerHTML.replace(/<br\s*\/?>/gi, '').trim()` to properly detect BR-only content
4. **Alternative**: Don't strip inline styles at all - only strip class attributes and `<style>` blocks

### Test Measurements

From `tests/e2e/screenshots/`:
- `gap_measurement.txt`: "Vertical gap: 126px" (expected <100px)
- `ground1_indent_measurement.txt`: "Calculated indent: 0px" (expected 60-120px)

### What "Fixed" Looks Like

1. "Case Name" row and "Medium Neutral Citation" row have reasonable ~20-60px spacing
2. "Ground 1 – The sentencing judge erred..." text is indented ~90px from left edge
3. Paragraph numbering still works (4, 5, 6... up to 48)
4. Table layout still preserved (label and value on same row)

## What Was Fixed

### Commits (most recent first)
1. **bd04418** - `fix: normalize whitespace in char span injection to prevent hard line breaks`
   - Collapsed multiple spaces/newlines to single space in `inject_character_spans()`
2. **c4dfcf1** - `feat: add aggressive HTML stripping and size instrumentation`
   - Added more aggressive empty element removal
   - Added size logging for debugging websocket issues
3. **841ae08** - `feat: move char span injection to client-side (websocket size fix)`
   - Moved heavy processing to browser to avoid websocket payload limits
4. **ed618ad** - `fix(security): strip script/style tags from HTML input`
   - Security hardening of HTML input
5. **c7f0b61** - `feat(ui): integrate HTML input pipeline into annotation page`
   - Integrated the new pipeline into the paste handler
6. **ac9a9b3** - `feat(input): add HTML input pipeline with char span injection`
   - Core implementation of HTML sanitization + char span injection

### Key Changes
- **Whitespace normalization**: `inject_character_spans()` now normalizes `\s+` to single space
- **Empty element removal**: Aggressive stripping of `<p><br></p>` patterns
- **Style preservation**: `margin-left` inline styles preserved for indentation
- **Client-side processing**: Heavy char span injection moved to browser JS

## Iteration Notes

Each iteration:
1. Read current paste handler code
2. Identify what's causing the specific test failure
3. Make targeted fix
4. Run tests: `uv run pytest tests/e2e/test_html_paste_whitespace.py -v`
5. If tests fail, analyze output and iterate
6. When all 6 tests pass, output the promise

## Do NOT

- Create new unit tests (the E2E tests are the source of truth)
- Refactor unrelated code
- Change the test thresholds to make tests pass
- Skip or xfail the failing tests
