# Plan: Fix Paragraph Number Formatting

## Problem
Paragraph references are formatted as `[start–end]` (e.g., `[1–3]`) but should be `[start]–[end]` (e.g., `[1]–[3]`).

## Change
Single file edit in [live_annotation_demo.py:760](src/promptgrimoire/pages/live_annotation_demo.py#L760):

**From:**
```python
para_ref = f"[{start_para}–{end_para}]"  # noqa: RUF001
```

**To:**
```python
para_ref = f"[{start_para}]–[{end_para}]"  # noqa: RUF001
```

## Verification
1. Run the live annotation demo
2. Create a highlight spanning multiple paragraphs
3. Confirm the annotation card shows `[1]–[3]` format instead of `[1–3]`
