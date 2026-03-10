# PDF Export Filename Convention Implementation Plan

**Goal:** Implement the pure filename-policy module for PDF export stems, with deterministic parsing, sanitisation, fallback handling, and length budgeting.

**Architecture:** Add a new internal helper module at `src/promptgrimoire/export/filename.py` following the existing pure-helper pattern used by `latex_render.py`. The phase keeps all logic independent of NiceGUI and database state so later phases can call one tested seam for filename assembly.

**Tech Stack:** Python 3.14, `python-slugify` (default transliterator: `text-unidecode`), pytest

**Scope:** 4 phases from original design (phase 1 of 4)

**Codebase verified:** 2026-03-09

---

## Acceptance Criteria Coverage

This phase implements and tests:

### pdf-export-filename-271.AC2: Owner display names are parsed and normalised deterministically
- **pdf-export-filename-271.AC2.1 Success:** Two-token display name `Ada Lovelace` maps to `LastName=Lovelace` and `FirstName=Ada` before sanitisation and final filename assembly.
- **pdf-export-filename-271.AC2.2 Success:** Multi-token display name `Mary Jane Smith` uses the first token for `FirstName` and the last token for `LastName`; middle tokens are ignored for filename purposes.
- **pdf-export-filename-271.AC2.3 Edge:** Single-token display name `Plato` fills both name slots as `Plato_Plato` so the filename remains non-empty and deterministic without adding schema.
- **pdf-export-filename-271.AC2.4 Success:** Diacritics and non-ASCII Latin characters are transliterated, so `José Núñez` yields `Nunez_Jose`.
- **pdf-export-filename-271.AC2.5 Success:** Unsafe punctuation and path separators are replaced with underscores, repeated underscores are collapsed, and leading/trailing underscores are stripped from each segment.
- **pdf-export-filename-271.AC2.6 Edge:** Emoji and symbols with no useful transliteration are removed rather than leaked verbatim into the output filename.

### pdf-export-filename-271.AC3: Length budgeting and truncation are deterministic
- **pdf-export-filename-271.AC3.1 Success:** When the fully rendered filename is 100 characters or fewer, no truncation occurs.
- **pdf-export-filename-271.AC3.2 Success:** When the filename exceeds 100 characters, truncation is applied to `WorkspaceTitle` before any truncation is applied to `ActivityName`.
- **pdf-export-filename-271.AC3.3 Success:** `UnitCode`, `LastName`, `FirstName`, and `YYYYMMDD` are preserved during normal overflow handling.
- **pdf-export-filename-271.AC3.4 Success:** If trimming `WorkspaceTitle` to empty is still insufficient, `ActivityName` is trimmed next until the 100-character limit is met.
- **pdf-export-filename-271.AC3.5 Edge:** If trimming `WorkspaceTitle` and `ActivityName` to empty is still insufficient, `FirstName` is trimmed next until only a one-character initial remains.
- **pdf-export-filename-271.AC3.6 Edge:** `UnitCode`, `LastName`, and `YYYYMMDD` are never truncated. If the filename still exceeds 100 characters with empty `WorkspaceTitle` / `ActivityName` and a one-character `FirstName` initial, the export keeps that overlong filename rather than truncating those non-negotiable segments.
- **pdf-export-filename-271.AC3.7 Success:** The final returned filename always ends with `.pdf` and is at or under 100 characters except for the pathological overflow case in AC3.6.

---

<!-- START_TASK_1 -->
### Task 1: Declare `python-slugify` as a direct dependency

**Verifies:** None

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

**Step 1: Add the dependency**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-export-filename-271
uv add python-slugify
```

Rationale:
- `uv.lock` already contains `python-slugify` transitively, but this feature depends on it directly.
- Phase 1 must not rely on a transitive install that could disappear when unrelated dependencies change.
- `python-slugify` uses `text-unidecode` by default in this repo unless we explicitly change that stack later, so the Phase 1 tests must lock behaviour against the actual installed transliterator rather than an abstract “Unidecode or similar” idea.

**Step 2: Verify installation**

Run: `uv sync`
Expected: Environment resolves without changes beyond the new direct dependency.

Run:
```bash
uv run python -c "from slugify import slugify; print(slugify('José Núñez', separator='_', lowercase=False))"
```
Expected: `Jose_Nunez`

## UAT Steps
1. [ ] Run `uv sync` in the worktree.
2. [ ] Run the `slugify` one-liner above.
3. [ ] Verify the transliteration is ASCII-safe and import succeeds from the declared dependency.

## Evidence Required
- [ ] Terminal output showing `uv add` / `uv sync` succeeded
- [ ] Terminal output showing `Jose_Nunez`

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: declare python-slugify for pdf export filenames"
```
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: Create the pure filename-policy module and core parsing/sanitisation tests

**Verifies:** pdf-export-filename-271.AC2.1, pdf-export-filename-271.AC2.2, pdf-export-filename-271.AC2.3, pdf-export-filename-271.AC2.4, pdf-export-filename-271.AC2.5, pdf-export-filename-271.AC2.6

