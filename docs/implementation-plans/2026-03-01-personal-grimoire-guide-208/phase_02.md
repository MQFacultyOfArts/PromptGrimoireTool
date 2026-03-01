# Personal Grimoire Guide Implementation Plan — Phase 2: Pipeline Integration and Tests

**Goal:** Register the personal grimoire guide in `make_docs()`, add MkDocs nav entry, refactor pandoc PDF generation to use glob discovery, and update tests.

**Architecture:** Extend the existing `make_docs()` pipeline to call the third guide after the student guide. Replace the hardcoded pandoc guide-name tuple with a glob over `docs/guides/*.md` so future guides are automatically discovered. Update `_mock_happy_path` fixture so mock guides create placeholder markdown files for glob discovery.

**Tech Stack:** Python 3.14, pytest, unittest.mock

**Scope:** Phase 2 of 2 from original design

**Codebase verified:** 2026-03-01

---

## Acceptance Criteria Coverage

This phase implements and tests:

### personal-grimoire-guide-208.AC5: Pipeline integration
- **personal-grimoire-guide-208.AC5.1 Success:** `make_docs()` calls the personal grimoire guide after the student guide
- **personal-grimoire-guide-208.AC5.2 Success:** MkDocs nav includes the guide as a third entry
- **personal-grimoire-guide-208.AC5.3 Success:** Pandoc generates a PDF for `your-personal-grimoire.md`

### personal-grimoire-guide-208.AC1: Guide produces structured output (pipeline verification)
- **personal-grimoire-guide-208.AC1.1 Success:** Guide produces `your-personal-grimoire.md` in `docs/guides/`

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add personal grimoire guide to make_docs() and refactor pandoc to glob

**Verifies:** personal-grimoire-guide-208.AC5.1, personal-grimoire-guide-208.AC5.3

**Files:**
- Modify: `src/promptgrimoire/cli.py:2596-2674` (make_docs function)

**Implementation:**

Two changes to `make_docs()`:

1. **Add import and call** for the personal grimoire guide after the student guide (line ~2610 for import, line ~2644 for call):

```python
# Add to imports at top of make_docs():
from promptgrimoire.docs.scripts.personal_grimoire import (
    run_personal_grimoire_guide,
)

# Add after run_student_guide(page, base_url) call:
run_personal_grimoire_guide(page, base_url)
```

2. **Replace hardcoded pandoc tuple with glob** (lines 2660-2674):

Replace:
```python
for guide_name in ("instructor-setup", "student-workflow"):
    md_path = guides_dir / f"{guide_name}.md"
    pdf_path = guides_dir / f"{guide_name}.pdf"
    subprocess.run(
        [
            "pandoc",
            "--pdf-engine=lualatex",
            f"--resource-path={guides_dir}",
            "-o",
            str(pdf_path),
            str(md_path),
        ],
        check=True,
    )
```

With:
```python
for md_path in sorted(guides_dir.glob("*.md")):
    pdf_path = md_path.with_suffix(".pdf")
    subprocess.run(
        [
            "pandoc",
            "--pdf-engine=lualatex",
            f"--resource-path={guides_dir}",
            "-o",
            str(pdf_path),
            str(md_path),
        ],
        check=True,
    )
```

Using `sorted()` ensures deterministic ordering (alphabetical by filename).

**Verification:**

Run: `uv run ruff check src/promptgrimoire/cli.py`
Expected: No lint errors

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add personal grimoire guide to make_docs pipeline and glob PDFs`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add MkDocs nav entry

**Verifies:** personal-grimoire-guide-208.AC5.2

**Files:**
- Modify: `mkdocs.yml:9-12` (nav section)

**Implementation:**

Add the third nav entry after "Student Workflow":

```yaml
nav:
  - Home: index.md
  - Instructor Setup: instructor-setup.md
  - Student Workflow: student-workflow.md
  - Your Personal Grimoire: your-personal-grimoire.md
```

**Verification:**

Visual inspection — the nav section should have 4 entries.

**Commit:** `docs: add personal grimoire guide to MkDocs nav`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Update _mock_happy_path fixture for three guides and glob-based pandoc

**Verifies:** (infrastructure — enables Task 4 tests)

**Files:**
- Modify: `tests/unit/test_make_docs.py:16-58` (_mock_happy_path fixture)

**Implementation:**

Two changes to the fixture:

1. **Add mock for the personal grimoire guide import** (alongside existing instructor and student mocks):

```python
patch(
    "promptgrimoire.docs.scripts.personal_grimoire.run_personal_grimoire_guide"
) as mock_personal,
```

2. **Make all three guide mocks create placeholder `.md` files** so the glob in `make_docs()` discovers them for pandoc PDF generation. Use `side_effect` that creates the markdown file in the actual `docs/guides/` directory relative to `cli.py`:

```python
import promptgrimoire.cli as cli_module

# Compute the guides dir that make_docs() will use.
# cli_module.__file__ = "src/promptgrimoire/cli.py"
# .parents[0] = src/promptgrimoire/
# .parents[1] = src/
# .parents[2] = project root
# This must match make_docs()'s own: Path(__file__).resolve().parents[2]
_guides_dir = Path(cli_module.__file__).resolve().parents[2] / "docs" / "guides"

def _create_guide_md(name: str):
    def _side_effect(*_args, **_kwargs):
        _guides_dir.mkdir(parents=True, exist_ok=True)
        (_guides_dir / f"{name}.md").write_text(f"# {name}\n")
    return _side_effect

