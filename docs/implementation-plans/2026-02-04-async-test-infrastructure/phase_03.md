## Phase 3: Remove Deprecated RTF Parser Tests

**Goal:** Remove tests for deprecated LibreOffice RTF conversion

**Components:**
- `tests/unit/test_rtf_parser.py` - delete entire file

**Done when:** RTF parser tests removed, `uv run test-all` passes

---

<!-- START_TASK_1 -->
### Task 1: Delete test_rtf_parser.py

**Files:**
- Delete: `tests/unit/test_rtf_parser.py`

**Step 1: Delete the file**

```bash
git rm tests/unit/test_rtf_parser.py
```

**Step 2: Run full test suite**

Run: `uv run test-all`
Expected: All tests pass (no skip messages for RTF parser tests)

**Step 3: Verify no subprocess.run in export pipeline**

Run: `grep -r "subprocess.run" src/promptgrimoire/export/latex.py`
Expected: No matches (Pandoc is now async)

**Step 4: Commit**

```bash
git commit -m "test: remove deprecated RTF parser tests (Issue #108)"
```
<!-- END_TASK_1 -->
