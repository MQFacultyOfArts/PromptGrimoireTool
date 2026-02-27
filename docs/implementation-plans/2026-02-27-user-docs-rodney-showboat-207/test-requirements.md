# Test Requirements — user-docs-rodney-showboat-207

## Test Strategy

This feature has two distinct categories of verification:

1. **Automated unit tests** for the Python orchestrator (`make_docs()` in `cli.py`). These mock external dependencies (Rodney, Showboat, subprocess, server lifecycle) to verify orchestration logic — dependency checking, server start/stop, error reporting. Test file: `tests/unit/test_make_docs.py`.

2. **Operational/human verification** for the bash guide scripts and PDF output. The guide scripts are bash driving external CLI tools (Rodney, Showboat) against a live NiceGUI server — they have no unit tests. Verification requires running `uv run make-docs` and inspecting the output. PDF quality criteria (AC2.5, AC3.4) explicitly require human judgement.

The `.gitignore` entries (AC4.2, AC4.3) can be verified with a simple automated check, but since they are static file contents rather than runtime behaviour, they are verified operationally during implementation.

---

## Acceptance Criteria Mapping

### AC1: CLI entry point works end-to-end

| Criterion | ID | Verification | Type | File / Approach | Description |
|---|---|---|---|---|---|
| Server starts with mock auth on free port | AC1.1 | Automated | Unit | `tests/unit/test_make_docs.py` | Mock `_start_e2e_server`; assert it is called with a port and `DEV__AUTH_MOCK=true` is set in the environment |
| Server stopped after scripts complete (even on failure) | AC1.2 | Automated | Unit | `tests/unit/test_make_docs.py` | Mock a script that raises an error; assert `_stop_e2e_server` is still called |
| Both PDFs produced in `docs/guides/` | AC1.3 | Operational | — | Run `uv run make-docs`; verify `docs/guides/instructor-setup.pdf` and `docs/guides/student-workflow.pdf` exist and are non-empty |
| Missing Rodney exits with clear error | AC1.4 | Automated | Unit | `tests/unit/test_make_docs.py` | Mock `shutil.which("rodney")` returning `None`; assert exit with error mentioning "rodney"; assert `_start_e2e_server` NOT called |
| Missing Showboat exits with clear error | AC1.5 | Automated | Unit | `tests/unit/test_make_docs.py` | Mock `shutil.which("showboat")` returning `None`; assert exit with error mentioning "showboat"; assert `_start_e2e_server` NOT called |
| Script failure identifies the failing step | AC1.6 | Automated | Unit | `tests/unit/test_make_docs.py` | Mock `subprocess.run` to return non-zero exit code with stderr containing `wait_for` context message; assert `make_docs` prints the script name, exit code, and context message |

**Phase 1** implements AC1.1, AC1.2, AC1.4, AC1.5 tests. **Phase 4** adds AC1.6 test.

### AC2: Instructor guide is complete and accurate

| Criterion | ID | Verification | Type | Approach |
|---|---|---|---|---|
| Creates unit, week, activity from empty DB | AC2.1 | Operational | — | Run `uv run make-docs`; open `instructor-setup.pdf`; verify screenshots show unit creation form, unit detail page, week creation, activity creation |
| Tag configuration documented with screenshots | AC2.2 | Operational | — | Verify PDF contains a screenshot of the tag management dialog with at least one group and tags configured |
| Enrollment instruction included | AC2.3 | Operational | — | Verify PDF contains text instructing the instructor to provide student email list to admin |
| Student view verified via re-authentication | AC2.4 | Operational | — | Verify PDF contains a screenshot of the student navigator showing the activity visible after enrollment |
| Readable by unfamiliar instructor | AC2.5 | **Human** | UAT | See human verification section below |

### AC3: Student guide is complete and accurate

| Criterion | ID | Verification | Type | Approach |
|---|---|---|---|---|
| Covers all 9 workflow steps | AC3.1 | Operational | — | Run `uv run make-docs`; open `student-workflow.pdf`; verify sections exist for: login, navigate, create workspace, paste, annotate, comment, organise, respond, export |
| Workspace inherits tags from activity | AC3.2 | Operational | — | Verify workspace creation screenshot (step 3) shows annotation page with tag configuration inherited from the instructor's activity |
| Each step has a screenshot | AC3.3 | Operational | — | Count screenshots in PDF; verify at least 9 (one per step) |
| Usable as class handout | AC3.4 | **Human** | UAT | See human verification section below |

### AC4: Pipeline is re-runnable

| Criterion | ID | Verification | Type | Approach |
|---|---|---|---|---|
| Running twice produces valid PDFs | AC4.1 | Operational | — | Run `uv run make-docs` twice in succession; verify both PDFs are produced each time with expected sections and screenshots (content equivalence, not byte identity) |
| Generated artefacts are gitignored | AC4.2 | Operational | — | After running `uv run make-docs`, run `git status`; verify no `.md`, `.pdf`, or `screenshots/` files appear as untracked |
| Only `docs/guides/scripts/` is committed | AC4.3 | Operational | — | Run `git status`; verify only files under `docs/guides/scripts/` are tracked; no generated artefacts in the index |