mock_instructor.side_effect = _create_guide_md("instructor-setup")
mock_student.side_effect = _create_guide_md("student-workflow")
mock_personal.side_effect = _create_guide_md("your-personal-grimoire")
```

3. **Add `"personal"` to the yielded dict:**

```python
yield {
    "start": mock_start,
    "stop": mock_stop,
    "process": mock_process,
    "page": mock_page,
    "browser": mock_browser,
    "pw": mock_pw,
    "sync_pw": mock_sync_pw,
    "instructor": mock_instructor,
    "student": mock_student,
    "personal": mock_personal,
    "subprocess_run": mock_subprocess_run,
}
```

4. **Clean up created files after test** — add teardown after `yield`:

```python
yield { ... }
# Cleanup: remove placeholder markdown files
for name in ("instructor-setup", "student-workflow", "your-personal-grimoire"):
    (_guides_dir / f"{name}.md").unlink(missing_ok=True)
```

**Note on `test_produces_output_files`:** This test overrides the instructor mock's `side_effect` to write files to `tmp_path`, not `_guides_dir`. After the glob refactor, the pandoc loop uses `sorted(guides_dir.glob("*.md"))` which scans the real filesystem. In this test:
- The instructor's overridden side_effect writes to `tmp_path` — the glob will NOT find `instructor-setup.md` in `_guides_dir`
- The student and personal mocks retain the fixture's default side_effects — the glob WILL find `student-workflow.md` and `your-personal-grimoire.md` in `_guides_dir`
- Pandoc is called for 2 files (student + personal), not 3 — this is acceptable because `test_produces_output_files` tests guide output production, not pandoc call count
- The test's assertions (`md_file.exists()`, `screenshot.exists()`) check `tmp_path` and continue to pass
- No changes are needed to this test

**Verification:**

Run: `uv run pytest tests/unit/test_make_docs.py -x`
Expected: All existing tests still pass

**Commit:** `test: update _mock_happy_path fixture for three guides with glob`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add tests for personal grimoire guide integration

**Verifies:** personal-grimoire-guide-208.AC5.1, personal-grimoire-guide-208.AC5.3, personal-grimoire-guide-208.AC1.1

**Files:**
- Modify: `tests/unit/test_make_docs.py` (add new test class and update existing tests)

**Implementation:**

**Update existing tests:**

1. **`TestMakeDocsServerLifecycle.test_both_guides_called_with_page_and_base_url`** — rename to `test_all_guides_called_with_page_and_base_url` and add assertions for the personal grimoire guide:

```python
mocks["personal"].assert_called_once()
page_arg, base_url_arg = mocks["personal"].call_args[0]
assert page_arg is mocks["page"]
assert base_url_arg.startswith("http://localhost:")
```

2. **`TestMakeDocsGuideOrder.test_instructor_runs_before_student`** — rename to `test_guide_execution_order` and extend to verify three-guide ordering:

```python
def _record_personal(*_args, **_kwargs):
    call_order.append("personal")

mocks["personal"].side_effect = _record_personal
# ... (keep existing instructor and student recording)

cli_module.make_docs()

assert call_order == ["instructor", "student", "personal"]
```

Note: the recording side_effects here override the fixture's default side_effects (which create markdown files in `_guides_dir`). This means the glob in the pandoc section will find zero `.md` files during this test, so pandoc is called zero times. This is acceptable because:
1. This test only checks guide call ordering, not pandoc behaviour
2. The pandoc call count is tested separately in `test_pandoc_called_for_each_guide`
3. `subprocess.run` is mocked anyway, so no actual pandoc invocation occurs

The same applies to `test_mkdocs_build_runs_after_guides` below — recording side_effects override the file-creating defaults, and the test only checks ordering.

3. **`TestMakeDocsPandocPdf.test_pandoc_called_for_each_guide`** — update from 2 to 3 pandoc calls, add `your-personal-grimoire.md` check:

```python
assert len(pandoc_calls) == 3

input_files = [c[0][0][-1] for c in pandoc_calls]
assert any("instructor-setup.md" in f for f in input_files)
assert any("student-workflow.md" in f for f in input_files)
assert any("your-personal-grimoire.md" in f for f in input_files)
```

4. **`TestMakeDocsMkdocsBuild.test_mkdocs_build_runs_after_guides`** — extend call_order to include personal guide:

```python
def _record_personal(*_args, **_kwargs):
    call_order.append("personal")

mocks["personal"].side_effect = _record_personal

# ... run make_docs ...

assert call_order.index("personal") < mkdocs_idx
```

**Testing:**

Tests must verify each AC listed above:
- personal-grimoire-guide-208.AC5.1: Call order test verifies personal guide called third (after student)
- personal-grimoire-guide-208.AC5.3: Pandoc test verifies PDF generated for `your-personal-grimoire.md`
- personal-grimoire-guide-208.AC1.1: Guide arguments test verifies correct `page` and `base_url` passed

Follow project testing patterns. Task-implementor generates actual test code at execution time.

**Verification:**

Run: `uv run pytest tests/unit/test_make_docs.py -x -v`
Expected: All tests pass (existing + updated)

Run: `uv run test-all`
Expected: Full test suite passes

**Commit:** `test: verify personal grimoire guide pipeline integration`

<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
