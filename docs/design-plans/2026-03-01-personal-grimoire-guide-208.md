# "Your Personal Grimoire" Guide Design

**GitHub Issue:** #208

## Summary

PromptGrimoire allows users to annotate and reflect on AI conversations in collaborative workspaces. Most workspaces are created within a unit-and-activity structure set up by an instructor. This guide documents a complementary "loose" flow: a student who is enrolled in a unit *chooses* to create a personal workspace outside the activity structure — building their own analytical vocabulary from scratch rather than inheriting instructor-defined tags. The guide is the third entry in the `make_docs()` documentation pipeline and is produced as both a MkDocs web page and a Pandoc PDF.

The implementation follows the established guide-script pattern from `instructor_setup.py` and `student_workflow.py`: a Python script drives a Playwright browser through the live application using the Guide DSL, emitting narrative markdown and capturing annotated screenshots at each step. The script is structured around five sections that mirror the paper's pedagogical arc — entering the grimoire, importing a conversation, building an emergent tag vocabulary, annotating with reflection, and finally connecting the loose workspace to a course activity via the placement dialog. The guide depends on the instructor guide having already created the UNIT1234 unit (and will invoke it as a prerequisite if the unit is missing). The guide creates and enrols its own dedicated user account at startup.

## Definition of Done

A third guide script, "Your Personal Grimoire", runs within the existing `make_docs()` pipeline and produces markdown with ~11 annotated screenshots. The guide demonstrates the loose workspace flow: an enrolled student chooses to create a personal workspace outside the activity structure, pastes an AI conversation, builds their own tag vocabulary (emergent folksonomy), annotates and reflects, then connects the workspace to a course activity via the placement dialog. Narrative text grounds each step in the pedagogical framework from "Teaching the Unknown" (Ballsun-Stanton & Torrington, 2025). The guide appears in the MkDocs nav and Pandoc PDF output alongside the existing instructor and student guides.

## Acceptance Criteria

### personal-grimoire-guide-208.AC1: Guide produces structured output
- **personal-grimoire-guide-208.AC1.1 Success:** Guide produces `your-personal-grimoire.md` in `docs/guides/`
- **personal-grimoire-guide-208.AC1.2 Success:** Guide produces ~11 screenshots in `docs/guides/screenshots/` with prefix `your-personal-grimoire-`
- **personal-grimoire-guide-208.AC1.3 Success:** Markdown contains 5 section headings matching the pedagogical arc
- **personal-grimoire-guide-208.AC1.4 Success:** All screenshot image references in the markdown resolve to files that exist on disk

### personal-grimoire-guide-208.AC2: Loose workspace created by enrolled student
- **personal-grimoire-guide-208.AC2.1 Success:** Student is enrolled in UNIT1234 but navigates to `/annotation` and clicks `create-workspace-btn` (bypassing the activity Start button)
- **personal-grimoire-guide-208.AC2.2 Success:** Created workspace has `activity_id=NULL` and `course_id=NULL`
- **personal-grimoire-guide-208.AC2.3 Success:** Navigator shows the workspace in the "Unsorted" section alongside the enrolled unit's activities

### personal-grimoire-guide-208.AC3: Emergent folksonomy — student creates own tags
- **personal-grimoire-guide-208.AC3.1 Success:** Tag management dialog opens on a workspace with zero pre-existing tags
- **personal-grimoire-guide-208.AC3.2 Success:** Student creates a tag group ("My Analysis") and three tags via the tag management dialog
- **personal-grimoire-guide-208.AC3.3 Success:** Created tags appear in the tag toolbar and can be applied to highlights

### personal-grimoire-guide-208.AC4: Placement dialog associates workspace with unit
- **personal-grimoire-guide-208.AC4.1 Success:** Placement dialog opens from the placement chip on the annotation header
- **personal-grimoire-guide-208.AC4.2 Success:** Cascading selects (Unit → Week → Activity) populate with UNIT1234 data
- **personal-grimoire-guide-208.AC4.3 Success:** After confirming placement, workspace is associated with the selected activity
- **personal-grimoire-guide-208.AC4.4 Success:** Student's enrolment in UNIT1234 causes it to appear in the placement dialog (enrolment is a precondition, not an edge case)

### personal-grimoire-guide-208.AC5: Pipeline integration
- **personal-grimoire-guide-208.AC5.1 Success:** `make_docs()` calls the personal grimoire guide after the student guide
- **personal-grimoire-guide-208.AC5.2 Success:** MkDocs nav includes the guide as a third entry
- **personal-grimoire-guide-208.AC5.3 Success:** Pandoc generates a PDF for `your-personal-grimoire.md`

## Glossary

