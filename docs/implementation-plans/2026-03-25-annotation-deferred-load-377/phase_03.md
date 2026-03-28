# Annotation Deferred Load — Phase 3: setLevel Cleanup

**Goal:** Remove all 41 `logging.getLogger(__name__).setLevel()` calls from `src/promptgrimoire/` and add a guard test to prevent reintroduction. These calls suppress structlog output and are redundant — structlog's level filtering is configured globally.

**Architecture:** Mechanical one-line removal per file. Guard test via AST scanning (matches existing pattern from `test_print_usage_guard.py`).

**Tech Stack:** Python AST module for guard test, structlog.

**Scope:** Phase 3 of 4 from original design.

**Codebase verified:** 2026-03-25

**Note:** The design plan assigns "Cache `list_documents()` result on PageState" to Phase 3. This was moved to Phase 2 Task 3 in the implementation plan because the documents cache is a natural part of the deferred loading restructure. Phase 3 focuses solely on the setLevel cleanup.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### annotation-deferred-load-377.AC4: setLevel cleanup
- **annotation-deferred-load-377.AC4.1:** No `logging.getLogger(__name__).setLevel()` calls remain in `src/promptgrimoire/` (guard test)
- **annotation-deferred-load-377.AC4.2:** `logger.debug()` calls in annotation modules produce output when structlog is configured at DEBUG level

---

## Reference Files

The task-implementor should read these files for context:

- **Guard test pattern:** `tests/unit/test_print_usage_guard.py` (AST scanning, allowlist, violation reporting)
- **Logging docs:** `docs/logging.md` (structlog configuration, level filtering)
- **Testing patterns:** `docs/testing.md`, `CLAUDE.md` (lines 47-102)

---

<!-- START_TASK_1 -->
### Task 1: Remove setLevel calls from all 41 files

**Verifies:** annotation-deferred-load-377.AC4.1

**Files:**
- Modify: 41 files across `src/promptgrimoire/` (see list below)

**Implementation:**

Remove the `logging.getLogger(__name__).setLevel(logging.INFO)` or `logging.getLogger(__name__).setLevel(logging.WARNING)` line from each file. In many files, this also makes the `import logging` unused — remove that import too if no other `logging.` usage remains in the file. The `structlog.get_logger()` import and `logger = structlog.get_logger()` line must remain.

**Files with `setLevel(logging.INFO)` (36 files):**

1. `src/promptgrimoire/docs/seed.py:24`
2. `src/promptgrimoire/llm/client.py:15`
3. `src/promptgrimoire/word_count.py:37`
4. `src/promptgrimoire/config.py:22`
5. `src/promptgrimoire/deadline_worker.py:21`
6. `src/promptgrimoire/ui_helpers.py:24`
7. `src/promptgrimoire/cli/e2e/_parallel.py:44`
8. `src/promptgrimoire/search_worker.py:20`
9. `src/promptgrimoire/input_pipeline/converters.py:20`
10. `src/promptgrimoire/input_pipeline/html_input.py:45`
11. `src/promptgrimoire/auth/client.py:28`
12. `src/promptgrimoire/pages/logviewer.py:24`
13. `src/promptgrimoire/export/pandoc.py:34`
14. `src/promptgrimoire/pages/courses.py:81`
15. `src/promptgrimoire/pages/auth.py:26`
16. `src/promptgrimoire/export/pdf_export.py:34`
17. `src/promptgrimoire/pages/highlight_api_demo.py:29`
18. `src/promptgrimoire/export/worker.py:34`
19. `src/promptgrimoire/pages/milkdown_spike.py:33`
20. `src/promptgrimoire/export/highlight_spans.py:49`
21. `src/promptgrimoire/pages/navigator/_search.py:32`
22. `src/promptgrimoire/export/platforms/__init__.py:31`
23. `src/promptgrimoire/pages/annotation/document_management.py:42`
24. `src/promptgrimoire/pages/annotation/sharing.py:26`
25. `src/promptgrimoire/pages/annotation/broadcast.py:38`
26. `src/promptgrimoire/pages/registry.py:22`
27. `src/promptgrimoire/pages/navigator/_cards.py:36`
28. `src/promptgrimoire/pages/annotation/tag_quick_create.py:26`
29. `src/promptgrimoire/pages/annotation/paste_handler.py:36`
30. `src/promptgrimoire/pages/annotation/pdf_export.py:54`
31. `src/promptgrimoire/pages/annotation/header.py:38`
32. `src/promptgrimoire/pages/annotation/tag_management_save.py:25`
33. `src/promptgrimoire/pages/annotation/respond.py:44`
34. `src/promptgrimoire/pages/roleplay.py:41`
35. `src/promptgrimoire/pages/annotation/upload_handler.py:34`
36. `src/promptgrimoire/pages/annotation/organise.py:41`

