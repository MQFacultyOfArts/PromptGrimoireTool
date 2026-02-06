# WIP: Speaker Labels Not Showing in Claude Fixtures

## Status: Root Cause Identified, Fix Not Implemented

Date: 2026-02-05

## Problem

Speaker labels ("User:", "Assistant:") are not appearing in chatbot fixtures (claude_cooking, claude_maths) despite CSS and preprocessing being in place.

## Root Cause

Found in `src/promptgrimoire/input_pipeline/html_input.py`:

The `_remove_empty_elements()` function (lines 507-546) removes **all empty divs**, including the speaker marker divs injected by `preprocess_for_export()`.

The speaker markers are injected as:
```html
<div data-speaker="user" class="speaker-turn"></div>
```

These are **intentionally empty** - they're marker elements styled with CSS `::before` pseudo-elements. But `_remove_empty_elements()` treats them as garbage whitespace divs.

### Evidence

```python
# Step-by-step trace of data-speaker count:
1. Original: 0
2. After preprocess_for_export(): 99  # <-- markers injected
3. After _strip_heavy_attributes(): 99  # <-- preserved correctly
4. After _remove_empty_elements(): 0  # <-- BUG: all removed!
```

## Fix Required

Modify `_remove_empty_elements()` to preserve elements with `data-speaker` attribute:

```python
# Around line 524, before the text check:
for node in tree.css("p, div, span"):
    # Preserve speaker markers (intentionally empty)
    if node.attributes.get("data-speaker"):
        continue

    # Get text content (strips HTML)
    text = (node.text() or "").strip()
    # ... rest of function
```

## Fixtures Evaluated So Far

| Fixture | Status | Notes |
|---------|--------|-------|
| austlii | PASS | Legal doc, no speaker labels needed |
| chinese_wikipedia | PASS | Article, CJK renders correctly |
| claude_cooking | BLOCKED | Speaker labels missing |
| claude_maths | BLOCKED | Speaker labels missing |
| translation_* | NOT EVALUATED | |
| openai_* | NOT EVALUATED | |
| google_* | NOT EVALUATED | |
| scienceos_* | NOT EVALUATED | |

## Files to Modify

1. `src/promptgrimoire/input_pipeline/html_input.py` - Fix `_remove_empty_elements()`
2. After fix, regenerate screenshots: `uv run pytest tests/e2e/test_fixture_screenshots.py -v`
3. Continue ralph loop evaluation in `docs/wip/ralph-fixture-presentation.md`

## Related Files

- `docs/wip/ralph-fixture-presentation.md` - Main ralph loop evaluation checklist
- `tests/e2e/test_fixture_screenshots.py` - Screenshot generator
- `src/promptgrimoire/pages/annotation.py` - CSS for speaker labels (lines 172-196)
- `src/promptgrimoire/export/platforms/__init__.py` - Speaker marker injection (lines 154-169)