- **Grimoire**: The application's metaphor for a student's personal workspace or collection of workspaces — a private "book of workings" where AI conversations are stored, annotated, and reflected upon.
- **Loose workspace**: A workspace with `activity_id=NULL` and `course_id=NULL`. Created from the annotation page without being linked to any course activity; appears in the Navigator's "Unsorted" section.
- **Emergent folksonomy**: A tag vocabulary that a user builds from scratch to suit their own analytical needs, rather than inheriting tags defined by an instructor. Contrasted with the instructor-defined tag sets used in the enrolled student flow.
- **Placement dialog**: A UI dialog on the annotation page that allows a student to retroactively associate a loose workspace with a specific Unit, Week, and Activity via cascading select inputs.
- **Placement chip**: The UI element in the annotation header that opens the placement dialog when clicked.
- **Guide DSL**: A small internal Python library (`guide.py`, `screenshot.py`) that provides context managers for writing documentation scripts. It wraps Playwright browser automation and handles markdown emission and screenshot capture.
- **`make_docs()` pipeline**: The CLI entry point (`uv run make-docs`) that runs all guide scripts in sequence and assembles the documentation site. Guide scripts execute in a fixed order; later scripts may depend on state created by earlier ones.
- **UNIT1234**: The fictional unit (course) used as shared seed data across all three guide scripts. Created by the instructor guide; referenced by the student and personal grimoire guides.
- **Navigator**: The application's workspace-browsing page (route `/`), which groups workspaces by unit/week/activity and includes an "Unsorted" section for loose workspaces.
- **Locus of control**: Term from the pedagogical framework (Ballsun-Stanton & Torrington, 2025) describing whether a student treats AI as an external authority or as a tool they direct. The guide's narrative arc moves students toward internal (self-directed) locus of control.
- **QEditor**: NiceGUI's rich-text editor component, backed by a `contenteditable` div. Guide scripts inject HTML content into it via `page.evaluate()` because normal typing simulation is unreliable for rich text.
- **Subprocess helper**: A pattern used in guide scripts to call `manage-users` CLI subcommands via `subprocess.run()` to set up database state without going through the UI.

## Architecture

The guide follows the established pattern from `instructor_setup.py` and `student_workflow.py`: a single entry-point function (`run_personal_grimoire_guide(page, base_url)`) that uses the Guide DSL context managers to drive a Playwright browser through the application, emitting narrative markdown and capturing annotated screenshots.

The guide is structured around five pedagogical sections rather than numbered UI steps. Each section maps to a phase from the paper's learning framework:

1. **Enter the Grimoire** — enrolled student chooses to create a loose workspace outside the activity structure
2. **Bring Your Conversation** — importing an AI conversation artefact
3. **Make Meaning Through Tags** — emergent folksonomy (student-created tags)
4. **Annotate and Reflect** — highlighting, commenting, organising, responding
5. **Connect to Your Unit** — placement dialog to associate the loose workspace with a course activity

The guide runs third in the `make_docs()` pipeline, after instructor and student guides. It depends on the instructor guide having created the UNIT1234 unit. If UNIT1234 is not found (e.g. when running the guide independently), the guide invokes `run_instructor_guide()` as a prerequisite.

### Data dependencies

| Step | Requires | Created by |
|------|----------|-----------|
| Setup | User account `loose-student@test.example.edu.au` | Guide's own `_setup_loose_student()` helper |
| Setup | Student enrolled in UNIT1234 | Guide's own `_setup_loose_student()` helper |
| Setup | UNIT1234 unit with week and activity | Instructor guide (invoked as prerequisite if missing) |
| 1. Enter the Grimoire | Enrolled student, no loose workspace yet | Setup |
| 2-4. Paste, tags, annotate | Loose workspace | Created in step 1 |
| 5. Connect to Unit | UNIT1234 activity visible in placement dialog | Enrolment from setup |

### Sample content

AI conversation about cultural markers in Japanese legal text translation — consistent with the UNIT1234 domain used by the instructor and student guides. Different conversation from the student workflow guide to avoid duplication.

Student-created tags (emergent folksonomy):
- Tag group: "My Analysis"
- Tags: "AI Assumption", "Cultural Gap", "Useful Insight"

## Existing Patterns

Investigation found two existing guide scripts that establish the authoring pattern:

- `src/promptgrimoire/docs/scripts/instructor_setup.py` — 395 lines, 7 steps, uses subprocess helpers for DB seeding (`_seed_template_tags`, `_create_demo_student`), per-step functions to keep main under 50 statements
- `src/promptgrimoire/docs/scripts/student_workflow.py` — 328 lines, 9 steps, uses `page.evaluate()` for HTML injection into contenteditable, `select_chars()` helper for text selection

