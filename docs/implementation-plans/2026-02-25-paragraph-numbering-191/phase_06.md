# Paragraph Numbering Implementation Plan — Phase 6: PDF Export Integration

**Goal:** Paragraph numbers appear in PDF export margin notes.

**Architecture:** Pass the document's `paragraph_map` (with string→int key conversion) as `word_to_legal_para` to the existing export pipeline. The pipeline already consumes this parameter — currently receives `None`.

**Tech Stack:** Export pipeline (`highlight_spans.py`), LaTeX margin notes

**Scope:** Phase 6 of 7 from original design

**Codebase verified:** 2026-02-27

---

## Acceptance Criteria Coverage

This phase implements and tests:

### paragraph-numbering-191.AC6: PDF export includes paragraph references
- **paragraph-numbering-191.AC6.1 Success:** PDF margin notes show `[N]` for annotations on numbered paragraphs
- **paragraph-numbering-191.AC6.2 Success:** Both auto-numbered and source-numbered documents produce correct PDF output

---

## Reference Files

The executor MUST read these before implementing:
- `src/promptgrimoire/pages/annotation/pdf_export.py` — `_handle_pdf_export()` (~line 88), call site (~line 154)
- `src/promptgrimoire/export/highlight_spans.py` — `compute_highlight_spans()` (~line 458), `_build_span_tag()` (~line 243)
- `tests/unit/export/test_highlight_spans.py` — existing tests (~line 464) showing `word_to_legal_para` usage
- `CLAUDE.md` — testing conventions

---

<!-- START_TASK_1 -->
### Task 1: Pass paragraph_map to export pipeline

**Verifies:** paragraph-numbering-191.AC6.1, AC6.2

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/pdf_export.py` (~line 154-162)

**Implementation:**

In `_handle_pdf_export()`, the document is already loaded at ~line 116 as `doc`. Change the `export_annotation_pdf()` call to pass the paragraph map with key conversion:

```python
# Convert string keys (from JSON) to int keys (expected by export pipeline)
legal_para_map: dict[int, int | None] | None = (
    {int(k): v for k, v in doc.paragraph_map.items()}
    if doc.paragraph_map
    else None
)

pdf_path = await export_annotation_pdf(
    html_content=html_content,
    highlights=highlights,
    tag_colours=state.tag_colours(),
    general_notes="",
    notes_latex=notes_latex,
    word_to_legal_para=legal_para_map,  # Was None
    filename=f"workspace_{workspace_id}",
)
```

**Key details:**
- `doc.paragraph_map` returns `dict[str, int]` from PostgreSQL JSON (string keys)
- Export pipeline expects `dict[int, int | None]` (int keys)
- Conversion: `{int(k): v for k, v in ...}` at the boundary
- Empty map `{}` → pass `None` (export pipeline handles `None` as "no paragraph numbers")

**Verification:**
```bash
uvx ty check
```

**Commit:** `feat: pass paragraph map to PDF export pipeline`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Unit tests for PDF export with paragraph numbers

**Verifies:** paragraph-numbering-191.AC6.1, AC6.2

**Files:**
- Modify: `tests/unit/export/test_highlight_spans.py` (add to existing tests)

**Testing:**

Add tests that verify `compute_highlight_spans()` produces correct `para_ref` values when `word_to_legal_para` is provided:

- AC6.1: HTML with a highlight at char offset 10, `word_to_legal_para={0: 1, 10: 2, 20: 3}` → output LaTeX contains `[2]` in the margin note for that highlight
- AC6.2: Test with both auto-numbered (sequential 1,2,3) and source-numbered (1,2,5,6 gaps) maps → both produce correct `[N]` references
- Test with `word_to_legal_para=None` → no para_ref in output (existing behavior preserved)
- Test with highlight on unnumbered offset → no para_ref

Follow the existing test patterns in the file (see ~line 464 for the existing `word_to_legal_para` test).

**Verification:**
```bash
uv run pytest tests/unit/export/test_highlight_spans.py -v -k "para"
```
Expected: All tests pass.

**Commit:** `test: add PDF export tests for paragraph number margin notes`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Unit test for key conversion at export call site

**Verifies:** paragraph-numbering-191.AC6.1, AC6.2

**Files:**
- Create: `tests/unit/export/test_pdf_export_para_map.py`

**Testing:**

The critical logic in Task 1 is the string→int key conversion at the call site boundary. Test this conversion independently:

- Input `{"0": 1, "50": 2, "120": 3}` (what `doc.paragraph_map` returns) → output `{0: 1, 50: 2, 120: 3}` (what export pipeline expects)
- Empty map `{}` → `None` (export pipeline treats `None` as "no paragraph numbers")
- Verify all output keys are `int`, all values are `int`

This is a pure data transformation test — no DB or app context needed.

**Verification:**
```bash
uv run pytest tests/unit/export/test_pdf_export_para_map.py -v
```

**Commit:** `test: add key conversion test for PDF export paragraph map`
<!-- END_TASK_3 -->

---

## UAT Steps

1. [ ] Run unit tests: `uv run pytest tests/unit/export/test_highlight_spans.py -v -k "para"` — all pass
2. [ ] Run key conversion tests: `uv run pytest tests/unit/export/test_pdf_export_para_map.py -v` — all pass
3. [ ] Type check clean: `uvx ty check`
4. [ ] Start the app: `uv run python -m promptgrimoire`
5. [ ] Open a workspace with a numbered document and some highlights
6. [ ] Export as PDF — verify paragraph references `[N]` appear in margin notes alongside highlight annotations (AC6.1)
7. [ ] Export an AustLII document (source-numbered) — verify source numbers appear correctly in PDF (AC6.2)

## Evidence Required
- [ ] Unit test output for paragraph export tests all green
- [ ] Key conversion test output green
- [ ] Sample PDF export showing `[N]` margin notes