**Files:**
- Create: `src/promptgrimoire/export/filename.py`
- Create: `tests/unit/export/test_filename_policy.py` (unit)

**Implementation:**

Create `src/promptgrimoire/export/filename.py` with:

1. Module docstring explaining that this module builds safe PDF export stems with no DB or UI dependencies.
2. `from __future__ import annotations`
3. `PdfExportFilenameContext` dataclass with:
   - `course_code: str | None`
   - `activity_title: str | None`
   - `workspace_title: str | None`
   - `owner_display_name: str | None`
   - `export_date: date`
4. Internal constants for:
   - `_MAX_FILENAME_LENGTH = 100`
   - `_PDF_SUFFIX = ".pdf"`
   - fallback labels used by the builder (`Unplaced`, `Loose Work`, `Workspace`, `Unknown Unknown`)
5. A pure helper to split display names deterministically:
   ```python
   def _split_owner_display_name(display_name: str | None) -> tuple[str, str]:
       """Return (last_name, first_name) using first-token / last-token heuristic."""
   ```
   Required behaviour:
   - collapse repeated whitespace
   - blank / None -> `("Unknown", "Unknown")`
   - one token -> duplicate into both slots
   - multiple tokens -> first token is first name, last token is last name
6. A pure helper to sanitise one segment:
   ```python
   def _safe_segment(value: str) -> str:
       """ASCII-safe filename segment using python-slugify + underscore cleanup."""
   ```
   Required behaviour:
   - call `slugify(value, separator="_", lowercase=False)`
   - collapse repeated underscores with `re.sub(r"_+", "_", ...)`
   - strip leading/trailing underscores
   - return `""` if no useful transliteration remains
   - add a short inline comment explaining that the post-processing is intentional defense-in-depth even though `slugify(..., separator="_")` already normalises most separators
7. Do **not** export this module from `src/promptgrimoire/export/__init__.py` yet. Keep it internal until a later phase proves a public export is needed.

**Testing:**

Create `tests/unit/export/test_filename_policy.py` using the same class-based style as `tests/unit/export/test_latex_render.py`.

Tests must verify each AC listed above:
- `pdf-export-filename-271.AC2.1`: `Ada Lovelace` splits to last=`Lovelace`, first=`Ada`
- `pdf-export-filename-271.AC2.2`: `Mary Jane Smith` ignores middle tokens and yields `Smith`, `Mary`
- `pdf-export-filename-271.AC2.3`: `Plato` yields `Plato`, `Plato`
- `pdf-export-filename-271.AC2.4`: `José Núñez` sanitises to `Jose` / `Nunez`
- `pdf-export-filename-271.AC2.5`: punctuation, path separators, and repeated separators collapse to underscores with no leading/trailing underscore
- `pdf-export-filename-271.AC2.6`: emoji-only or symbol-only input sanitises to empty string under the actual `python-slugify` + `text-unidecode` stack in this environment

Include targeted test classes such as:
- `TestSplitOwnerDisplayName`
- `TestSafeSegment`

**Verification:**

Run: `uv run grimoire test all -- tests/unit/export/test_filename_policy.py -v`
Expected: All parsing and sanitisation tests pass.

Run: `uvx ty check src/promptgrimoire/export/filename.py tests/unit/export/test_filename_policy.py`
Expected: No type errors.

## UAT Steps
1. [ ] Run `uv run grimoire test all -- tests/unit/export/test_filename_policy.py -v`.
2. [ ] Run:
   ```bash
   uv run python - <<'PY'
   from datetime import date
   from promptgrimoire.export.filename import _safe_segment, _split_owner_display_name
   print(_split_owner_display_name("Mary Jane Smith"))
   print(_safe_segment("folder/name ::: draft"))
   PY
   ```
3. [ ] Verify the output shows `('Smith', 'Mary')` and a single-underscore-safe segment.

## Evidence Required
- [ ] Green pytest output for `tests/unit/export/test_filename_policy.py`
- [ ] `ty check` output with zero issues
- [ ] Python snippet output demonstrating the split and sanitisation behaviour

**Commit:** `feat: add pure filename parsing and sanitisation helpers`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add stem assembly, fallback labels, and deterministic length budgeting

**Verifies:** pdf-export-filename-271.AC3.1, pdf-export-filename-271.AC3.2, pdf-export-filename-271.AC3.3, pdf-export-filename-271.AC3.4, pdf-export-filename-271.AC3.5, pdf-export-filename-271.AC3.6, pdf-export-filename-271.AC3.7

**Files:**
- Modify: `src/promptgrimoire/export/filename.py`
- Modify: `tests/unit/export/test_filename_policy.py`

**Implementation:**

Add the public builder:

```python
def build_pdf_export_stem(ctx: PdfExportFilenameContext) -> str:
    """Return the export stem for a PDF filename."""
```