This design follows the same patterns:
- Module-level `GUIDE_OUTPUT_DIR = Path("docs/guides")`
- `_authenticate(page, base_url, email)` helper (duplicated per script, not shared — consistent with existing practice)
- Per-section functions: `def _section_NAME(page, base_url, guide) -> None`
- Subprocess calls for user management: `subprocess.run(["uv", "run", "manage-users", ...], capture_output=True, check=False)`
- `page.evaluate()` for HTML injection into QEditor contenteditable
- `Guide("Title", GUIDE_OUTPUT_DIR, page)` as top-level context manager

Data-testid attributes used by this guide that were missing and have been added:
- `create-workspace-btn` on the "Create Workspace" button (`annotation/__init__.py`, `annotation/workspace.py`)
- `quick-create-name-input`, `quick-create-group-select`, `quick-create-save-btn` on the tag quick-create dialog (`annotation/tag_quick_create.py`)
- `placement-confirm-btn` on the placement dialog confirm button (`annotation/placement.py`)

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Guide Script

**Goal:** Write the `personal_grimoire.py` guide script with all five pedagogical sections.

**Components:**
- `src/promptgrimoire/docs/scripts/personal_grimoire.py` — new file, ~350-400 lines
  - `run_personal_grimoire_guide(page, base_url)` — entry point
  - `_setup_loose_student()` — subprocess helper to create user account and enrol in UNIT1234
  - `_ensure_instructor_guide_ran(page, base_url)` — guard that checks for UNIT1234 and invokes `run_instructor_guide()` if missing
  - `_authenticate(page, base_url, email)` — mock auth helper
  - `_section_enter_grimoire(page, base_url, guide)` — login, Navigator showing enrolled unit, navigate to `/annotation`, create loose workspace
  - `_section_bring_conversation(page, guide)` — paste AI conversation, confirm content type
  - `_section_make_meaning(page, guide)` — create tag group "My Analysis", add 3 tags via tag management dialog
  - `_section_annotate_and_reflect(page, guide)` — highlight text, comment, organise tab, respond tab
  - `_section_connect_to_unit(page, guide)` — open placement dialog, select UNIT1234 activity, confirm
- Sample HTML content as module-level constant (`_SAMPLE_HTML`)

**Dependencies:** Existing Guide DSL (`guide.py`, `screenshot.py`), data-testid additions (already committed)

**Done when:** Script runs within `make_docs()` pipeline, produces `docs/guides/your-personal-grimoire.md` and ~11 screenshots in `docs/guides/screenshots/`
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Pipeline Integration and Tests

**Goal:** Register the guide in `make_docs()`, MkDocs nav, and update tests.

**Components:**
- `src/promptgrimoire/cli.py` — add import and call for `run_personal_grimoire_guide` after `run_student_guide`
- `mkdocs.yml` — add nav entry: `- Your Personal Grimoire: your-personal-grimoire.md`
- `tests/unit/test_make_docs.py` — update `_mock_happy_path` fixture to mock the new guide import, add test assertions for third guide call order and Pandoc PDF generation for 3 guides

**Dependencies:** Phase 1

**Done when:** All existing `test_make_docs.py` tests pass with the third guide added, new tests verify: (1) personal grimoire guide called after student guide, (2) personal grimoire guide called with correct `page` and `base_url` arguments, (3) Pandoc generates PDF for all three guides, (4) `make_docs()` end-to-end produces the expected output
<!-- END_PHASE_2 -->

## Additional Considerations

**Narrative tone:** The notes in this guide are longer than the other two guides. The instructor guide is procedural ("click this, fill that"). The student workflow guide is task-oriented ("paste your conversation, highlight text"). This guide is reflective — it explains *why* each action matters pedagogically, connecting to the grimoire concept, emergent folksonomy, and the shift from external to internal AI locus of control. This is by design, matching the paper's emphasis on process over product.

**Enrolled from the start:** The student is enrolled in UNIT1234 before the guide begins. They can see the unit and its activities on the Navigator. The guide's premise is that the student *chooses* to create a loose workspace instead of clicking Start on an activity — they want to explore independently, building their own analytical vocabulary. Section 5 closes the arc by connecting this personal work back to the course structure. The narrative should frame this choice explicitly: "Instead of starting from the activity, you create your own workspace."

**Prerequisite guard:** `_ensure_instructor_guide_ran(page, base_url)` checks whether UNIT1234 exists (e.g. by querying the Navigator or the DB). If missing, it invokes `run_instructor_guide(page, base_url)` to create the required state. This allows the guide to be run independently during development without requiring the full pipeline.

**User account isolation:** The guide creates its own user (`loose-student@test.example.edu.au`) distinct from the instructor (`instructor@uni.edu`) and the enrolled student (`student-demo@test.example.edu.au`). This user is enrolled in UNIT1234 at setup time but has no workspaces.
