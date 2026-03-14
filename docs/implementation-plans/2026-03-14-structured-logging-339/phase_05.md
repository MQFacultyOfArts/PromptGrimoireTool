# Structured Logging Implementation Plan — Phase 5

**Goal:** Structured stage-progression events for the PDF export pipeline with timing, error extraction, and font tracking.

**Architecture:** Each export run gets a `uuid4()` `export_id`. Stage boundaries emit log events with `export_stage`, `stage_duration_ms`. LaTeX errors extracted from `.log` file on failure. `detect_scripts()` result logged as `font_fallbacks` on success.

**Tech Stack:** structlog, uuid4, time.monotonic, ast (for LaTeX log parsing)

**Scope:** 7 phases from original design (phases 1-7)

**Codebase verified:** 2026-03-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### structured-logging-339.AC3: Export pipeline instrumentation
- **structured-logging-339.AC3.1 Success:** Successful PDF export produces log events for each stage (`pandoc_convert`, `tex_generate`, `latex_compile`, `pdf_validate`) with `export_id`, `export_stage`, `stage_duration_ms`
- **structured-logging-339.AC3.2 Success:** All stage events for one export share the same `export_id` and `workspace_id`
- **structured-logging-339.AC3.3 Failure:** LaTeX compilation failure produces log event with `latex_errors` containing extracted `!`-prefixed lines (not the full log)
- **structured-logging-339.AC3.4 Success:** Successful export includes `font_fallbacks` field with `detect_scripts()` result

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Export stage timing and event logging

**Verifies:** structured-logging-339.AC3.1, structured-logging-339.AC3.2

**Files:**
- Modify: `src/promptgrimoire/export/pdf_export.py` (main export pipeline, ~518 lines)

**Implementation:**

Add structured logging at each stage boundary in `export_annotation_pdf()` (lines 436-517) and `generate_tex_only()` (lines 342-433).

1. Generate `export_id = str(uuid4())` at the entry point of `export_annotation_pdf()`.

2. Bind export context: `log = structlog.get_logger().bind(export_id=export_id)`.

3. Wrap each stage with timing. Create a helper context manager or use inline timing:

```python
import time

start = time.monotonic()
# ... stage work ...
duration_ms = round((time.monotonic() - start) * 1000)
log.info("export_stage_complete", export_stage="pandoc_convert", stage_duration_ms=duration_ms)
```

4. Instrument these stages:
   - **pandoc_convert**: Around `convert_html_with_annotations()` call (~line 314 area in the flow)
   - **tex_generate**: Around `generate_tex_only()` call (~line 500-512)
   - **latex_compile**: Around `compile_latex()` call (~line 515)
   - **pdf_validate**: The PDF existence and size check after compilation

5. The `workspace_id` is already bound via contextvars (Phase 3 binds it in `_handle_pdf_export()`), so it will appear automatically on all log lines.

**Testing:**

Tests must verify:
- structured-logging-339.AC3.1: Export produces log events with `export_id`, `export_stage`, `stage_duration_ms` for each of the 4 stages
- structured-logging-339.AC3.2: All stage events share the same `export_id`

Follow project testing patterns. Use existing export test fixtures (check `tests/unit/` and `tests/integration/` for export-related tests). The test should mock or control the export pipeline to produce log events, then verify log output.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/export/pdf_export.py && uvx ty check`
Expected: No lint or type errors

Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat: add export stage timing and event logging`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: LaTeX error extraction on failure

**Verifies:** structured-logging-339.AC3.3

**Files:**
- Modify: `src/promptgrimoire/export/pdf.py` (compile_latex function, lines 80-154)

**Implementation:**

When `compile_latex()` raises `LaTeXCompilationError`, extract `!`-prefixed error lines from the LaTeX log file.

In `compile_latex()`, before raising `LaTeXCompilationError`:

1. Read the log file content: `log_content = log_file.read_text(errors='replace')`
2. Extract error lines: `error_lines = [line.strip() for line in log_content.splitlines() if line.startswith('!')]`
3. Log the extracted errors:
   ```python
   logger.error("latex_compilation_failed",
       export_stage="latex_compile",
       latex_errors=error_lines,
       tex_path=str(tex_path),
       log_path=str(log_file),
   )
   ```