**Files with `setLevel(logging.WARNING)` (5 files):**

37. `src/promptgrimoire/db/tags.py:35`
38. `src/promptgrimoire/db/wargames.py:53`
39. `src/promptgrimoire/db/engine.py:32`
40. `src/promptgrimoire/crdt/persistence.py:21`
41. `src/promptgrimoire/crdt/annotation_doc.py:24`

**For each file:**
1. Remove the `logging.getLogger(__name__).setLevel(...)` line
2. Check if `import logging` is still used elsewhere in the file (search for other `logging.` usages)
3. If `import logging` is now unused, remove it
4. Verify the file still has `import structlog` and `logger = structlog.get_logger()`

**Verification:**
Run: `grep -r 'logging.getLogger(__name__).setLevel' src/promptgrimoire/ | wc -l`
Expected: `0`

Run: `uv run ruff check src/promptgrimoire/`
Expected: No errors (ruff will catch unused imports)

**Commit this in batches by directory:**

```
git commit -m "fix(logging): remove setLevel from db/ and crdt/ modules

Addresses #391, #359. structlog's global level config makes
per-module stdlib level overrides redundant and harmful."

git commit -m "fix(logging): remove setLevel from export/ modules"

git commit -m "fix(logging): remove setLevel from pages/ modules"

git commit -m "fix(logging): remove setLevel from remaining modules"
```

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add guard test to prevent setLevel reintroduction

**Verifies:** annotation-deferred-load-377.AC4.1

**Files:**
- Create: `tests/unit/test_setlevel_guard.py`
- Read (reference pattern): `tests/unit/test_print_usage_guard.py`

**Testing:**

Create an AST-based guard test that scans `src/promptgrimoire/` for `logging.getLogger(__name__).setLevel()` calls. Follow the pattern from `test_print_usage_guard.py`.

Tests must verify:
- **annotation-deferred-load-377.AC4.1:** No setLevel calls in `src/promptgrimoire/` — scan all `.py` files, parse AST, look for `ast.Call` nodes where the function is an attribute `setLevel` on a call to `logging.getLogger(__name__)`.
- The test should report violations with exact file path and line number.

**Pattern to detect (AST structure):**
```python
# This is what we're looking for in the AST:
logging.getLogger(__name__).setLevel(logging.INFO)
# Which is: Call(func=Attribute(value=Call(func=Attribute(value=Name('logging'), attr='getLogger')), attr='setLevel'))
```

**Verification:**
Run: `uv run grimoire test run tests/unit/test_setlevel_guard.py`
Expected: Test passes (no violations)

Then temporarily add `logging.getLogger(__name__).setLevel(logging.INFO)` to any file and re-run:
Expected: Test fails, reporting the violation with file:line

**Commit:** `test(logging): guard test prevents setLevel reintroduction`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify structlog debug output works

**Verifies:** annotation-deferred-load-377.AC4.2

**Files:**
- Create: `tests/unit/test_structlog_debug_output.py`
- Read (reference): `docs/logging.md`

**Testing:**

Verify that `logger.debug()` calls produce output through structlog even when the stdlib root logger is at a higher level. This confirms the setLevel removal was meaningful — the previous `setLevel(logging.INFO)` calls were suppressing debug output via the stdlib bridge.

- **annotation-deferred-load-377.AC4.2:** Configure structlog at DEBUG level. Also configure the stdlib root logger at WARNING (simulating what `setLevel(logging.WARNING)` previously did). Call `structlog.get_logger().debug("test message")`. Assert the message appears in captured output. This proves structlog's output bypasses stdlib level filtering when `setLevel()` is not applied to the module-level logger.

  **Why this isn't vacuous:** If `setLevel(logging.WARNING)` were still present on a module's stdlib logger, structlog's stdlib integration would honour the level gate and suppress debug messages. This test verifies the suppression is gone.

**Verification:**
Run: `uv run grimoire test run tests/unit/test_structlog_debug_output.py`
Expected: Test passes

**Commit:** `test(logging): verify debug output works after setLevel removal`

<!-- END_TASK_3 -->