Required behaviour:

1. Resolve raw component values before sanitisation:
   - course code -> `ctx.course_code or "Unplaced"`
   - activity title -> `ctx.activity_title or "Loose Work"`
   - workspace title -> `ctx.workspace_title or "Workspace"`
   - owner display name -> `ctx.owner_display_name or "Unknown Unknown"`
2. Split the owner display name with `_split_owner_display_name`.
3. Sanitise every segment with `_safe_segment`.
4. If a sanitised fallback-bearing segment becomes empty, replace it with a safe fallback token:
   - course code -> `Unplaced`
   - activity title -> `Loose_Work`
   - workspace title -> `Workspace`
   - last name / first name -> `Unknown`
5. Format the date as `ctx.export_date.strftime("%Y%m%d")`.
6. Assemble the initial stem as:
   - `"{course}_{last}_{first}_{activity}_{workspace}_{date}"`
7. Enforce the 100-character final filename limit by budgeting against `f"{stem}.pdf"`:
   - if already within budget, return unchanged
   - trim `workspace` first
   - if still too long, trim `activity`
   - if still too long, trim `first` down to a one-character initial
   - keep `course`, `last`, and `date` intact even in pathological overflow handling
   - if the filename still exceeds 100 after `workspace` and `activity` are empty and `first` is reduced to one character, return the overlong filename unchanged rather than truncating `course`, `last`, or `date`
8. Implement trimming as deterministic right-truncation on the already-sanitised segment values.
9. Add a small internal helper if needed:
   ```python
   def _truncate_for_budget(
       course: str,
       last: str,
       first: str,
       activity: str,
       workspace: str,
       date_part: str,
   ) -> tuple[str, str, str]:
       """Return trimmed (first, activity, workspace) segments for the budget."""
   ```

**Testing:**

Extend `tests/unit/export/test_filename_policy.py` with a `TestBuildPdfExportStem` class.

Tests must verify each AC listed above:
- `pdf-export-filename-271.AC3.1`: a short, already-valid stem is returned unchanged
- `pdf-export-filename-271.AC3.2`: overlong filenames trim workspace before activity
- `pdf-export-filename-271.AC3.3`: unit code, last name, first name, and date stay intact while workspace/activity are trimmed
- `pdf-export-filename-271.AC3.4`: when workspace reaches empty budget, activity trimming begins next
- `pdf-export-filename-271.AC3.5`: when workspace/activity are exhausted, first name is reduced to a single-character initial before any non-negotiable segment is touched
- `pdf-export-filename-271.AC3.6`: if `course + last + first_initial + date` still cannot fit, the returned stem remains overlong rather than truncating the unit code, surname, or date
- `pdf-export-filename-271.AC3.7`: non-pathological cases still satisfy `len(f"{stem}.pdf") <= 100`

Also add explicit fallback tests for:
- blank workspace title -> `Workspace`
- blank owner display name -> `Unknown_Unknown`
- missing course/activity input to the builder -> `Unplaced` / `Loose_Work`

Also add explicit pathological-overflow tests for:
- a long first name that is reduced to a single-character initial after workspace/activity have already been exhausted
- an extreme last-name case where the final filename still exceeds 100 characters because surname/unit/date are non-negotiable, and that overlong output is preserved rather than silently truncating those segments

**Verification:**

Run: `uv run grimoire test all -- tests/unit/export/test_filename_policy.py -v`
Expected: All filename-policy tests pass, including the new budgeting cases.

Run:
```bash
uv run python - <<'PY'
from datetime import date
from promptgrimoire.export.filename import PdfExportFilenameContext, build_pdf_export_stem

ctx = PdfExportFilenameContext(
    course_code="LAWS5000",
    activity_title="A Very Long Activity Title That Should Eventually Be Trimmed",
    workspace_title="A Workspace Title That Is Even Longer And Should Be Trimmed First",
    owner_display_name="José Núñez",
    export_date=date(2026, 3, 9),
)
stem = build_pdf_export_stem(ctx)
print(stem)
print(len(f"{stem}.pdf"))
PY
```
Expected:
- Output stem starts with `LAWS5000_Nunez_Jose_`
- Printed length is `<= 100` for this non-pathological case

## UAT Steps
1. [ ] Run `uv run grimoire test all -- tests/unit/export/test_filename_policy.py -v`.
2. [ ] Run the Python snippet above.
3. [ ] Verify the stem keeps the unit code, surname, given name, and date while shortening workspace title before activity title.
4. [ ] Verify a pathological overlong-surname test preserves the surname rather than truncating it, even if the final filename exceeds 100 characters.

## Evidence Required
- [ ] Green pytest output covering `TestBuildPdfExportStem`
- [ ] Python snippet output showing the generated stem
- [ ] Printed final filename length at or under 100 for non-pathological cases
- [ ] Test output showing the pathological overlong-surname case preserves the non-negotiable core segments

**Commit:** `feat: add pdf export stem builder with truncation policy`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