4. Still raise the `LaTeXCompilationError` — the log event is additional instrumentation, not a replacement for the exception.

Do NOT parse the log file on success — it can be multi-megabyte.

**Testing:**

Tests must verify:
- structured-logging-339.AC3.3: A LaTeX compilation failure produces a log event with `latex_errors` field containing a list of strings starting with `!`

Follow project testing patterns. Check for existing LaTeX test fixtures (look for `@pytest.mark.latex` tests).

**Verification:**

Run: `uv run ruff check src/promptgrimoire/export/pdf.py && uvx ty check`
Expected: No lint or type errors

Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat: extract LaTeX error lines on compilation failure`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Font fallback logging

**Verifies:** structured-logging-339.AC3.4

**Files:**
- Modify: `src/promptgrimoire/export/pdf_export.py` (in `generate_tex_only()` or `export_annotation_pdf()`)

**Implementation:**

After successful export, log the `detect_scripts()` result as `font_fallbacks`.

In `export_annotation_pdf()`, `detect_scripts()` is called indirectly via `build_annotation_preamble()` which calls `build_font_preamble(scripts)`. The scripts value is computed from the document content.

Find where `detect_scripts()` is called (in `preamble.py:102`) and capture its result. Then log:

```python
log.info("export_complete",
    export_stage="pdf_validate",
    font_fallbacks=sorted(scripts),  # frozenset → sorted list for JSON
)
```

Since `detect_scripts()` is called inside `build_annotation_preamble()`, you may need to either:
- Return the scripts from `build_annotation_preamble()` alongside the preamble text
- Or call `detect_scripts()` separately in `export_annotation_pdf()` on the document content

Choose whichever approach minimises changes to existing function signatures.

**Testing:**

Tests must verify:
- structured-logging-339.AC3.4: Successful export log event includes `font_fallbacks` field with the `detect_scripts()` result as a list

Follow project testing patterns. Task-implementor generates actual test code at execution time.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/export/ && uvx ty check`
Expected: No lint or type errors

Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat: log font fallback detection in export pipeline`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Capture LaTeX subprocess stdout/stderr into structured log

**Files:**
- Modify: `src/promptgrimoire/export/pdf.py` (compile_latex function, subprocess.run call)

**Implementation:**

The design explicitly requires capturing LaTeX subprocess stdout/stderr into structured log events rather than leaving them in PrivateTmp (where systemd isolation makes them inaccessible after process exit).

In `compile_latex()`, modify the `subprocess.run()` call to capture output:

```python
result = subprocess.run(
    cmd,
    capture_output=True,  # capture stdout and stderr
    text=True,
    timeout=120,
    cwd=output_dir,
)
```

On failure (non-zero return code or missing PDF):
1. Log the captured stderr and stdout as structured fields:
   ```python
   logger.error("latex_subprocess_output",
       export_stage="latex_compile",
       latex_stdout=result.stdout[-4096:] if result.stdout else "",  # last 4K chars
       latex_stderr=result.stderr[-4096:] if result.stderr else "",  # last 4K chars
       return_code=result.returncode,
   )
   ```
2. This captures output that would otherwise be lost to PrivateTmp isolation.

On success: optionally log stderr at DEBUG level (LaTeX warnings are common and verbose).

**Testing:**

Tests should verify that subprocess output is captured and appears in structured log events on failure.

Follow project testing patterns. Task-implementor generates actual test code at execution time.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/export/pdf.py && uvx ty check`
Expected: No lint or type errors

Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat: capture LaTeX subprocess output into structured log`

<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->

## UAT Steps

1. Start the app: `uv run run.py`
2. Navigate to an annotation workspace with content
3. Click Export PDF
4. After export completes, run: `jq 'select(.export_id != null)' logs/promptgrimoire.jsonl`
5. Verify: 4+ events with same `export_id`, each with `export_stage` and `stage_duration_ms`
6. Verify: Final event has `font_fallbacks` field
7. To test failure path: create a document with broken LaTeX content, trigger export
8. Verify: `jq 'select(.latex_errors != null)' logs/promptgrimoire.jsonl` shows extracted error lines