---

## Automated Tests Detail

All automated tests live in `tests/unit/test_make_docs.py`. They mock external dependencies to isolate orchestration logic.

### Mocked dependencies

- `shutil.which` — controls whether Rodney/Showboat are "installed"
- `promptgrimoire.cli._pre_test_db_cleanup` — skips real DB operations
- `promptgrimoire.cli._start_e2e_server` — returns a mock process
- `promptgrimoire.cli._stop_e2e_server` — verifies cleanup
- `subprocess.run` — controls script and Rodney start/stop outcomes

### Test inventory

| Test | AC | Description |
|---|---|---|
| `test_make_docs_starts_server_with_mock_auth` | AC1.1 | Verifies `_start_e2e_server` called with port; `DEV__AUTH_MOCK=true` in env |
| `test_make_docs_stops_server_on_script_failure` | AC1.2 | Raises error in script subprocess; asserts `_stop_e2e_server` called in finally |
| `test_make_docs_exits_if_rodney_missing` | AC1.4 | `shutil.which("rodney")` returns `None`; asserts SystemExit with "rodney" in output; server never started |
| `test_make_docs_exits_if_showboat_missing` | AC1.5 | `shutil.which("showboat")` returns `None`; asserts SystemExit with "showboat" in output; server never started |
| `test_make_docs_rodney_start_stop_lifecycle` | AC1.2 | Verifies `rodney start --local` called after server starts; `rodney stop --local` called in finally block even on failure |
| `test_make_docs_error_reports_script_name_and_context` | AC1.6 | Subprocess returns exit code 1 with stderr "FAILED waiting for: Create unit form"; asserts output includes script name, exit code, and context message |

---

## Human Verification Items

These criteria require human judgement and cannot be meaningfully automated. They are UAT gates.

### AC2.5 — Instructor guide readability

**What to check:**
1. Open `docs/guides/instructor-setup.pdf`
2. Read through the guide as if you were an instructor unfamiliar with PromptGrimoire
3. Verify:
   - The guide reads as coherent instructor instructions, not developer notes
   - Each step logically follows from the previous one
   - Screenshots match the text instructions they accompany
   - Technical terminology is explained or avoided
   - No placeholder text, broken images, or rendering artefacts
   - Tag configuration screenshot (step 5) clearly shows the tag management interface
   - Student verification screenshot (step 7) shows the enrolled student's navigator

**Why it cannot be automated:** "Readable standalone by an instructor unfamiliar with the tool" is a subjective quality criterion. Automated checks can verify that screenshots and text exist, but not that they form a coherent, useful instructional document.

### AC3.4 — Student guide usability as class handout

**What to check:**
1. Open `docs/guides/student-workflow.pdf`
2. Read through the guide as if you were a student seeing PromptGrimoire for the first time
3. Verify:
   - Language is task-oriented ("Click Start", "Select text", "Switch to the Organise tab")
   - No developer jargon (no references to NiceGUI, WebSocket, DOM, CRDT, etc.)
   - Steps follow logical student workflow order
   - Screenshots match the text instructions they accompany
   - Each screenshot shows meaningful UI state (not blank pages or error screens)
   - The paste step (step 4) shows realistic conversation content
   - The export step (step 9) shows evidence of successful PDF generation
   - No placeholder text, broken images, or rendering artefacts
   - Suitable for printing as a class handout (readable layout, reasonable page count)

**Why it cannot be automated:** "Usable as a class handout" requires evaluating prose clarity, logical flow, visual layout, and pedagogical appropriateness. These are human judgement calls.

---

## Operational Verification Checklist

Run these after implementation is complete (post Phase 4). These are not automated tests but structured manual checks.

```bash
# 1. Run the pipeline
uv run make-docs

# 2. Verify both PDFs exist and are non-empty (AC1.3)
ls -la docs/guides/instructor-setup.pdf docs/guides/student-workflow.pdf

# 3. Verify gitignore works (AC4.2, AC4.3)
git status
# Expected: no .md, .pdf, or screenshots/ files appear as untracked

# 4. Run again to verify re-runnability (AC4.1)
uv run make-docs
ls -la docs/guides/instructor-setup.pdf docs/guides/student-workflow.pdf

# 5. Verify error reporting (AC1.6) — temporarily break a testid in a script
# Edit generate-instructor-setup.sh, change a data-testid to a nonexistent value
# Run uv run make-docs — verify output names the failing script and the wait context
# Revert the edit

# 6. Open PDFs for human review (AC2.5, AC3.4)
# See human verification sections above
```
