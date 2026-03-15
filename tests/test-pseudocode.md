# Test Pseudocode

Human-readable description of what each test does, organised by domain.
Maintained by project-claude-librarian at branch completion.

Overlapping tests and coverage gaps are documented intentionally --
they reveal where the test suite is redundant or incomplete.

> **Scope:** This file covers tests added or modified on the
> 134-lua-highlight, 94-hierarchy-placement, 103-copy-protection,
> css-highlight-api, 165-auto-create-branch-db, 96-workspace-acl,
> 95-annotation-tags, workspace-navigator-196,
> user-docs-rodney-showboat-207,
> platform-handlers-openrouter-chatcraft-209, docs-platform-208,
> tags-214, word-count-limits-47, wargame-schema-294, card-layout-236,
> and pdf-export-filename-271 branches.
> Existing tests from before these branches are not yet documented here.

## Highlight Span Insertion (Pre-Pandoc)

### No highlights leaves HTML unchanged
**File:** tests/unit/export/test_highlight_spans.py::TestAC1_4_NoHighlights
1. Pass HTML with an empty highlights list to compute_highlight_spans
2. Assert output HTML is identical to input
3. Pass empty HTML with a highlight; assert output is empty string

**Verifies:** The pipeline is a no-op when there is nothing to highlight

### Single-block highlight produces one span
**File:** tests/unit/export/test_highlight_spans.py::TestAC1_3_SingleBlockHighlight
1. Create HTML with one paragraph
2. Create a highlight covering "simple" (chars 0-6)
3. Call compute_highlight_spans
4. Parse output, find spans with data-hl attribute
5. Assert exactly 1 span, with data-hl="0", data-colors="tag-jurisdiction-light", text="simple"
6. Repeat for mid-text highlight ("world" in "hello world today")

**Verifies:** Highlights within a single block produce exactly one span with correct attributes

### 3+ overlapping highlights carry all indices and colours
**File:** tests/unit/export/test_highlight_spans.py::TestAC1_2_OverlappingHighlights
1. Create HTML with one paragraph
2. Create 3 overlapping highlights on the same word "text"
3. Call compute_highlight_spans
4. Find spans where data-hl contains all three indices "0,1,2"
5. Assert all three colour names appear in data-colors
6. Repeat with only 2 overlapping highlights; assert data-hl="0,1"

**Verifies:** Overlapping highlights merge into single spans with comma-separated indices/colours

### Cross-block highlight produces pre-split spans
**File:** tests/unit/export/test_highlight_spans.py::TestAC1_1_CrossBlockSplit
1. Create HTML with h1 followed by p
2. Create a highlight spanning from h1 through p (entire text)
3. Call compute_highlight_spans
4. Assert at least 2 spans are emitted
5. Assert one span contains "Title" and one contains "Body text"
6. All spans have data-hl="0"

**Verifies:** Highlights crossing block boundaries are split into separate spans per block

### No single span crosses a block boundary
**File:** tests/unit/export/test_highlight_spans.py::TestAC1_5_NoCrossBlockSpan
1. Create cross-block highlight (h2 into p)
2. Call compute_highlight_spans
3. For each output span, walk up to find its block ancestor
4. Assert every span is fully within one block element
5. Assert separate spans exist for "Heading" and "Body"

**Verifies:** Pandoc would silently destroy cross-block spans; the pipeline prevents this

### Edge cases: adjacent, entities, newlines, annotations
**File:** tests/unit/export/test_highlight_spans.py::TestEdgeCases
1. Adjacent non-overlapping highlights produce 2 separate spans with different data-hl values
2. HTML entity (&amp;) within highlighted range: span text contains the decoded character
3. data-annots appears on exactly one span (the last span of a highlight)
4. data-annots contains pre-formatted LaTeX (\annot{tag-jurisdiction}{...})
5. Newline characters in text: highlight spans correctly cover both lines
6. PANDOC_BLOCK_ELEMENTS constant contains all required block elements

**Verifies:** Correct behaviour under non-trivial HTML content

### format_annot_latex produces correct annotation strings
**File:** tests/unit/export/test_highlight_spans.py::TestFormatAnnotLatex (function now in latex_format.py)
1. Basic: tag + author produces \annot{tag-jurisdiction}{\textbf{Jurisdiction}...Alice Jones}
2. Underscore tags: "key_issue" becomes "tag-key-issue" colour name and "Key Issue" display
3. Para ref "[45]" is included in margin content
4. ISO timestamp formatted as "26 Jan 2026 14:30"
5. Comments produce \par\hrulefill separator with author and text
6. Multiple comments each appear in output
7. LaTeX special characters (&) are escaped
8. Test UUID suffixes ("Alice Jones 1664E02D") are stripped from display names
9. Integration: data-annots attribute in compute_highlight_spans output contains pre-formatted LaTeX

**Verifies:** Annotation margin notes are correctly formatted as LaTeX

## Lua Filter (Pandoc Integration)

### Single highlight tier
**File:** tests/integration/test_highlight_lua_filter.py::TestSingleHighlight
1. Create HTML with span data-hl="0" data-colors="tag-jurisdiction-light"
2. Run Pandoc with highlight.lua filter
3. Assert LaTeX contains \highLight[tag-jurisdiction-light]{
4. Assert LaTeX contains \underLine[color=tag-jurisdiction-dark, height=1pt, bottom=-3pt]{
5. Assert "highlighted text" content is preserved

**Verifies:** Single highlight produces highlight background + 1pt underline in tag colour

### Two-highlight tier
**File:** tests/integration/test_highlight_lua_filter.py::TestTwoHighlights
1. Create HTML with span data-hl="0,1" and two colours
2. Run Pandoc with filter
3. Assert two nested \highLight wrappers
4. Assert outer underline is 2pt at -5pt, inner is 1pt at -3pt
5. Assert nesting order: jurisdiction (outer) wraps evidence (inner)

**Verifies:** Two highlights stack with distinct underline weights and correct nesting

### Three+ highlights (many-dark)
**File:** tests/integration/test_highlight_lua_filter.py::TestManyHighlights
1. Create HTML with span data-hl="0,1,2" and three colours
2. Run Pandoc with filter
3. Assert \underLine[color=many-dark, height=4pt, bottom=-5pt]{
4. Assert three nested \highLight wrappers
5. Assert NO individual dark colour underlines appear

**Verifies:** 3+ highlights collapse to single thick many-dark underline

### Annotation emission
**File:** tests/integration/test_highlight_lua_filter.py::TestAnnotation
1. Create HTML with span containing data-annots with pre-formatted \annot{} LaTeX
2. Run Pandoc with filter
3. Assert \annot{tag-jurisdiction} appears in output
4. Assert annotation content (author, tag name) is present
5. Assert annotation appears after all highlight/underline closing braces

**Verifies:** Annotations are emitted as raw LaTeX after the highlight wrapping

### Heading safety
**File:** tests/integration/test_highlight_lua_filter.py::TestHeading
1. Create h2 containing a highlighted span
2. Run Pandoc with filter
3. Assert \texorpdfstring{ appears (Pandoc auto-wraps for PDF bookmarks)

**Verifies:** Highlighted headings produce valid LaTeX (no \annot in \section{} args)

### No hl attribute (pass-through)
**File:** tests/integration/test_highlight_lua_filter.py::TestNoHlAttribute
1. Create HTML with span class="other" but no data-hl
2. Run Pandoc with filter
3. Assert no \highLight or \underLine in output
4. Assert text content preserved

**Verifies:** Non-highlight spans pass through without modification

### Edge cases: empty hl, empty colors
**File:** tests/integration/test_highlight_lua_filter.py::TestEdgeCases
1. Empty data-hl="": no highlights, no crash, text preserved
2. data-hl="0" but data-colors="": no highlights, no crash, text preserved

**Verifies:** Graceful degradation on malformed attributes

## Pipeline Cleanup Validation

### pylatexenc removed from main dependencies
**File:** tests/unit/export/test_pipeline_cleanup.py::TestAC4_1_PylatexencRemoved
1. Read pyproject.toml
2. Extract [project] dependencies section
3. Assert "pylatexenc" not in main deps
4. Assert "pylatexenc" IS still in dev deps (used by test helpers)

**Verifies:** Production dependency removed; dev dependency retained for structural LaTeX assertions

### latex.py deleted
**File:** tests/unit/export/test_pipeline_cleanup.py::TestAC4_2_LatexPyDeleted
1. Check src/promptgrimoire/export/latex.py path
2. Assert file does not exist

**Verifies:** Old monolithic module fully removed

### Old pipeline test files deleted
**File:** tests/unit/export/test_pipeline_cleanup.py::TestAC4_3_P4TestFilesDeleted
1. Parametrize over 7 deleted test file paths
2. Assert each file does not exist

**Verifies:** No orphaned tests from the old pipeline remain

### Old pipeline classes not importable
**File:** tests/unit/export/test_pipeline_cleanup.py::TestAC4_4_P4ClassesRemoved
1. Import promptgrimoire.export
2. Assert MarkerToken, MarkerTokenType, Region are not attributes of the module

**Verifies:** Old pipeline types are completely removed from the public API

### lark removed from dependencies
**File:** tests/unit/export/test_pipeline_cleanup.py::TestAC4_5_LarkRemoved
1. Read pyproject.toml
2. Assert "lark" not in main deps
3. Assert "lark" not in dev deps

**Verifies:** Lark dependency completely removed

### _format_annot replaced by format_annot_latex
**File:** tests/unit/export/test_pipeline_cleanup.py::TestAC4_6_FormatAnnotRemoved
1. Assert _format_annot not importable from export, preamble, or pandoc
2. Assert format_annot_latex IS importable from latex_format (moved from highlight_spans)

**Verifies:** Annotation formatting function renamed and relocated to latex_format.py

### Integration test file exists and resolves
**File:** tests/unit/export/test_pipeline_cleanup.py::TestAC5_3_IntegrationTestsExist
1. Assert tests/integration/test_highlight_latex_elements.py exists on disk
2. Import the module; assert no ImportError

**Verifies:** Integration tests survived the pipeline replacement

## Module Split Validation

### Line count constraints
**File:** tests/unit/export/test_module_split.py::TestAC3_1_LineCounts
1. Count lines in preamble.py; assert < 450
2. Count lines in pandoc.py; assert < 450
3. Assert latex.py does not exist (deleted in Phase 4)

**Verifies:** New modules stay manageable in size; old monolith removed

### Symbol placement matches DFD
**File:** tests/unit/export/test_module_split.py::TestAC3_2_SymbolPlacement
1. Import build_annotation_preamble from preamble; assert callable
2. Import generate_tag_colour_definitions from preamble; assert callable
3. Import convert_html_to_latex from pandoc; assert callable
4. Import convert_html_with_annotations from pandoc; assert callable

**Verifies:** Functions landed in the correct module per data flow design

### Public API imports resolve
**File:** tests/unit/export/test_module_split.py::TestAC3_3_PublicAPI
1. Import convert_html_to_latex from promptgrimoire.export
2. Import export_annotation_pdf from promptgrimoire.export
3. Import build_annotation_preamble from preamble
4. Import convert_html_with_annotations from pandoc
5. Import export_annotation_pdf from pdf_export

**Verifies:** Package-level re-exports work; no broken imports after restructuring

## Export Resilience

### Preamble loads .sty package
**File:** tests/unit/test_export_image_stripping.py::TestIncludegraphicsStub::test_preamble_loads_sty
1. Generate preamble with build_annotation_preamble
2. Assert \usepackage{promptgrimoire-export} appears in output

**Verifies:** The preamble correctly references the .sty package

### \includegraphics stub after hyperref in .sty
**File:** tests/unit/test_export_image_stripping.py::TestIncludegraphicsStub::test_stub_defined_after_hyperref_in_sty
1. Read promptgrimoire-export.sty content
2. Find last \RequirePackage position
3. Find \renewcommand{\includegraphics} position
4. Assert stub position is after last \RequirePackage

**Verifies:** Image references cannot crash PDF compilation (corrupt-PDF regression); stub survives hyperref/graphicx loading

### otherlanguage environment defined in .sty
**File:** tests/unit/test_export_image_stripping.py::TestOtherlanguageEnvironment
1. Read promptgrimoire-export.sty content
2. Assert "otherlanguage" and "newenvironment" appear in .sty

**Verifies:** Pandoc's language markup for non-English content does not crash compilation

### Markdown images stripped before Pandoc
**File:** tests/unit/test_export_image_stripping.py::TestMarkdownImageStripping
1. Convert markdown with ![alt](url) to LaTeX via markdown_to_latex_notes
2. Assert \includegraphics not in output
3. Repeat with reference-style images ![alt][id]
4. Verify empty/whitespace markdown returns empty string

**Verifies:** Image syntax in response drafts cannot produce \includegraphics in LaTeX

## LaTeX Compilation Safety (Process & Concurrency)

### Timeout kills entire process group
**File:** tests/unit/test_compile_latex_timeout.py::test_timeout_kills_process_group
1. Write a shell script that forks a child process (simulating latexmk -> lualatex), both sleep forever
2. Patch get_latexmk_path to use the script, patch wait_for to use 1s timeout
3. Call compile_latex, assert LaTeXCompilationError with "timed out"
4. Wait 0.2s for OS cleanup
5. Read child PID from file written by script
6. Assert os.kill(child_pid, 0) raises OSError (child is dead)

**Verifies:** Process group kill (os.killpg) kills both latexmk and its child lualatex, preventing orphaned processes from leaking memory

### Semaphore caps concurrent compilations at 2
**File:** tests/unit/test_compile_latex_timeout.py::test_semaphore_caps_concurrent_compilations
1. Create a fake _run_latexmk that tracks concurrent invocations and blocks until released
2. Launch 3 concurrent compile_latex tasks
3. Wait until 2 are running, then assert concurrent_count == 2 (third is blocked by semaphore)
4. Release all, gather results
5. Assert peak concurrency was exactly 2

**Verifies:** asyncio.Semaphore(2) prevents more than 2 concurrent LaTeX subprocesses server-wide

## Per-User PDF Export Lock

### Same user gets same lock instance
**File:** tests/unit/test_per_user_export_lock.py::test_same_user_gets_same_lock
1. Call _get_user_export_lock("user-1") twice
2. Assert both return the same Lock object (identity check)

**Verifies:** Lock registry returns consistent locks per user ID

### Different users get independent locks
**File:** tests/unit/test_per_user_export_lock.py::test_different_users_get_different_locks
1. Call _get_user_export_lock with "user-1" and "user-2"
2. Assert locks are different objects

**Verifies:** Users do not share export locks

### Lock blocks concurrent export for same user
**File:** tests/unit/test_per_user_export_lock.py::test_lock_blocks_concurrent_export_for_same_user
1. Acquire lock for "user-1" via async with
2. While held, assert lock.locked() is True
3. Re-fetch lock for same user, assert still locked (same instance)
4. Fetch lock for "user-2", assert not locked (independent)
5. After release, assert lock is no longer locked

**Verifies:** Per-user mutex prevents a single user from stacking concurrent PDF exports

## LaTeX Rendering Utilities

### NoEscape marker
**File:** tests/unit/export/test_latex_render.py::TestNoEscape
1. Assert NoEscape("x") is a str subclass
2. Concatenate two NoEscape values; assert result is "xy"
3. Pass NoEscape to escape_latex; assert returned object is the same instance (identity)

**Verifies:** NoEscape is a transparent str wrapper; escape_latex passes it through unchanged

### escape_latex special characters (AC4.3)
**File:** tests/unit/export/test_latex_render.py::TestEscapeLatex
1. Parametrize over all 10 LaTeX specials (#, $, %, &, _, {, }, ~, ^, \)
2. Assert each maps to its correct escape sequence
3. Normal text without specials passes through unchanged
4. Combined specials ("Cost: $30 & 50%") all escaped in one string
5. Tag names with specials (AC4.5): "C#_notes" becomes "C\#\_notes"
6. Assert return type is NoEscape

**Verifies:** All 10 LaTeX special characters are correctly escaped; result is trusted (NoEscape)

### latex_cmd command builder
**File:** tests/unit/export/test_latex_render.py::TestLatexCmd
1. Single arg: latex_cmd("textbf", "hello") produces \textbf{hello}
2. Multi arg: latex_cmd("definecolor", "mycolor", "HTML", "FF0000") produces \definecolor{mycolor}{HTML}{FF0000}
3. String args auto-escaped: "C#_notes" becomes "C\#\_notes" inside braces
4. NoEscape arg: passed through without re-escaping
5. Return type is NoEscape

**Verifies:** Programmatic LaTeX command construction with auto-escaping

### render_latex t-string renderer
**File:** tests/unit/export/test_latex_render.py::TestRenderLatex
1. Static t-string with no interpolation passes through verbatim
2. Interpolated value "C#" is auto-escaped to "C\#"
3. NoEscape interpolation is not re-escaped
4. Complex template with braces and interpolation produces correct output

**Verifies:** t-string rendering auto-escapes interpolated values while preserving static LaTeX

## Font Detection and Registry

### detect_scripts returns correct tags (AC3.1)
**File:** tests/unit/export/test_font_detection.py::TestDetectScriptsAC31
1. Parametrize over ASCII, Hebrew, Arabic, CJK, Devanagari, Greek, mixed, empty
2. For each: call detect_scripts(text) and assert correct frozenset of script tags

**Verifies:** Script detection correctly identifies Unicode script families from text

### Every required script is detectable (AC3.2 Guard 2)
**File:** tests/unit/export/test_font_detection.py::TestGuard2ScriptDetectability
1. Parametrize over all tags in _REQUIRED_SCRIPTS
2. For each: construct single character from first codepoint of first range
3. Call detect_scripts; assert the tag is in result

**Verifies:** No dead entries in FONT_REGISTRY -- every registered script can actually be detected

### Font registry and detection ranges consistent (AC3.7 Guard 4)
**File:** tests/unit/export/test_font_detection.py::TestGuard4DataConsistency
1. Assert _REQUIRED_SCRIPTS is a subset of SCRIPT_TAG_RANGES keys
2. Assert every non-latn font tag has a detection range
3. Combine one char from each required script; detect_scripts returns all of them

**Verifies:** FONT_REGISTRY, SCRIPT_TAG_RANGES, and _REQUIRED_SCRIPTS are mutually consistent

## Font Preamble Output

### Latin-only preamble (AC3.3)
**File:** tests/unit/export/test_font_preamble.py::TestLatinOnlyPreambleAC33
1. Call build_font_preamble(frozenset())
2. Assert base fonts present (Gentium Plus, Charis SIL, Noto Serif)
3. Assert \setmainfont{TeX Gyre Termes} present
4. Assert NO luatexja-fontspec, \setmainjfont, \renewcommand{\cjktext}
5. Assert NO non-base fonts (Ezra SIL, Scheherazade, etc.)

**Verifies:** Empty script set produces minimal Latin-only font preamble

### CJK preamble (AC3.4)
**File:** tests/unit/export/test_font_preamble.py::TestCJKPreambleAC34
1. Call build_font_preamble(frozenset({"cjk"}))
2. Assert luatexja-fontspec, ltjsetparameter, setmainjfont, setsansjfont present
3. Assert newjfontfamily\notocjk and renewcommand{\cjktext} present
4. Assert base fonts still present alongside CJK

**Verifies:** CJK script tag triggers full CJK font setup

### Mixed scripts (Hebrew + Arabic)
**File:** tests/unit/export/test_font_preamble.py::TestMixedScriptsPreamble
1. Call build_font_preamble(frozenset({"hebr", "arab"}))
2. Assert Hebrew fonts present (Ezra SIL, Noto Serif Hebrew)
3. Assert Arabic fonts present (Scheherazade, Noto Naskh Arabic)
4. Assert NO CJK setup
5. Assert base fonts present

**Verifies:** Selective font loading includes only fonts for detected scripts

### Full chain (all scripts)
**File:** tests/unit/export/test_font_preamble.py::TestFullChainGuard
1. Call build_font_preamble(_REQUIRED_SCRIPTS)
2. For every font in FONT_REGISTRY, assert its name appears in output

**Verifies:** All-scripts preamble contains every registered font

## LaTeX Migration Snapshots (AC4.4)

### generate_tag_colour_definitions output identity
**File:** tests/unit/export/test_latex_migration_snapshots.py::TestGenerateTagColourDefinitionsSnapshot
1. Call generate_tag_colour_definitions with 3 tags (including "C#_notes")
2. Assert exact string match against pre-migration baseline
3. Includes definecolor, colorlet -light, colorlet -dark for each tag, plus many-dark

**Verifies:** AC4.4 output identity -- post-migration output is byte-identical to pre-migration

### format_annot_latex output identity
**File:** tests/unit/export/test_latex_migration_snapshots.py::TestFormatAnnotLatexSnapshot
1. Basic with comments: author "Alice Jones ABC123" (UUID stripped), timestamp formatted, comment with "$damages" escaped
2. Special chars in author/comments: "C#_notes" tag, "O'Brien & Associates" author, tilde and percent in comment
3. With paragraph reference: "[45]" appears after tag name
4. No timestamp/no comments: minimal output

**Verifies:** AC4.4 output identity for annotation formatting across all edge cases

## f-string LaTeX Guard

### No f-string LaTeX in migrated files (AC4.1, AC4.2)
**File:** tests/unit/export/test_no_fstring_latex.py::test_no_fstring_latex_in_migrated_files
1. For each migrated file (preamble.py, latex_format.py, unicode_latex.py):
2. Parse AST, find f-strings with backslash in static parts
3. Check if enclosing function is in allowlist
4. Assert no violations remain

**Verifies:** Migrated files use latex_cmd/render_latex/NoEscape, not f-string LaTeX commands

### Migrated files import latex_render
**File:** tests/unit/export/test_no_fstring_latex.py::test_migrated_files_import_latex_render
1. For each migrated file: read source text
2. Assert "from promptgrimoire.export.latex_render import" present

**Verifies:** Migration is not circumvented by removing the import

## Mega-Document Infrastructure

### Mega-document compilation and subfiles
**File:** tests/integration/test_mega_doc_infrastructure.py::TestMegaDocInfrastructure
1. Compile 2-segment mega-document (alpha, beta)
2. Assert PDF created, non-empty, valid magic bytes
3. Assert segment_tex dict has entries for both segments
4. Assert subfile .tex paths exist on disk
5. Compile each subfile independently (AC1.5); assert PDF created
6. Assert PDF text contains content from both segments
7. Assert main .tex has \usepackage{subfiles}, \subfile{...}, \clearpage
8. Assert subfiles have \documentclass[mega_test.tex]{subfiles}
9. Subtests wrapper verifies independent execution (AC1.6)

**Verifies:** Mega-document builder works with subfiles package; each segment independently compilable

## English Mega-Document (Consolidated LaTeX Tests)

### 13 chatbot fixtures + pipeline tests in one compilation
**File:** tests/integration/test_english_mega_doc.py
1. Build segments from 13 English chatbot fixtures (claude_cooking through austlii)
2. Add pipeline segments: basic highlights, overlapping highlights, multi-paragraph, cross-env highlights
3. Compile all as one mega-document (AC1.1: 1 compile replaces ~38)
4. Per-fixture subtests: assert PDF text contains expected characters
5. Per-pipeline subtests: assert highlights, underlines, annotations present in LaTeX
6. Cross-env highlights: assert LibreOffice table HTML compiles successfully

**Verifies:** All English-only LaTeX compile tests pass in consolidated form

## i18n Mega-Document (CJK + Multilingual)

### 4 CJK/multilingual fixtures in one compilation
**File:** tests/integration/test_i18n_mega_doc.py
1. Load clean fixtures: chinese_wikipedia, japanese, korean, spanish
2. Compile as mega-document with CJK font support
3. Per-fixture subtests: assert expected CJK/Unicode characters in PDF text
4. Assert cjktext command present in CJK fixture LaTeX

**Verifies:** CJK and multilingual content compiles correctly in consolidated mega-document

## Workspace Placement Validation (Unit)

### Mutual exclusivity model validator
**File:** tests/unit/test_workspace_placement_validation.py::TestWorkspacePlacementExclusivity
1. Workspace.model_validate({}) -- both None is valid
2. Workspace.model_validate({activity_id: uuid}) -- activity only is valid
3. Workspace.model_validate({course_id: uuid}) -- course only is valid
4. Workspace.model_validate({activity_id: uuid, course_id: uuid}) -- raises ValueError "cannot be placed in both"
5. Direct construction Workspace(activity_id=X, course_id=Y) bypasses validator (documents SQLModel behavior; DB CHECK is the real guard)
6. enable_save_as_draft defaults to False; can be set to True

**Verifies:** Pydantic model_validator enforces mutual exclusivity of placement fields; documents that direct construction skips validation (intentional -- DB constraint covers it)

## Activity CRUD (Integration)

### Activity creation and schema constraints
**File:** tests/integration/test_activity_crud.py::TestCreateActivity
1. Create course+week, create workspace, create Activity with all fields -- assert UUID and timestamps auto-generated
2. Create workspace then Activity in single transaction -- assert template workspace exists after commit (atomic creation)
3. Create Activity with non-existent week_id -- assert IntegrityError (FK constraint)
4. Create Activity with null week_id -- assert IntegrityError (NOT NULL)

**Verifies:** Activity model has correct auto-fields, FK constraints, and NOT NULL enforcement at DB level

### Workspace placement DB constraints
**File:** tests/integration/test_activity_crud.py::TestWorkspacePlacementFields
1. Create workspace -- assert activity_id, course_id are None, enable_save_as_draft is False
2. Set both activity_id and course_id on a workspace via session -- assert IntegrityError matching "ck_workspace_placement_exclusivity"

**Verifies:** DB CHECK constraint enforces mutual exclusivity independently of Pydantic validator

### FK cascade and set-null behaviors
**File:** tests/integration/test_activity_crud.py::TestCascadeBehavior
1. Delete Activity that has a student workspace placed in it -- assert student workspace still exists with activity_id=None (SET NULL)
2. Delete Course that has a workspace with course_id set -- assert workspace still exists with course_id=None (SET NULL)
3. Delete Week that has an Activity -- assert Activity is gone (CASCADE)

**Verifies:** FK behaviors: Activity deletion SET NULLs workspace.activity_id, Course deletion SET NULLs workspace.course_id, Week deletion CASCADEs to Activity

### Activity CRUD lifecycle
**File:** tests/integration/test_activity_crud.py::TestActivityCRUD
1. create_activity -- assert UUID, title, description, template_workspace_id; verify template workspace has activity_id back-link
2. get_activity -- assert fields match
3. update_activity with new title+description -- assert fields updated, updated_at advanced
4. delete_activity -- assert returns True; get_activity returns None
5. delete_activity also deletes template workspace (CASCADE via explicit code)
6. update_activity with description=None -- clears description
7. update/delete/get on non-existent ID -- returns None/False/None

**Verifies:** Full Activity CRUD lifecycle, template workspace lifecycle, sentinel-based description clearing

### Activity copy_protection CRUD
**File:** tests/integration/test_activity_crud.py::TestActivityCRUD (copy_protection tests)
1. create_activity with copy_protection=True -- persists and round-trips
2. create_activity without copy_protection -- defaults to None (inherit)
3. update_activity copy_protection None to True -- persists
4. update_activity copy_protection True to None -- resets to inherit
5. update_activity with only title -- preserves existing copy_protection value (Ellipsis sentinel)

**Verifies:** copy_protection tri-state persists through create/update lifecycle; Ellipsis sentinel pattern leaves field unchanged when not explicitly provided

### List activities by week and course
**File:** tests/integration/test_activity_crud.py::TestListActivities
1. Create 3 activities in one week -- list_activities_for_week returns them ordered by created_at
2. list_activities_for_week on empty week -- returns empty list
3. Create activities across 2 weeks in one course -- list_activities_for_course returns them ordered by week_number then created_at

**Verifies:** Activity listing respects ordering contracts (created_at within week, week_number across course)

## Workspace Placement (Integration)

### Place, move, and unplace workspaces
**File:** tests/integration/test_workspace_placement.py::TestPlaceWorkspace
1. Place workspace in course, then place in activity -- assert activity_id set, course_id cleared, updated_at advanced
2. Place workspace in activity, then place in course -- assert course_id set, activity_id cleared
3. Place in activity, then make_workspace_loose -- assert both IDs cleared
4. place_workspace_in_activity with non-existent Activity -- ValueError
5. place_workspace_in_course with non-existent Course -- ValueError
6. place_workspace_in_activity with non-existent Workspace -- ValueError

**Verifies:** Placement functions enforce mutual exclusivity, update timestamps, validate entity existence

### List workspaces by activity and course
**File:** tests/integration/test_workspace_placement.py::TestListWorkspaces
1. Place 2 workspaces in Activity (plus auto-created template = 3) -- list_workspaces_for_activity returns all 3
2. Place 2 workspaces in Course, 1 in Activity -- list_loose_workspaces_for_course returns only the 2 course-placed ones

**Verifies:** Listing functions filter correctly; template workspace appears in activity listing

### PlacementContext hierarchy resolution
**File:** tests/integration/test_workspace_placement.py::TestPlacementContext
1. Loose workspace -- placement_type="loose", all hierarchy fields None, display_label="Unplaced"
2. Activity-placed workspace -- placement_type="activity", all fields populated (activity_title, week_number, week_title, course_code, course_name), display_label format correct
3. Course-placed workspace -- placement_type="course", course fields only, display_label="Loose work for CODE"
4. Template workspace -- is_template=True
5. Student workspace in same activity -- is_template=False
6. Loose workspace -- is_template=False
7. Non-existent workspace ID -- returns loose context

**Verifies:** PlacementContext correctly walks Activity->Week->Course chain, detects template workspaces, and degrades gracefully

### workspaces_with_documents batch query
**File:** tests/integration/test_workspace_placement.py::TestWorkspacesWithDocuments
1. Empty input set -- returns empty set (no DB query)
2. Workspace with 1 document -- included in result
3. Workspace with 0 documents -- excluded from result
4. Mixed set (1 with, 1 without documents) -- returns only the populated one
5. Non-existent UUIDs -- silently excluded

**Verifies:** Batch presence-check for documents is correct and handles edge cases

## Workspace Cloning (Integration)

### Document cloning
**File:** tests/integration/test_workspace_cloning.py::TestCloneDocuments
1. Clone activity with template that has enable_save_as_draft=True -- assert clone has activity_id set and flag copied
2. Clone template with 2 docs (source+draft) -- cloned docs preserve content, type, source_type, title, order_index
3. Clone template with 2 docs -- cloned doc UUIDs are all new; doc_id_map maps each template UUID to its clone
4. After clone, template workspace and all its documents are unchanged (field-by-field comparison)
5. Clone empty template (no docs) -- returns workspace with activity_id, empty doc_id_map, zero documents
6. Clone non-existent activity -- ValueError

**Verifies:** Document cloning preserves field values, generates independent UUIDs, does not mutate template, handles empty/missing cases

### CRDT state cloning
**File:** tests/integration/test_workspace_cloning.py::TestCloneCRDT
1. Template with highlight referencing doc 0 -- clone highlight has document_id remapped to cloned doc UUID (not template doc UUID)
2. Template with highlight with specific fields (start_char, end_char, tag, text, author, para_ref) -- all preserved in clone
3. Template with highlight + 2 comments -- comments preserved (author, text)
4. Template with registered client -- clone's client_meta map is empty (client metadata excluded)
5. Template with null crdt_state -- clone crdt_state is None
6. Template with 2 highlights + 2 docs -- all parts present after clone (atomicity)
7. Template with general notes -- notes cloned
8. Template with highlights referencing 2 different docs -- each highlight's document_id remapped to correct cloned doc

**Verifies:** CRDT replay correctly remaps document IDs, preserves highlight fields and comments, excludes client metadata, handles null state, and clones general notes

## Copy Protection Resolution (Integration)

### Activity copy_protection field round-trip (AC1.1-AC1.4)
**File:** tests/integration/test_workspace_placement.py::TestCopyProtectionResolution
1. Create activity with copy_protection=True -- fetch, assert True
2. Create activity with copy_protection=False -- fetch, assert False
3. Create activity with copy_protection=None -- fetch, assert None
4. Create activity without specifying copy_protection -- fetch, assert None (default)

**Verifies:** Activity.copy_protection tri-state stores and retrieves all three values correctly

### PlacementContext copy_protection resolution (AC2.1-AC2.4)
**File:** tests/integration/test_workspace_placement.py::TestCopyProtectionResolution
1. Workspace in activity with copy_protection=True -- PlacementContext.copy_protection is True
2. Workspace in activity with copy_protection=False -- PlacementContext.copy_protection is False
3. Loose workspace -- PlacementContext.copy_protection is False
4. Course-placed workspace -- PlacementContext.copy_protection is False

**Verifies:** PlacementContext resolves copy_protection from activity; loose/course workspaces always False

### Nullable fallback inheritance (AC3.1-AC3.7)
**File:** tests/integration/test_workspace_placement.py::TestCopyProtectionResolution
1. Activity cp=None, course default=True -- resolves True (inherits)
2. Activity cp=None, course default=False -- resolves False (inherits)
3. Activity cp=True, course default=False -- resolves True (explicit wins)
4. Activity cp=False, course default=True -- resolves False (explicit wins)
5. Change course default from False to True -- activity with cp=None now resolves True (dynamic inheritance)
6. Change course default -- activity with explicit cp=True is unaffected
7. New activity defaults to cp=None

**Verifies:** Tri-state resolution: explicit activity value wins, None inherits from course default, dynamic changes propagate to inheriting activities but not explicit ones

## Course Update (Integration)

### update_course default_copy_protection
**File:** tests/integration/test_course_service.py::TestUpdateCourse
1. Update default_copy_protection False to True -- round-trips via get_course_by_id
2. Update default_copy_protection True to False -- round-trips
3. Update name only -- preserves existing default_copy_protection (Ellipsis sentinel)
4. Update non-existent course -- returns None

**Verifies:** update_course correctly persists default_copy_protection changes; Ellipsis sentinel pattern leaves field unchanged when not provided

## Auth Role Check (Unit)

### is_privileged_user role classification (AC5.1-AC5.6)
**File:** tests/unit/test_auth_roles.py::TestIsPrivilegedUser
1. Org-level admin (is_admin=True) -- returns True
2. User with "instructor" role -- returns True
3. User with "stytch_admin" role -- returns True
4. Student (no privileged roles) -- returns False
5. Tutor role -- returns False (not privileged)
6. Unauthenticated (None) -- returns False
7. Empty dict (missing keys) -- returns False
8. roles=None (not a list) -- returns False

**Verifies:** is_privileged_user correctly classifies admins and instructors as privileged, all others as unprivileged

## Copy Protection Client-Side (Unit)

### Protection flag computation (AC4.12, AC4.13)
**File:** tests/unit/test_copy_protection_js.py::TestCopyProtectionInactiveStates
1. Activity with copy_protection=False, student user -- protect is False
2. Loose workspace (no activity) -- PlacementContext.copy_protection is False, protect is False
3. Activity with copy_protection=True, student user -- protect is True
4. Activity with copy_protection=True, instructor user -- protect is False (bypassed)
5. Activity with copy_protection=True, org admin -- protect is False (bypassed)
6. Activity with copy_protection=True, unauthenticated (None) -- protect is True
7. Course-placed workspace -- copy_protection defaults False, protect is False

**Verifies:** protect flag is True only when copy_protection is active AND user is not privileged; privileged users always bypass

### _inject_copy_protection function signature
**File:** tests/unit/test_copy_protection_js.py::TestInjectCopyProtectionFunction
1. Assert function is synchronous (not async)
2. Assert function takes no parameters

**Verifies:** Fire-and-forget JS injection function has correct signature

### _render_workspace_header protect parameter
**File:** tests/unit/test_copy_protection_js.py::TestRenderWorkspaceHeaderSignature
1. Assert "protect" parameter exists in signature
2. Assert protect defaults to False (backward compatible)

**Verifies:** Workspace header accepts protect flag for conditional lock icon rendering

### Print suppression injection (AC4.6)
**File:** tests/unit/test_copy_protection_js.py::TestPrintSuppressionInjection
1. Mock NiceGUI UI calls, call _inject_copy_protection -- ui.add_css called with @media print and .q-tab-panels
2. Mock UI calls, call _inject_copy_protection -- ui.html called with copy-protection-print-message div
3. When _inject_copy_protection is NOT called (protect=False) -- no CSS/HTML injection occurs

**Verifies:** Print suppression CSS and hidden message div are conditionally injected only when protection is active

## Copy Protection UI Mapping (Unit)

### _model_to_ui conversion
**File:** tests/unit/test_copy_protection_ui.py::TestModelToUi
1. None maps to "inherit"
2. True maps to "on"
3. False maps to "off"

**Verifies:** Model tri-state correctly converts to UI select key

### _ui_to_model conversion
**File:** tests/unit/test_copy_protection_ui.py::TestUiToModel
1. "inherit" maps to None
2. "on" maps to True
3. "off" maps to False

**Verifies:** UI select key correctly converts to model tri-state

### _COPY_PROTECTION_OPTIONS dictionary
**File:** tests/unit/test_copy_protection_ui.py::TestCopyProtectionOptions
1. Has exactly three entries
2. Keys are "inherit", "on", "off"
3. "inherit" label mentions "course"

**Verifies:** Options dictionary has correct structure for NiceGUI select widget

### Round-trip conversions
**File:** tests/unit/test_copy_protection_ui.py::TestRoundTrip
1. Parametrize model values (None, True, False) -- model->UI->model preserves identity
2. Parametrize UI values ("inherit", "on", "off") -- UI->model->UI preserves identity

**Verifies:** Bidirectional conversion is lossless for all valid values

## Browser Feature Gate (E2E)

### Supported browser sees annotation page
**File:** tests/e2e/test_browser_gate.py::test_supported_browser_sees_annotation
1. Navigate to login page
2. Verify feature gate element exists (checks CSS.highlights API)
3. If gate passes, navigate to annotation page
4. Assert annotation page loads with document container

**Verifies:** Browsers with CSS Custom Highlight API support reach the annotation page

### Unsupported browser sees warning
**File:** tests/e2e/test_browser_gate.py::test_unsupported_browser_sees_warning
1. Navigate to login page
2. Inject JS override to simulate missing CSS.highlights
3. Assert warning banner appears about unsupported browser

**Verifies:** Browsers without CSS Custom Highlight API get a clear message instead of silent failure

## Text Walker Parity (Integration)

### Python and JS text extraction produce identical results
**File:** tests/integration/test_text_walker_parity.py::test_text_walker_parity
1. For each HTML fixture (chatbot conversations, edge cases):
2. Run Python extract_text_from_html() on the HTML
3. Render HTML in Playwright browser, run JS textWalker.buildNodeMap()
4. Extract text from JS node map
5. Assert Python char list == JS char list (character-for-character)

**Verifies:** Server-side highlight coordinates map correctly to client-side text nodes

**Overlap note:** This test bridges the server (Python) and client (JS) text extraction.
It catches any divergence that would cause highlights to render at wrong positions.

### Edge case HTML produces matching results
**File:** tests/integration/test_text_walker_parity.py::test_edge_case_parity
1. Test empty HTML, whitespace-only, nested inline elements, entities
2. For each: compare Python extract vs JS textWalker
3. Assert identical character sequences

**Verifies:** Text walker parity holds for degenerate and complex HTML structures

## CSS Highlight API Rendering (E2E)

### Single highlight renders with correct colour
**File:** tests/e2e/test_highlight_rendering.py::test_single_highlight_renders
1. Load document with one highlight (chars 10-20, tag "jurisdiction")
2. Wait for CSS.highlights to contain "hl-0" highlight
3. Query computed styles on highlighted range
4. Assert background colour matches jurisdiction tag colour

**Verifies:** CSS Custom Highlight API applies correct tag colour to highlighted text

### Overlapping highlights render all layers
**File:** tests/e2e/test_highlight_rendering.py::test_overlapping_highlights
1. Load document with 2 overlapping highlights
2. Wait for CSS.highlights to contain both "hl-0" and "hl-1"
3. Assert both highlight registrations exist
4. Assert overlap region has both highlights applied

**Verifies:** Multiple overlapping highlights coexist without destroying each other

### Highlight persists after scroll
**File:** tests/e2e/test_highlight_rendering.py::test_highlight_persists_after_scroll
1. Load document with highlight in a long document
2. Scroll away from highlighted region
3. Scroll back to highlighted region
4. Assert highlight is still rendered

**Verifies:** CSS highlights survive DOM scroll events (no re-rendering needed)

### Empty document shows no highlights
**File:** tests/e2e/test_highlight_rendering.py::test_empty_document_no_highlights
1. Load empty document (no highlights)
2. Assert CSS.highlights registry is empty or has zero entries

**Verifies:** No phantom highlights appear on documents without annotations

### Highlight removal clears rendering
**File:** tests/e2e/test_highlight_rendering.py::test_highlight_removal
1. Load document with one highlight
2. Assert highlight renders
3. Remove highlight via API
4. Assert CSS.highlights no longer contains the highlight

**Verifies:** Highlight deletion propagates to CSS Custom Highlight API cleanup

## Bottom Toolbar CSS Audit (E2E)

### Toolbar is fixed to viewport bottom
**File:** tests/e2e/test_css_audit.py::TestStructuralCssProperties::test_toolbar_position_fixed_bottom
1. Navigate to annotation workspace
2. Locate `#tag-toolbar-wrapper` element
3. Assert computed CSS `position: fixed` and `bottom: 0px`

**Verifies:** Quasar q-footer keeps toolbar fixed at viewport bottom

### Toolbar has upward box shadow
**File:** tests/e2e/test_css_audit.py::TestStructuralCssProperties::test_toolbar_box_shadow_upward
1. Locate `#tag-toolbar-wrapper`
2. Assert computed box-shadow is `rgba(0,0,0,0.1) 0px -2px 4px 0px`

**Verifies:** Shadow projects upward to visually separate toolbar from content

### Compact button padding is tighter than Quasar default
**File:** tests/e2e/test_css_audit.py::TestStructuralCssProperties::test_compact_button_padding
1. Locate `.q-btn.compact-btn` inside `#tag-toolbar-wrapper`
2. Assert computed padding is `0px 6px`

**Verifies:** Custom `.compact-btn` CSS overrides Quasar's default button padding

### Highlight menu z-index above toolbar
**File:** tests/e2e/test_css_audit.py::TestStructuralCssProperties::test_highlight_menu_z_index
1. Locate `#highlight-menu`
2. Assert computed z-index is `110`

**Verifies:** Highlight creation popup renders above the toolbar (z-index 110 > 100)

### Sidebar uses relative positioning
**File:** tests/e2e/test_css_audit.py::TestStructuralCssProperties::test_sidebar_position_relative
1. Locate `.annotations-sidebar`
2. Assert computed CSS `position: relative`

**Verifies:** Annotation card sidebar is positioned relative (not fixed/absolute)

### Toolbar bottom edge at viewport bottom
**File:** tests/e2e/test_css_audit.py::TestLayoutCorrectness::test_toolbar_at_viewport_bottom
1. Get bounding box of `#tag-toolbar-wrapper`
2. Get viewport size
3. Assert toolbar bottom edge equals viewport height (within 1px)

**Verifies:** Toolbar visually occupies the bottom edge of the viewport

### Content not obscured by toolbar
**File:** tests/e2e/test_css_audit.py::TestLayoutCorrectness::test_content_not_obscured_by_toolbar
1. Get toolbar bounding box
2. Scroll to last paragraph in `.doc-container`
3. Get last paragraph bounding box
4. Assert paragraph bottom is above toolbar top (2px tolerance)

**Verifies:** Quasar q-page padding prevents content from being hidden behind toolbar

### No inline title heading
**File:** tests/e2e/test_css_audit.py::TestLayoutCorrectness::test_no_inline_title
1. Assert no element with classes `.text-2xl.font-bold` exists

**Verifies:** Workspace title moved to header; no redundant inline heading

### No UUID label visible
**File:** tests/e2e/test_css_audit.py::TestLayoutCorrectness::test_no_uuid_label
1. Assert no text matching `Workspace: <uuid>` pattern is visible

**Verifies:** Raw workspace ID not exposed in UI

### Header row renders after title removal
**File:** tests/e2e/test_css_audit.py::TestLayoutCorrectness::test_header_row_visible
1. Locate `[data-testid="user-count"]`
2. Assert visible within 5s

**Verifies:** Presence indicator still renders after inline title was removed

## Text Selection Detection (E2E)

### Selection produces correct char offsets
**File:** tests/e2e/test_text_selection.py::test_selection_char_offsets
1. Load document with known text content
2. Simulate mouse selection across a word
3. Wait for selection_made event from JS
4. Assert start_char and end_char match expected character indices

**Verifies:** Browser selection ranges convert correctly to document character offsets via text walker

### Selection across inline elements
**File:** tests/e2e/test_text_selection.py::test_selection_across_inline
1. Load document with bold/italic inline formatting
2. Select text spanning across formatting boundary
3. Assert char offsets are contiguous (inline elements don't break offset counting)

**Verifies:** Text walker correctly skips element boundaries when computing offsets

### Empty selection produces no event
**File:** tests/e2e/test_text_selection.py::test_empty_selection_no_event
1. Load document
2. Click without selecting (collapsed selection)
3. Assert no selection_made event fires

**Verifies:** Collapsed selections (clicks) are filtered out, preventing ghost highlights

### Selection at document boundaries
**File:** tests/e2e/test_text_selection.py::test_selection_at_boundaries
1. Select from start of document to middle
2. Assert start_char == 0
3. Select from middle to end of document
4. Assert end_char == last character index

**Verifies:** Boundary selections don't produce off-by-one errors

## Annotation Integration (E2E)

### Full highlight creation flow
**File:** tests/e2e/test_annotation_highlight_api.py::test_full_highlight_flow
1. Load annotation page with document
2. Select text range
3. Choose tag from dialog
4. Assert highlight appears in CSS.highlights
5. Assert highlight card appears in sidebar
6. Assert CRDT state updated with highlight data

**Verifies:** End-to-end highlight creation from selection through rendering to persistence

### Multiple highlights on same document
**File:** tests/e2e/test_annotation_highlight_api.py::test_multiple_highlights
1. Create first highlight (chars 0-10, tag A)
2. Create second highlight (chars 20-30, tag B)
3. Assert both highlights render independently
4. Assert both highlight cards appear in sidebar

**Verifies:** Multiple non-overlapping highlights coexist on the same document

## Remote Presence Rendering (E2E -- JS Functions)

### renderRemoteCursor places cursor at correct position
**File:** tests/e2e/test_remote_presence_rendering.py::test_cursor_position
1. Load document, build text node map
2. Call renderRemoteCursor(clientId, name, charIndex, color) via JS
3. Assert cursor element exists at correct text node position
4. Assert cursor shows user name label
5. Assert cursor colour matches provided color

**Verifies:** Remote cursor rendering maps character index to correct DOM position

### renderRemoteCursor with out-of-range index
**File:** tests/e2e/test_remote_presence_rendering.py::test_cursor_out_of_range
1. Call renderRemoteCursor with charIndex > document length
2. Assert no crash
3. Assert cursor is placed at document end or not rendered

**Verifies:** Graceful handling of stale cursor positions from disconnected clients

### renderRemoteSelection highlights correct range
**File:** tests/e2e/test_remote_presence_rendering.py::test_selection_range
1. Load document, build text node map
2. Call renderRemoteSelection(clientId, startChar, endChar, color) via JS
3. Assert CSS highlight registered for the selection range
4. Assert highlight colour matches provided color

**Verifies:** Remote selection rendering uses CSS Custom Highlight API correctly

### removeRemotePresence cleans up cursor and selection
**File:** tests/e2e/test_remote_presence_rendering.py::test_remove_presence
1. Render cursor and selection for a client
2. Call removeRemotePresence(clientId)
3. Assert cursor element removed from DOM
4. Assert CSS highlight deregistered

**Verifies:** Disconnect cleanup removes all visual artifacts for a client

### Multiple remote users render independently
**File:** tests/e2e/test_remote_presence_rendering.py::test_multiple_users
1. Render cursors for user A and user B at different positions
2. Assert both cursor elements exist with correct colours
3. Remove user A
4. Assert user B cursor still exists

**Verifies:** Per-client presence tracking is independent

### renderRemoteCursor updates position on repeated calls
**File:** tests/e2e/test_remote_presence_rendering.py::test_cursor_update
1. Render cursor at position 10
2. Render same client cursor at position 20
3. Assert only one cursor element exists (not two)
4. Assert cursor is at new position 20

**Verifies:** Cursor updates replace previous position rather than accumulating

## Remote Presence Multi-Context (E2E)

### Remote cursor appears in second browser
**File:** tests/e2e/test_remote_presence_e2e.py::test_remote_cursor_appears
1. Open same workspace in two browser contexts
2. Move cursor in browser A
3. Assert remote cursor element appears in browser B
4. Assert cursor shows browser A's user name

**Verifies:** Cursor broadcast via WebSocket reaches other clients

### Remote selection appears in second browser
**File:** tests/e2e/test_remote_presence_e2e.py::test_remote_selection_appears
1. Open same workspace in two browsers
2. Select text range in browser A
3. Assert selection highlight appears in browser B via CSS Custom Highlight API

**Verifies:** Selection broadcast renders as CSS highlight in remote browsers

### Disconnect removes presence
**File:** tests/e2e/test_remote_presence_e2e.py::test_disconnect_removes_presence
1. Open workspace in two browsers
2. Move cursor in browser A
3. Close browser A
4. Assert remote cursor disappears from browser B

**Verifies:** Server broadcasts disconnect to remaining clients, triggering cleanup

### Presence does not leak between workspaces
**File:** tests/e2e/test_remote_presence_e2e.py::test_no_cross_workspace_leak
1. Open workspace 1 in browser A
2. Open workspace 2 in browser B
3. Move cursor in browser A
4. Assert no remote cursor appears in browser B

**Verifies:** Workspace isolation prevents presence cross-contamination

### Three users see each other
**File:** tests/e2e/test_remote_presence_e2e.py::test_three_users
1. Open same workspace in three browsers
2. Each moves cursor to different position
3. Each browser sees exactly 2 remote cursors
4. Assert each remote cursor has correct colour and name

**Verifies:** Presence scales to N users with correct per-client rendering

## Server-Side Presence Refactor (Unit)

### Old CSS-injection symbols removed (AC3.5)
**File:** tests/unit/test_remote_presence_refactor.py::TestDeletedSymbolsAC35
1. Read annotation.py source text
2. Parse AST, collect all names (function defs, class defs, identifiers, attributes)
3. Assert _connected_clients not in source text
4. Assert _ClientState class does not exist (not in module, not in AST names)
5. Assert _build_remote_cursor_css, _build_remote_selection_css, _update_cursor_css, _update_selection_css do not exist
6. Assert PageState has no cursor_style or selection_style fields

**Verifies:** Old CSS-injection presence mechanism completely excised from codebase

### _RemotePresence dataclass replaces _ClientState
**File:** tests/unit/test_remote_presence_refactor.py::TestRemotePresenceDataclass
1. Assert _RemotePresence exists in annotation module
2. Assert it is a dataclass (dataclasses.is_dataclass)
3. Assert fields: name, color, nicegui_client, callback, cursor_char, selection_start, selection_end, has_milkdown_editor, user_id
4. Assert _workspace_presence dict exists at module level

**Verifies:** New presence data model is correctly structured with all required fields

## JS Interpolation Security (_render_js)

### String escaping (JSON-safe)
**File:** tests/unit/test_render_js.py::TestStringEscaping
1. Single quotes: "O'Brien" rendered as JSON string (escaped within double quotes)
2. Double quotes: 'say "hello"' rendered with escaped double quotes
3. Backslashes: path with backslashes rendered with doubled backslashes
4. Newlines: literal newline becomes \n escape (no raw newline in output)

**Verifies:** All string values are JSON-encoded, preventing JS string context escapes

### XSS prevention
**File:** tests/unit/test_render_js.py::TestXssPrevention
1. Script tag injection: "</script><script>alert(1)</script>" neutralised inside JSON string
2. Event handler injection: '");alert(document.cookie);//' - closing quote escaped
3. Template literal injection: backtick ${alert(1)} neutralised inside JSON string

**Verifies:** Adversarial inputs cannot escape the JSON string context to execute JS

### Unicode passthrough
**File:** tests/unit/test_render_js.py::TestUnicode
1. Emoji in display names survives round-trip through JSON encoding
2. CJK characters preserved
3. RTL (Arabic) text preserved
4. Null bytes escaped (not passed raw)

**Verifies:** Non-Latin characters pass through _render_js correctly

### Numeric and None handling
**File:** tests/unit/test_render_js.py::TestNumericPassthrough + TestNoneAndBool
1. Integers become bare JS numbers (42, -1, 0)
2. Floats become bare JS numbers (3.14)
3. None becomes JS null literal
4. Bool edge case: True/False render as Python str (documented, not used in practice)

**Verifies:** Non-string types pass through as appropriate JS literals

### Static template portions
**File:** tests/unit/test_render_js.py::TestStaticPortions
1. Template with no interpolation returns literal string
2. Multiple interpolations in one template: f("alice", 10, null)
3. Adjacent interpolations with no separator: "12"

**Verifies:** Static JS code in templates passes through unchanged alongside interpolated values

## Input Pipeline Public API (Unit)

### inject_char_spans and strip_char_spans removed
**File:** tests/unit/input_pipeline/test_public_api.py::test_removed_functions
1. Assert inject_char_spans not importable from input_pipeline
2. Assert strip_char_spans not importable from input_pipeline

**Verifies:** Old char-span injection functions removed from public API after CSS Highlight API migration

### extract_text_from_html added to public API
**File:** tests/unit/input_pipeline/test_public_api.py::test_extract_text_from_html_public
1. Import extract_text_from_html from input_pipeline
2. Call with simple HTML
3. Assert returns list of characters matching visible text

**Verifies:** New text extraction function is part of the public API

### Converter functions exported from package
**File:** tests/unit/input_pipeline/test_public_api.py::TestConverterExports
1. Assert convert_docx_to_html importable from input_pipeline and callable
2. Assert convert_pdf_to_html importable from input_pipeline and callable
3. Assert build_paragraph_map_for_json importable from input_pipeline and callable
4. Assert all three appear in __all__

**Verifies:** File upload converter functions are part of the public API

## Content Type Detection (Unit)

### Basic type detection from content signatures
**File:** tests/unit/input_pipeline/test_content_type.py::TestDetectContentType
1. HTML detected from DOCTYPE, html tag, div, p tags (case-insensitive, with whitespace)
2. RTF detected from magic header (string and bytes)
3. PDF detected from %PDF magic bytes
4. DOCX detected from PK signature + word/document.xml marker
5. Plain text as fallback (including angle brackets that aren't HTML tags)
6. Empty string returns "text"
7. Bytes content decoded as UTF-8

**Verifies:** Content type detection correctly classifies all supported input formats

### Fixture file detection
**File:** tests/unit/input_pipeline/test_content_type.py::TestDetectContentTypeFixtures
1. Parametrize over 12 HTML fixtures and 12 gzipped HTML fixtures
2. Assert all detected as "html" (gzipped decompressed first)
3. RTF fixture detected as "rtf"
4. JSON fixture (SillyTavern card) detected as "text"
5. BLNS (naughty strings) detected as "html" (contains XSS div tags)

**Verifies:** Detection works on real-world fixture files, not just synthetic inputs

### Fake-HTML reclassification (PDF viewer paste)
**File:** tests/unit/input_pipeline/test_content_type.py::TestFakeHtmlDetection
1. Plain text wrapped in html/body tags reclassified as "text"
2. Real HTML with block-level elements (p, div, h1, table, ul, ol, blockquote, pre, section, article) stays "html"
3. HTML with only inline elements (span, br) reclassified as "text"
4. Real evince PDF paste fixture wrapped in HTML body detected as "text"

**Verifies:** PDF viewer paste (plain text in HTML wrapper) correctly reclassified so newlines become br tags

## File Converters (Unit)

### DOCX to HTML conversion
**File:** tests/unit/input_pipeline/test_converters.py::TestConvertDocxToHtml
1. Convert real DOCX fixture, assert output contains p tags
2. Convert formatted DOCX, assert output contains strong or em tags
3. Assert output is string (not bytes)
4. Corrupt DOCX bytes raise ValueError
5. Empty bytes raise ValueError

**Verifies:** mammoth produces semantic HTML from DOCX with correct error handling

### PDF to HTML conversion
**File:** tests/unit/input_pipeline/test_converters.py::TestConvertPdfToHtml
1. Convert real PDF fixture (async), assert output contains p and heading tags
2. Assert output is string with substantial content (>100 chars)
3. Corrupt PDF bytes raise ValueError
4. Empty bytes raise ValueError
5. Mock pandoc failure raises ValueError (not CalledProcessError)

**Verifies:** pymupdf4llm + pandoc pipeline produces structured HTML from PDF with correct error handling

## Process Input Orchestration (Unit)

### Basic pipeline orchestration
**File:** tests/unit/input_pipeline/test_process_input.py::TestProcessInput
1. Empty text input produces empty paragraph
2. Plain text converted to HTML paragraphs (no char spans)
3. HTML content passes through preprocessing
4. Double newlines create separate paragraphs
5. Bytes input decoded and processed
6. Unsupported format (rtf) raises NotImplementedError
7. ChatCraft fixture preserves blockquotes and code blocks

**Verifies:** process_input() routes content types correctly through the pipeline

### DOCX through process_input
**File:** tests/unit/input_pipeline/test_process_input.py::TestProcessInputDocx
1. DOCX bytes produce semantic HTML with p tags (>100 chars)
2. Real fixture (Shen v R) produces valid HTML with paragraph structure and text
3. String input (instead of bytes) raises TypeError

**Verifies:** DOCX conversion integrates correctly with the full pipeline

### PDF through process_input
**File:** tests/unit/input_pipeline/test_process_input.py::TestProcessInputPdf
1. PDF bytes produce HTML with paragraph structure (>100 chars)
2. Real fixture (Lawlis v R) produces valid HTML with paragraphs and text
3. String input (instead of bytes) raises TypeError

**Verifies:** PDF conversion integrates correctly with the full pipeline

### PDF paste through process_input
**File:** tests/unit/input_pipeline/test_process_input.py::TestProcessInputPdfPaste
1. Fake-HTML paste (html/body wrapper around plain text) auto-detected as "text", produces br tags
2. Real evince fixture wrapped in HTML body produces multiple text blocks (>5 paragraphs + br tags)

**Verifies:** PDF viewer paste scenario produces properly structured output end-to-end

## Text Extraction (Unit)

### Basic HTML text extraction
**File:** tests/unit/input_pipeline/test_text_extraction.py::test_basic_extraction
1. Pass simple <p>Hello world</p> HTML
2. Assert returns ["H", "e", "l", "l", "o", " ", "w", "o", "r", "l", "d"]

**Verifies:** Text extraction produces character-by-character list from HTML content

### Nested elements and entities
**File:** tests/unit/input_pipeline/test_text_extraction.py::test_nested_and_entities
1. Pass HTML with nested bold/italic: <p><b>He<em>ll</em>o</b></p>
2. Assert inline elements don't break character sequence
3. Pass HTML with entity: <p>A &amp; B</p>
4. Assert entity decoded to single "&" character

**Verifies:** Text extraction handles HTML structure and entities correctly

## E2E Test Infrastructure

### E2E compliance guard
**File:** tests/unit/test_e2e_compliance.py
1. Scan all E2E test files for JS file references
2. Assert all referenced JS files are in ALLOWED_JS_FILES allowlist
3. Assert all allowed JS files exist on disk

**Verifies:** E2E tests only reference registered static JS files; no orphaned file references

### Async fixture safety guard
**File:** tests/unit/test_async_fixture_safety.py
1. Parse all test files' AST
2. Find all functions decorated with @pytest.fixture
3. Assert none of them are async def (must use @pytest_asyncio.fixture instead)

**Verifies:** No async fixtures use the sync decorator (prevents xdist event loop errors)

### E2E Helper: navigate_home_via_drawer
**File:** tests/e2e/annotation_helpers.py::navigate_home_via_drawer
1. Check if "Home" nav item is visible
2. If not, click header menu button to open nav drawer, wait 500ms
3. Assert "Home" nav item visible, click it

**Purpose:** Shared helper for navigating home via page_layout's nav drawer (replaces direct home button clicks)

### E2E Helper: scroll_to_char
**File:** tests/e2e/annotation_helpers.py::scroll_to_char
1. Wait for text walker to be ready
2. Call JS `walkTextNodes()` + `scrollToCharOffset()` with given char index
3. Wait 500ms for card positioning to update

**Purpose:** Scroll document to a character offset so annotation cards attached to that region become visible (cards hide when their highlight is off-screen)

## Database Bootstrap (ensure_database_exists return value)

### Returns False for None/empty/malformed URLs
**File:** tests/unit/test_db_schema.py::test_ensure_database_exists_returns_false_for_none_url, test_ensure_database_exists_returns_false_for_empty_url, test_ensure_database_exists_returns_false_for_url_without_db_name
1. Call ensure_database_exists(None) -- assert returns False
2. Call ensure_database_exists("") -- assert returns False
3. Call ensure_database_exists("postgresql://host/") -- assert returns False (no db name after slash)

**Verifies:** No-op cases return False without attempting a connection

### Returns True when database is created
**File:** tests/unit/test_db_schema.py::test_ensure_database_exists_returns_true_when_created
1. Mock psycopg.connect; mock cursor.fetchone returns None (DB does not exist)
2. Call ensure_database_exists with valid PostgreSQL URL
3. Assert returns True
4. Assert connection.execute called twice (SELECT pg_database + CREATE DATABASE)

**Verifies:** Function reports True when it actually creates the database

### Returns False when database already exists
**File:** tests/unit/test_db_schema.py::test_ensure_database_exists_returns_false_when_exists
1. Mock psycopg.connect; mock cursor.fetchone returns (1,) (DB exists)
2. Call ensure_database_exists with valid PostgreSQL URL
3. Assert returns False
4. Assert connection.execute called once (only SELECT, no CREATE)

**Verifies:** Function reports False for pre-existing databases without issuing CREATE

## Test Runner Header (CLI)

### Branch name appears in header
**File:** tests/unit/test_cli_header.py::TestBuildTestHeaderBranch
1. Call _build_test_header with branch="165-auto-create-branch-db"
2. Assert branch name appears in Rich Text output (plain text)
3. Assert branch name appears in plain-text log header

**Verifies:** Test runner header displays current branch name in both Rich panel and log file

### Database name appears in header
**File:** tests/unit/test_cli_header.py::TestBuildTestHeaderDbName
1. Call _build_test_header with db_name="promptgrimoire_test_165"
2. Assert DB name appears in Rich Text output
3. Assert DB name appears in plain-text log header

**Verifies:** Test runner header displays resolved test database name

### Detached HEAD handled gracefully
**File:** tests/unit/test_cli_header.py::TestBuildTestHeaderDetachedHead
1. Call _build_test_header with branch=None
2. Assert "detached/unknown" appears in Rich Text output
3. Assert "detached/unknown" appears in log header

**Verifies:** No crash on detached HEAD; fallback label displayed

### No database configured handled gracefully
**File:** tests/unit/test_cli_header.py::TestBuildTestHeaderNoDb
1. Call _build_test_header with db_name="not configured"
2. Assert "not configured" appears in both outputs

**Verifies:** Missing test DB URL produces informative message rather than crash

### Return type is (Rich Text, str) tuple
**File:** tests/unit/test_cli_header.py::TestBuildTestHeaderReturnTypes
1. Call _build_test_header with minimal args
2. Assert result is 2-tuple
3. Assert first element is rich.text.Text
4. Assert second element is str

**Verifies:** Function contract: returns (Text, str) for panel display and log file respectively

## App Startup Bootstrap (main)

### Bootstrap functions called when DB configured
**File:** tests/unit/test_main_startup.py::TestBootstrapCalledWithDbUrl
1. Configure Settings with database_url set
2. Mock ensure_database_exists (returns False) and run_alembic_upgrade
3. Call main()
4. Assert ensure_database_exists called once with the configured URL
5. Assert run_alembic_upgrade called once

**Verifies:** App startup invokes database creation and migration when DATABASE__URL is configured

### Seed data invoked when new database created
**File:** tests/unit/test_main_startup.py::TestSeedOnCreation
1. Mock ensure_database_exists to return True (new DB)
2. Mock subprocess.run
3. Call main()
4. Assert subprocess.run called with ["uv", "run", "seed-data"]

**Verifies:** Conditional seeding -- only runs seed-data when ensure_database_exists reports a newly created database

### Seed data NOT invoked for existing database
**File:** tests/unit/test_main_startup.py::TestNoSeedOnExistingDb
1. Mock ensure_database_exists to return False (existing DB)
2. Mock subprocess.run
3. Call main()
4. Assert no subprocess.run call with ["uv", "run", "seed-data"]

**Verifies:** Existing databases are not re-seeded on every startup

### Branch info printed for feature branches
**File:** tests/unit/test_main_startup.py::TestBranchInfoPrintedForFeatureBranch
1. Mock get_current_branch to return "165-auto-create-branch-db"
2. Configure database URL with db name "pg_branch_165"
3. Call main(), capture stdout
4. Assert "Branch: 165-auto-create-branch-db" in output
5. Assert "pg_branch_165" in output

**Verifies:** Feature branches print branch and database name to stdout for developer orientation

### Branch info NOT printed for main
**File:** tests/unit/test_main_startup.py::TestBranchInfoNotPrintedForMain
1. Mock get_current_branch to return "main"
2. Call main(), capture stdout
3. Assert "Branch:" not in output

**Verifies:** Main branch does not clutter output with branch info

### No bootstrap without database URL
**File:** tests/unit/test_main_startup.py::TestNoBootstrapWithoutDbUrl
1. Configure Settings with database_url=None
2. Mock ensure_database_exists and run_alembic_upgrade
3. Call main()
4. Assert neither function was called

**Verifies:** Bootstrap is entirely skipped when no database is configured (e.g. non-DB pages)

## Annotation Package Structure Guards (Unit)

### Package directory exists
**File:** tests/unit/test_annotation_package_structure.py::test_annotation_is_package_directory
1. Assert pages/annotation/ is a directory

**Verifies:** Annotation module is a package directory, not a file

### Package has __init__.py
**File:** tests/unit/test_annotation_package_structure.py::test_annotation_init_exists
1. Assert pages/annotation/__init__.py is a file

**Verifies:** Python package has required init module

### Monolith annotation.py does not exist
**File:** tests/unit/test_annotation_package_structure.py::test_monolith_annotation_py_does_not_exist
1. Assert pages/annotation.py does NOT exist as a file

**Verifies:** Old monolith file removed; a file here would shadow the package and break all imports

### All 17 authored modules present
**File:** tests/unit/test_annotation_package_structure.py::test_all_authored_modules_exist
1. Check __init__, broadcast, cards, content_form, css, document, highlights, organise, pdf_export, respond, tag_import, tag_management, tag_management_rows, tag_management_save, tag_quick_create, tags, workspace
2. Assert all 17 .py files exist in pages/annotation/

**Verifies:** No modules accidentally deleted during split or new additions

### No satellite files at pages/ level
**File:** tests/unit/test_annotation_package_structure.py::test_no_satellite_files_at_pages_level
1. Assert annotation_organise.py does NOT exist at pages/ level
2. Assert annotation_respond.py does NOT exist at pages/ level
3. Assert annotation_tags.py does NOT exist at pages/ level

**Verifies:** Phase 3 git-mv completed; old satellite files not re-introduced

### No imports from old satellite paths
**File:** tests/unit/test_annotation_package_structure.py::test_no_imports_from_old_satellite_paths
1. Scan all .py files in src/ and tests/
2. Regex match imports from promptgrimoire.pages.annotation_organise, annotation_respond, annotation_tags
3. Assert no matches

**Verifies:** All imports updated to new pages.annotation.{organise,respond,tags} paths

### No PLC0415 per-file-ignores for annotation package
**File:** tests/unit/test_annotation_package_structure.py::test_no_plc0415_ignores_for_annotation_package
1. Read pyproject.toml
2. Check for lines containing both "pages/annotation" and "PLC0415"
3. Assert no matches

**Verifies:** Annotation package uses definition-before-import ordering, not lint suppression

### Package is importable (smoke test)
**File:** tests/unit/test_annotation_package_structure.py::test_annotation_package_imports_succeed
1. Import PageState and annotation_page from promptgrimoire.pages.annotation
2. Assert both are not None

**Verifies:** Package resolves without import errors; key public names accessible

## JS Extraction Guards (Unit)

### annotation-card-sync.js exists and exposes setupCardPositioning
**File:** tests/unit/test_annotation_js_extraction.py::TestCardSyncJsExists
1. Assert static/annotation-card-sync.js exists
2. Assert file contains "function setupCardPositioning" declaration

**Verifies:** Card sync JS extracted from Python string constant to static file

### annotation-copy-protection.js exists and exposes setupCopyProtection
**File:** tests/unit/test_annotation_js_extraction.py::TestCopyProtectionJsExists
1. Assert static/annotation-copy-protection.js exists
2. Assert file contains "function setupCopyProtection" declaration

**Verifies:** Copy protection JS extracted from Python string constant to static file

### _COPY_PROTECTION_JS constant removed from Python source
**File:** tests/unit/test_annotation_js_extraction.py::TestNoCopyProtectionJsConstant
1. Scan all .py files in src/promptgrimoire/
2. Skip comments
3. Assert no line assigns _COPY_PROTECTION_JS

**Verifies:** Old Python string constant not re-introduced after extraction to static JS

## Annotation Page Structural Guards (Unit)

### No querySelector data-char-index in annotation package
**File:** tests/unit/test_no_char_span_queries.py::test_no_char_index_queries_in_annotation_py
1. Read all .py files in pages/annotation/ package
2. Assert "data-char-index" not in concatenated source

**Verifies:** Old char-span DOM queries removed after CSS Highlight API migration

### No data-char-index queries in annotation-highlight.js
**File:** tests/unit/test_no_char_span_queries.py::test_no_char_index_queries_in_annotation_highlight_js
1. Read static/annotation-highlight.js
2. Assert "querySelector" not combined with "data-char-index" or "char-span"

**Verifies:** Client-side JS also free of char-span queries

### Old presence symbols removed from annotation package
**File:** tests/unit/test_no_char_span_queries.py::test_no_old_presence_symbols_in_annotation_py
1. Read all .py files in pages/annotation/ package
2. Assert _connected_clients, _ClientState, _build_remote_cursor_css, _build_remote_selection_css not in source

**Verifies:** Old CSS-injection presence symbols fully excised

### hl-throb CSS rule uses only background-color
**File:** tests/unit/test_no_char_span_queries.py::test_hl_throb_css_rule_uses_only_background_color
1. Read all .py files in pages/annotation/ package
2. Find ::highlight(hl-throb) CSS rule via regex
3. Assert only background-color property present (CSS Highlight API limitation)

**Verifies:** Highlight throb animation uses only CSS Highlight API-compatible properties

## ACL Reference Tables (Integration)

### Permission seed data from migration
**File:** tests/integration/test_acl_reference_tables.py::TestPermissionSeedData
1. Query Permission table -- assert exactly 3 rows
2. Assert owner exists with level 30
3. Assert editor exists with level 20
4. Assert viewer exists with level 10

**Verifies:** Alembic migration seeds Permission reference table with correct name/level pairs

### CourseRoleRef seed data from migration
**File:** tests/integration/test_acl_reference_tables.py::TestCourseRoleRefSeedData
1. Query CourseRoleRef table -- assert exactly 4 rows
2. Assert coordinator exists with level 40
3. Assert instructor exists with level 30
4. Assert tutor exists with level 20
5. Assert student exists with level 10

**Verifies:** Alembic migration seeds CourseRoleRef table with correct name/level pairs

### Seed data comes from migration, not seed-data script
**File:** tests/integration/test_acl_reference_tables.py::TestSeedDataFromMigration
1. Inspect seed_data() function source code
2. Assert "Permission" not in source
3. Assert "CourseRoleRef" not in source

**Verifies:** Reference tables are populated by migration, not the seed-data CLI (integration test DB never runs seed-data)

### PK and constraint enforcement
**File:** tests/integration/test_acl_reference_tables.py::TestPermissionDuplicateNameRejected, TestCourseRoleRefDuplicateNameRejected, TestPermissionLevelConstraints, TestCourseRoleRefLevelConstraints
1. INSERT duplicate "owner" name -- assert IntegrityError (PK constraint)
2. INSERT duplicate "student" name -- assert IntegrityError (PK constraint)
3. Permission with level 0 -- assert IntegrityError (CHECK constraint, below range)
4. Permission with level 101 -- assert IntegrityError (CHECK constraint, above range)
5. Permission with level 30 (=owner) -- assert IntegrityError (UNIQUE constraint)
6. Same pattern for CourseRoleRef

**Verifies:** CHECK (1-100) and UNIQUE constraints on level column; PK on name column

## ACL CRUD (Integration)

### grant_permission creates and upserts ACL entries
**File:** tests/integration/test_acl_crud.py::TestGrantPermission
1. Create user and workspace, grant "viewer" -- assert entry has correct workspace_id, user_id, permission, id, created_at
2. Grant again with "editor" to same pair -- assert same row id (upsert), permission updated to "editor"

**Verifies:** grant_permission creates entries and upserts on conflict

### revoke_permission deletes entries
**File:** tests/integration/test_acl_crud.py::TestRevokePermission
1. Grant then revoke -- returns True
2. Revoke when no entry exists -- returns False
3. Revoke twice -- first True, second False

**Verifies:** revoke_permission returns correct boolean and actually deletes the row

### list_entries_for_workspace
**File:** tests/integration/test_acl_crud.py::TestListEntriesForWorkspace
1. Grant 2 users on same workspace -- list returns 2 entries with correct user_ids
2. Workspace with no entries -- returns empty list

**Verifies:** Workspace-scoped listing returns all entries and handles empty case

### list_entries_for_user
**File:** tests/integration/test_acl_crud.py::TestListEntriesForUser
1. Grant user on 2 workspaces -- list returns 2 entries with correct workspace_ids
2. User with no entries -- returns empty list

**Verifies:** User-scoped listing returns all entries and handles empty case

### CASCADE delete from Workspace
**File:** tests/integration/test_acl_crud.py::TestCascadeDeleteWorkspace
1. Grant permission on workspace, delete workspace -- list_entries returns empty

**Verifies:** Deleting workspace cascades to ACLEntry rows

### CASCADE delete from User
**File:** tests/integration/test_acl_crud.py::TestCascadeDeleteUser
1. Grant permission, delete user via session -- query ACLEntry for deleted user_id returns 0 rows

**Verifies:** Deleting user cascades to ACLEntry rows

### UNIQUE constraint on (workspace_id, user_id)
**File:** tests/integration/test_acl_crud.py::TestDuplicateConstraint
1. Insert ACLEntry directly, insert duplicate pair -- assert IntegrityError

**Verifies:** Direct INSERT (not upsert) of duplicate pair raises IntegrityError

## Course Role Normalisation (Integration)

### Role FK constraint
**File:** tests/integration/test_course_role_normalisation.py::TestRoleFKConstraint
1. Enroll user with role "student" -- succeeds, role string round-trips
2. Enroll user with invalid role "invalid_role" -- IntegrityError (FK constraint)

**Verifies:** CourseEnrollment.role is a FK to course_role reference table

### Enrollment CRUD with string roles
**File:** tests/integration/test_course_role_normalisation.py::TestEnrollmentCRUDWithStringRoles
1. Enroll with role="instructor" -- enrollment.role is "instructor"
2. Update role from "student" to "tutor" -- role string updated
3. Enroll without specifying role -- defaults to "student"

**Verifies:** All enrollment operations work with string role values

### Week visibility after normalisation
**File:** tests/integration/test_course_role_normalisation.py::TestWeekVisibilityAfterNormalisation
1. Create published and unpublished weeks, enroll instructor -- instructor sees both weeks
2. Enroll student -- student sees only published week

**Verifies:** Week visibility logic works identically after CourseRole StrEnum removal

## Permission Resolution (Integration)

### Explicit ACL resolution
**File:** tests/integration/test_permission_resolution.py::TestExplicitACL
1. Grant "viewer" to user on workspace -- resolve_permission returns "viewer"
2. Grant "editor" -- returns "editor"
3. Grant "owner" -- returns "owner"

**Verifies:** Explicit ACL entries are returned directly

### Enrollment-derived instructor access
**File:** tests/integration/test_permission_resolution.py::TestEnrollmentDerivedInstructor
1. Create activity-placed workspace, enroll instructor, no explicit ACL -- resolve_permission returns Course.default_instructor_permission ("editor")
2. Set default_instructor_permission to "viewer" -- resolve_permission returns "viewer"
3. Instructor on template workspace -- same enrollment-derived access applies

**Verifies:** Staff roles derive access from course enrollment; permission level follows Course.default_instructor_permission

### Enrollment-derived coordinator and tutor access
**File:** tests/integration/test_permission_resolution.py::TestEnrollmentDerivedCoordinator, TestEnrollmentDerivedTutor
1. Enroll as coordinator/tutor, no explicit ACL -- resolve_permission returns default_instructor_permission

**Verifies:** Coordinator and tutor roles also derive access (all staff roles treated equally)

### Highest wins when both exist
**File:** tests/integration/test_permission_resolution.py::TestHighestWins
1. Explicit "viewer" + enrollment-derived "editor" -- returns "editor" (derived wins)
2. Explicit "owner" + enrollment-derived "editor" -- returns "owner" (explicit wins)

**Verifies:** When both explicit ACL and enrollment-derived access exist, higher Permission.level wins

### Student without ACL denied
**File:** tests/integration/test_permission_resolution.py::TestStudentDenial
1. Enroll student in course, no explicit ACL on activity workspace -- resolve_permission returns None

**Verifies:** Students do not get enrollment-derived access (only staff roles do)

### Unenrolled user denied
**File:** tests/integration/test_permission_resolution.py::TestUnenrolledDenial
1. User not enrolled, no explicit ACL -- resolve_permission returns None

**Verifies:** Default deny for users with no access path

### Loose workspace access
**File:** tests/integration/test_permission_resolution.py::TestLooseWorkspace
1. Loose workspace, no ACL -- returns None
2. Loose workspace, explicit ACL "editor" -- returns "editor"
3. Instructor enrolled in a course, loose workspace -- returns None (no enrollment derivation for loose)

**Verifies:** Loose workspaces only support explicit ACL, no enrollment derivation

### Course-placed workspace access
**File:** tests/integration/test_permission_resolution.py::TestCoursePlacedWorkspace
1. Course-placed workspace, instructor enrolled in course -- returns default_instructor_permission
2. Course-placed workspace, student enrolled -- returns None

**Verifies:** Course-placed workspaces support enrollment-derived staff access

### can_access_workspace delegates correctly
**File:** tests/integration/test_permission_resolution.py::TestCanAccessWorkspace
1. User with ACL -- can_access_workspace returns same as resolve_permission
2. User without ACL or enrollment -- returns None

**Verifies:** can_access_workspace is a thin wrapper around resolve_permission

### Admin bypass and no-auth denial (unit-level)
**File:** tests/integration/test_permission_resolution.py::TestAdminBypass, TestNoAuthDenial
1. Admin is_admin=True -- is_privileged_user returns True
2. Instructor role -- is_privileged_user returns True
3. Admin without ACL -- resolve_permission returns None (admin bypass is page-level)
4. None auth_user -- is_privileged_user returns False
5. Unknown user_id -- resolve_permission returns None

**Verifies:** Admin bypass is NOT in the DB layer; is_privileged_user only checks auth_user dict

## Clone Eligibility (Integration)

### Enrolled student eligible
**File:** tests/integration/test_clone_eligibility.py::TestCheckCloneEligibility
1. Create hierarchy (course, published week, activity), enroll student -- check_clone_eligibility returns None (eligible)

**Verifies:** Enrolled student with published week passes eligibility check

### Unenrolled user rejected
**File:** tests/integration/test_clone_eligibility.py::TestCheckCloneEligibility
1. User not enrolled in course -- returns error containing "not enrolled"

**Verifies:** Unenrolled users cannot clone

### Non-existent activity rejected
**File:** tests/integration/test_clone_eligibility.py::TestCheckCloneEligibility
1. Random UUID as activity_id -- returns error containing "not found"

**Verifies:** Invalid activity IDs are caught

### Unpublished week blocks student
**File:** tests/integration/test_clone_eligibility.py::TestCheckCloneEligibility
1. Create unpublished week + activity, student enrolled -- returns error "not published"

**Verifies:** Students cannot clone activities in unpublished weeks

### Future visible_from blocks student
**File:** tests/integration/test_clone_eligibility.py::TestCheckCloneEligibility
1. Published week with visible_from 7 days in future -- returns error "not yet visible"

**Verifies:** Students cannot clone activities in not-yet-visible weeks

### Staff bypasses week visibility
**File:** tests/integration/test_clone_eligibility.py::TestCheckCloneEligibility
1. Instructor on unpublished week -- returns None (eligible)
2. Instructor on future-visible week -- returns None (eligible)

**Verifies:** Staff roles (via is_staff on CourseRoleRef) bypass week visibility checks

## Clone Ownership (Integration)

### Clone creates owner ACL entry
**File:** tests/integration/test_clone_ownership.py::TestCloneOwnership
1. Clone workspace from activity with user_id -- list ACL entries returns 1 entry with permission="owner" and correct user_id
2. Second student clones -- their entry has their user_id

**Verifies:** clone_workspace_from_activity creates an owner ACLEntry for the cloning user

### Duplicate detection
**File:** tests/integration/test_clone_ownership.py::TestDuplicateDetection
1. No cloned workspace yet -- get_user_workspace_for_activity returns None
2. After cloning -- returns the clone
3. Different user's clone not returned for another user

**Verifies:** get_user_workspace_for_activity correctly detects existing owned workspaces

### Type annotation guards unauthenticated access
**File:** tests/integration/test_clone_ownership.py::TestUnauthenticatedCloneRejection
1. Inspect type hints on check_clone_eligibility -- user_id is UUID (not Optional)
2. Inspect type hints on clone_workspace_from_activity -- user_id is UUID (not Optional)

**Verifies:** Type system prevents None from being passed as user_id

## Workspace Access Enforcement (Integration)

### Admin bypass via check_workspace_access
**File:** tests/integration/test_enforcement.py::TestCheckWorkspaceAccessAdminBypass
1. Admin auth_user (is_admin=True) with no ACL -- returns "owner"
2. Instructor role auth_user -- returns "owner"

**Verifies:** Admins and instructors bypass ACL via is_privileged_user

### No auth returns None
**File:** tests/integration/test_enforcement.py::TestCheckWorkspaceAccessNoAuth, TestCheckWorkspaceAccessUnauthenticated
1. None auth_user -- returns None
2. Auth_user with empty/missing user_id -- returns None

**Verifies:** Unauthenticated users are denied

### Permission levels returned correctly
**File:** tests/integration/test_enforcement.py::TestCheckWorkspaceAccessViewer, TestCheckWorkspaceAccessEditorOwner
1. User with "viewer" ACL -- returns "viewer"
2. User with "editor" ACL -- returns "editor"
3. User with "owner" ACL -- returns "owner"

**Verifies:** check_workspace_access returns the correct permission string

### Unauthorised user denied
**File:** tests/integration/test_enforcement.py::TestCheckWorkspaceAccessUnauthorised
1. User with no ACL and no enrollment -- returns None

**Verifies:** Default deny for users without access

### Revocation broadcast
**File:** tests/integration/test_enforcement.py::TestRevocationBroadcast
1. Revoke with no connected clients -- revoke_and_redirect returns 0
2. After revocation, workspace_presence dict is cleaned up

**Verifies:** Revocation handles empty presence gracefully and cleans up state

## Workspace Listing Queries (Integration)

### list_accessible_workspaces
**File:** tests/integration/test_listing_queries.py::TestListAccessibleWorkspaces
1. Owner sees cloned workspace with "owner" permission
2. Owner sees loose workspace with "owner" permission
3. Shared viewer sees workspace with "viewer" permission
4. Orphaned workspace (activity deleted) still accessible via persistent ACLEntry

**Verifies:** Student workspace listing returns all workspaces with explicit ACL entries

### list_course_workspaces (instructor view)
**File:** tests/integration/test_listing_queries.py::TestListCourseWorkspaces
1. Student clone included in results
2. Template workspace excluded
3. Loose workspace (course-placed) included

**Verifies:** Instructor course view shows student clones and loose workspaces but not templates

### list_activity_workspaces
**File:** tests/integration/test_listing_queries.py::TestListActivityWorkspaces
1. Student clone returned with owner user_id
2. Template workspace excluded
3. Non-existent activity returns empty list

**Verifies:** Per-activity view shows student clones with ownership info

### Resume vs Start detection
**File:** tests/integration/test_listing_queries.py::TestResumeDetection
1. Owner of cloned workspace -- get_user_workspace_for_activity returns the clone (resume)
2. Shared viewer -- returns None (start new, not resume shared workspace)

**Verifies:** Only owner ACL entries trigger resume; shared access does not count as "has workspace"

## Sharing Controls (Integration)

### grant_share success cases
**File:** tests/integration/test_sharing_controls.py::TestGrantShareSuccess
1. Owner shares as editor -- ACLEntry created with "editor" permission
2. Owner shares as viewer -- ACLEntry created with "viewer"
3. Staff bypasses sharing_allowed=False -- share succeeds
4. Share updates existing entry -- permission changed, same row

**Verifies:** Owners can share when allowed; staff always share; upsert works

### grant_share rejection cases
**File:** tests/integration/test_sharing_controls.py::TestGrantShareRejection
1. Non-owner tries to share -- PermissionError "only workspace owners can share"
2. Owner with sharing disabled -- PermissionError "sharing is not allowed"
3. Any user tries to grant "owner" -- PermissionError "cannot grant owner"

**Verifies:** Sharing rules enforced: owner-only, sharing-enabled, never owner permission

### Sharing tri-state inheritance
**File:** tests/integration/test_sharing_controls.py::TestSharingInheritance
1. Activity allow_sharing=None, course default=True -- PlacementContext.allow_sharing is True
2. Activity allow_sharing=None, course default=False -- PlacementContext.allow_sharing is False
3. Activity allow_sharing=True, course default=False -- PlacementContext.allow_sharing is True (explicit wins)
4. Activity allow_sharing=False, course default=True -- PlacementContext.allow_sharing is False (explicit wins)

**Verifies:** Same tri-state resolution pattern as copy_protection

## manage-users CLI (Unit)

### Argument parser
**File:** tests/unit/test_manage_users.py::TestUserParserSubcommands
1. "list" parses with no args
2. "list --all" sets include_all flag
3. "show" requires email positional
4. "admin" parses email and optional --remove flag
5. "enroll" parses email, code, semester, optional --role
6. "unenroll" parses email, code, semester
7. "role" parses email, code, semester, new_role
8. No subcommand raises SystemExit

**Verifies:** Argparse parser structure matches CLI contract

### _format_last_login
**File:** tests/unit/test_manage_users.py::TestFormatLastLogin
1. None returns "Never"
2. Datetime returns "YYYY-MM-DD HH:MM" formatted string

**Verifies:** Login timestamp formatting for CLI output

### Command output (mocked DB)
**File:** tests/unit/test_manage_users.py::TestCmdList, TestCmdShow, TestCmdAdmin, TestCmdEnroll
1. _cmd_list with users -- table shows emails, names, admin status, last login
2. _cmd_list empty -- prints "No users found"
3. _cmd_show with unknown email -- prints error and exits
4. _cmd_show with enrollments -- displays user details + enrollment table
5. _cmd_admin with unknown email -- prints error and exits
6. _cmd_admin set -- calls set_admin(True), prints confirmation
7. _cmd_admin remove -- calls set_admin(False), prints confirmation
8. _cmd_enroll with unknown course -- prints error and exits
9. _cmd_enroll success -- calls enroll_user, prints confirmation

**Verifies:** CLI subcommands produce correct output and handle error cases

## Course Update with Sharing (Integration)

### update_course default_allow_sharing
**File:** tests/integration/test_course_service.py::TestUpdateCourse (modified)
1. Update default_allow_sharing False to True -- round-trips via get_course_by_id
2. Update name only -- preserves existing default_allow_sharing (Ellipsis sentinel)

**Verifies:** update_course correctly persists default_allow_sharing changes

**Overlap note:** Extends existing TestUpdateCourse tests that cover default_copy_protection.

## DB Schema Guards (Unit -- modified)

### Expected tables list updated
**File:** tests/unit/test_db_schema.py (modified)
1. get_expected_tables() now returns 15 tables including wargame_config, wargame_team, wargame_message

**Verifies:** Schema verification function knows about all tables including wargame tables

### Activity metadata includes discriminator CHECK constraints
**File:** tests/unit/test_db_schema.py::test_activity_metadata_includes_discriminator_check_constraints
1. Import Activity model and inspect __table_args__
2. Filter for CheckConstraint instances
3. Assert ck_activity_type_known, ck_activity_annotation_requires_template, and ck_activity_wargame_no_template are present

**Verifies:** Activity table metadata carries all three discriminator CHECK constraints

## Annotation Tags -- Tag Model Defaults (Unit)

### TagGroup has auto UUID and defaults
**File:** tests/unit/test_tag_models.py::TestTagGroupDefaults
1. Create TagGroup via fixture
2. Assert id is UUID, name is stored, order_index defaults to 0, created_at is set, workspace_id is UUID

**Verifies:** TagGroup model fields have correct types and defaults

### Tag has auto UUID and defaults
**File:** tests/unit/test_tag_models.py::TestTagDefaults
1. Create Tag via fixture
2. Assert id is UUID, workspace_id is UUID, group_id defaults to None
3. Assert name/color stored, description defaults to None, locked defaults to False, order_index defaults to 0, created_at is set

**Verifies:** Tag model fields have correct types and defaults

### Activity.allow_tag_creation defaults to None
**File:** tests/unit/test_tag_models.py::TestActivityTagCreationPolicy
1. Construct Activity model without allow_tag_creation
2. Assert allow_tag_creation is None (inherits from course)

**Verifies:** Activity policy column defaults to tri-state inherit

### Course.default_allow_tag_creation defaults to True
**File:** tests/unit/test_tag_models.py::TestCourseTagCreationPolicy
1. Construct Course model without default_allow_tag_creation
2. Assert default_allow_tag_creation is True

**Verifies:** Course-level tag creation defaults to permissive

## Annotation Tags -- TagInfo Dataclass (Unit)

### TagInfo frozen dataclass properties
**File:** tests/unit/pages/test_annotation_tags.py::TestTagInfo
1. Create TagInfo, assert name/colour/raw_key are strings
2. Attempt mutation, assert AttributeError (frozen)
3. Assert colour matches hex pattern (#xxxxxx)
4. Assert equality for same fields, inequality for different raw_key

**Verifies:** TagInfo is immutable with expected string fields and correct equality semantics

## Annotation Tags -- Tag CRUD (Integration)

### Create tag with all fields
**File:** tests/integration/test_tag_crud.py::TestCreateTag::test_create_tag_with_all_fields
1. Create Course -> Week -> Activity hierarchy
2. Create TagGroup, then create Tag with name, color, group_id, description, locked=True, order_index=5
3. Assert all fields match, UUID generated, created_at set

**Verifies:** Full Tag creation with all fields persists correctly

### Create tag with only required fields
**File:** tests/integration/test_tag_crud.py::TestCreateTag::test_create_tag_with_only_required_fields
1. Create hierarchy, create Tag with only name and color
2. Assert group_id is None, description is None, locked is False, order_index auto-appends

**Verifies:** Defaults are correct when optional fields omitted

### Update tag fields
**File:** tests/integration/test_tag_crud.py::TestUpdateTag::test_update_tag_fields
1. Create tag, update name/color/description/group_id
2. Assert all updated fields match

**Verifies:** update_tag modifies requested fields

### Ellipsis sentinel leaves fields unchanged
**File:** tests/integration/test_tag_crud.py::TestUpdateTag::test_update_with_ellipsis_leaves_unchanged
1. Create tag with specific name/color/description
2. Call update_tag with only locked=True (other fields default to Ellipsis)
3. Assert original name/color/description unchanged, locked is True

**Verifies:** Ellipsis sentinel pattern distinguishes "not provided" from explicit None

### Update nonexistent tag returns None
**File:** tests/integration/test_tag_crud.py::TestUpdateTag::test_update_nonexistent_returns_none
1. Call update_tag with random UUID
2. Assert result is None

**Verifies:** Graceful handling of missing tags

### Create TagGroup with fields
**File:** tests/integration/test_tag_crud.py::TestCreateTagGroup::test_create_tag_group_with_fields
1. Create hierarchy, create TagGroup with name and order_index
2. Assert UUID, workspace_id, name, order_index all correct

**Verifies:** TagGroup creation persists correctly

### Update TagGroup name and order
**File:** tests/integration/test_tag_crud.py::TestUpdateTagGroup::test_update_tag_group_name_and_order
1. Create group, update name and order_index
2. Assert both changed

**Verifies:** update_tag_group modifies requested fields

### Delete TagGroup ungroups its tags
**File:** tests/integration/test_tag_crud.py::TestDeleteTagGroup::test_delete_group_ungroups_tags
1. Create group, create tag in group
2. Delete group
3. Assert tag still exists with group_id=None

**Verifies:** SET NULL FK on TagGroup delete preserves tags as ungrouped

### Locked tag rejects field changes
**File:** tests/integration/test_tag_crud.py::TestLockEnforcement::test_update_locked_tag_rejects_field_changes
1. Create tag with locked=True
2. Attempt update_tag with name change
3. Assert ValueError("Tag is locked")

**Verifies:** Lock enforcement blocks non-lock field modifications

### Locked tag rejects deletion
**File:** tests/integration/test_tag_crud.py::TestLockEnforcement::test_delete_locked_tag_raises
1. Create tag with locked=True
2. Attempt delete_tag
3. Assert ValueError("Tag is locked")

**Verifies:** Lock enforcement blocks tag deletion

### Lock toggle always permitted
**File:** tests/integration/test_tag_crud.py::TestLockEnforcement::test_lock_toggle_always_permitted
1. Create tag with locked=True
2. Call update_tag with locked=False
3. Assert success, locked is now False

**Verifies:** Instructors can always toggle the lock field itself

### Unlocked tag permits update and delete
**File:** tests/integration/test_tag_crud.py::TestLockEnforcement::test_unlocked_tag_allows_update_and_delete
1. Create unlocked tag
2. Rename it, assert success
3. Delete it, assert success

**Verifies:** No lock enforcement on unlocked tags

### Permission denied when tag creation disallowed
**File:** tests/integration/test_tag_crud.py::TestPermissionEnforcement::test_create_tag_denied_when_tag_creation_false
1. Create hierarchy with course default_allow_tag_creation=False
2. Create student workspace in activity
3. Attempt create_tag
4. Assert PermissionError

**Verifies:** Tag creation respects PlacementContext permission resolution

### Permission allowed when tag creation enabled
**File:** tests/integration/test_tag_crud.py::TestPermissionEnforcement::test_create_tag_allowed_when_tag_creation_true
1. Create hierarchy with course default_allow_tag_creation=True
2. Create student workspace, create tag
3. Assert tag created successfully

**Verifies:** Tag creation succeeds when permitted

### Permission denied for group creation when disallowed
**File:** tests/integration/test_tag_crud.py::TestPermissionEnforcement::test_create_tag_group_denied_when_tag_creation_false
1. Create hierarchy with tag creation disabled
2. Attempt create_tag_group
3. Assert PermissionError

**Verifies:** Group creation follows same permission gate as tag creation

### Reorder tags updates order_index
**File:** tests/integration/test_tag_crud.py::TestReorderTags::test_reorder_tags_updates_order_index
1. Create 3 tags with order 0,1,2
2. Call reorder_tags with reversed order [t3,t1,t2]
3. Re-fetch each, assert order_index matches new position

**Verifies:** Reorder assigns sequential order_index matching list position

### Reorder groups updates order_index
**File:** tests/integration/test_tag_crud.py::TestReorderTagGroups::test_reorder_groups_updates_order_index
1. Create 3 groups with order 0,1,2
2. Call reorder_tag_groups with reversed order
3. Re-fetch each, assert order_index matches new position

**Verifies:** Group reorder works identically to tag reorder

### Import copies groups and tags with new UUIDs
**File:** tests/integration/test_tag_crud.py::TestImportTagsFromActivity::test_import_copies_groups_and_tags
1. Create source activity with 1 group and 3 tags (2 grouped, 1 ungrouped)
2. Create target activity, call import_tags_from_activity
3. Assert target has 1 group and 3 tags with new UUIDs
4. Assert grouped tags point to new group, ungrouped tag has group_id=None
5. Assert all field values (color, description, locked, order_index) preserved

**Verifies:** Import creates independent copies with correct field preservation and group remapping

### Delete tag removes CRDT highlights
**File:** tests/integration/test_tag_crud.py::TestDeleteTagCrdtCleanup::test_delete_tag_removes_crdt_highlights
1. Create workspace with tag, build CRDT state with 3 highlights for that tag
2. Save CRDT state, delete tag
3. Reload CRDT, assert 0 highlights remain and tag_order entry removed

**Verifies:** Tag deletion cascades to CRDT highlight cleanup

### Delete tag preserves other tags' highlights
**File:** tests/integration/test_tag_crud.py::TestDeleteTagCrdtCleanup::test_delete_tag_preserves_other_highlights
1. Create 2 tags, build CRDT state with highlights for both
2. Delete tag A only
3. Assert tag B's highlights and tag_order entry preserved

**Verifies:** CRDT cleanup is surgical -- only removes targeted tag's data

### Delete tag succeeds when no tag_order entry exists
**File:** tests/integration/test_tag_crud.py::TestDeleteTagCrdtCleanup::test_delete_tag_no_tag_order_entry
1. Create tag, build CRDT with highlight but no tag_order entry
2. Delete tag -- assert no error
3. Assert highlights removed

**Verifies:** Missing tag_order is silently skipped during cleanup

## Annotation Tags -- Tag Schema & Cascade (Integration)

### PlacementContext inherits allow_tag_creation from course
**File:** tests/integration/test_tag_schema.py::TestPlacementContextTagCreation::test_inherits_from_course_true
1. Create hierarchy with course default=True, activity=None
2. Clone workspace, get PlacementContext
3. Assert allow_tag_creation is True

**Verifies:** Tri-state inheritance: None at activity level inherits course default

### Activity overrides course True with False
**File:** tests/integration/test_tag_schema.py::TestPlacementContextTagCreation::test_activity_overrides_course_true_with_false
1. Create hierarchy with course default=True, activity=False
2. Clone workspace, get PlacementContext
3. Assert allow_tag_creation is False

**Verifies:** Activity-level override wins over course default

### Activity overrides course False with True
**File:** tests/integration/test_tag_schema.py::TestPlacementContextTagCreation::test_activity_overrides_course_false_with_true
1. Create hierarchy with course default=False, activity=True
2. Clone workspace, get PlacementContext
3. Assert allow_tag_creation is True

**Verifies:** Activity-level override works in both directions

### Workspace delete cascades to tags
**File:** tests/integration/test_tag_schema.py::TestTagCascadeOnWorkspaceDelete::test_workspace_delete_cascades_to_tags
1. Create workspace, add TagGroup and Tag via direct session
2. Verify both exist
3. Delete workspace
4. Assert both TagGroup and Tag are gone

**Verifies:** CASCADE delete from Workspace propagates to tag tables

### TagGroup delete nullifies tag group_id
**File:** tests/integration/test_tag_schema.py::TestTagGroupSetNullOnDelete::test_tag_group_delete_nulls_tag_group_id
1. Create workspace, group, and tag in group
2. Delete group
3. Assert tag still exists with group_id=None

**Verifies:** SET NULL FK on TagGroup delete preserves tag rows

## Annotation Tags -- Tag Cloning (Integration)

### Clone creates TagGroups with same names and new UUIDs
**File:** tests/integration/test_tag_cloning.py::TestTagGroupCloning::test_clone_creates_tag_groups_with_same_names_and_order
1. Add 2 TagGroups to template workspace
2. Clone workspace
3. Assert cloned groups have same names and order_index but new UUIDs and new workspace_id

**Verifies:** TagGroup cloning preserves display properties with fresh identities

### Clone creates Tags with remapped group IDs
**File:** tests/integration/test_tag_cloning.py::TestTagCloning::test_clone_creates_tags_with_remapped_group_ids
1. Add 1 group and 3 tags (2 grouped, 1 ungrouped) to template
2. Clone workspace
3. Assert grouped tags point to clone's group (not template's), ungrouped stays None
4. Assert field values (color, description) preserved, new workspace_id

**Verifies:** Tag cloning remaps group_id references to cloned group UUIDs

### Clone preserves locked flag
**File:** tests/integration/test_tag_cloning.py::TestTagCloning::test_locked_flag_preserved_on_clone
1. Add locked and unlocked tags to template
2. Clone workspace
3. Assert locked tag stays locked, unlocked stays unlocked

**Verifies:** Lock state survives cloning

### Empty template produces zero tags
**File:** tests/integration/test_tag_cloning.py::TestEmptyTagClone::test_empty_template_produces_zero_tags
1. Clone a template with no tags
2. Assert 0 TagGroups and 0 Tags

**Verifies:** Cloning empty template is safe (no spurious data)

### CRDT highlight tags remapped to cloned tag UUIDs
**File:** tests/integration/test_tag_cloning.py::TestCrdtTagRemapping::test_highlight_tags_remapped_to_cloned_tag_uuids
1. Add 2 tags and 3 highlights to template CRDT (2 for TagA, 1 for TagB)
2. Clone workspace
3. Assert all cloned highlights reference cloned tag UUIDs, not template UUIDs

**Verifies:** CRDT highlight tag fields are remapped during clone replay

### tag_order keys remapped to cloned tag UUIDs
**File:** tests/integration/test_tag_cloning.py::TestCrdtTagRemapping::test_tag_order_keys_remapped_to_cloned_tag_uuids
1. Add 2 tags, 3 highlights with tag_order entries to template CRDT
2. Clone workspace
3. Assert tag_order keys are cloned tag UUIDs, not template UUIDs
4. Assert highlight IDs in tag_order are from clone, not template

**Verifies:** tag_order map is fully remapped during clone

### Legacy BriefTag strings pass through unchanged
**File:** tests/integration/test_tag_cloning.py::TestLegacyBriefTagPassthrough::test_legacy_string_tags_pass_through_unchanged
1. Add 1 UUID-based tag and build CRDT with one UUID highlight and one legacy string ("jurisdiction") highlight
2. Clone workspace
3. Assert UUID-based tag is remapped to cloned UUID
4. Assert legacy string "jurisdiction" passes through unchanged

**Verifies:** Backward compatibility with pre-UUID tag strings

## Annotation Tags -- Tag Creation Settings CRUD (Integration)

### Create activity with allow_tag_creation=False
**File:** tests/integration/test_tag_settings.py::TestCreateActivityWithTagCreation::test_create_with_allow_tag_creation_false
1. Create activity with allow_tag_creation=False
2. Assert persisted value is False after re-fetch

**Verifies:** create_activity accepts and persists allow_tag_creation

### Create activity defaults allow_tag_creation to None
**File:** tests/integration/test_tag_settings.py::TestCreateActivityWithTagCreation::test_create_without_allow_tag_creation_defaults_none
1. Create activity without allow_tag_creation
2. Assert persisted value is None

**Verifies:** Omitting allow_tag_creation defaults to inherit

### Update activity allow_tag_creation to False
**File:** tests/integration/test_tag_settings.py::TestUpdateActivityTagCreation::test_update_allow_tag_creation_to_false
1. Create activity (default None), update to False
2. Assert persisted value is False

**Verifies:** update_activity can set allow_tag_creation

### Reset activity allow_tag_creation to None
**File:** tests/integration/test_tag_settings.py::TestUpdateActivityTagCreation::test_update_allow_tag_creation_reset_to_none
1. Create activity with False, update to None
2. Assert persisted value is None

**Verifies:** Can reset to inherit after explicit override

### Update title only preserves allow_tag_creation
**File:** tests/integration/test_tag_settings.py::TestUpdateActivityTagCreation::test_update_title_only_preserves_allow_tag_creation
1. Create activity with allow_tag_creation=False
2. Update only title
3. Assert allow_tag_creation still False

**Verifies:** Ellipsis sentinel prevents unintended field resets

### Update course default_allow_tag_creation to False
**File:** tests/integration/test_tag_settings.py::TestUpdateCourseDefaultTagCreation::test_update_default_allow_tag_creation_to_false
1. Create course (default True), update to False
2. Assert persisted value is False

**Verifies:** update_course accepts and persists default_allow_tag_creation

### Update course default_allow_tag_creation to True
**File:** tests/integration/test_tag_settings.py::TestUpdateCourseDefaultTagCreation::test_update_default_allow_tag_creation_to_true
1. Set to False, then back to True
2. Assert persisted value is True

**Verifies:** Round-trip through both values works

### Update name only preserves default_allow_tag_creation
**File:** tests/integration/test_tag_settings.py::TestUpdateCourseDefaultTagCreation::test_update_name_only_preserves_default_allow_tag_creation
1. Set to False, then update only name
2. Assert default_allow_tag_creation still False

**Verifies:** Ellipsis sentinel on course update

### CRUD round-trip: inherit True from course
**File:** tests/integration/test_tag_settings.py::TestTriStateInheritanceFromCrud::test_activity_none_inherits_course_true
1. Set course default=True, activity=None via update functions
2. Clone workspace, check PlacementContext
3. Assert allow_tag_creation is True

**Verifies:** End-to-end inheritance through CRUD

### CRUD round-trip: activity True overrides course False
**File:** tests/integration/test_tag_settings.py::TestTriStateInheritanceFromCrud::test_activity_true_overrides_course_false
1. Set course default=False, activity=True via update functions
2. Clone workspace, check PlacementContext
3. Assert allow_tag_creation is True

**Verifies:** Activity override via CRUD round-trip

### CRUD round-trip: activity False overrides course True
**File:** tests/integration/test_tag_settings.py::TestTriStateInheritanceFromCrud::test_activity_false_overrides_course_true
1. Set course default=True, activity=False via update functions
2. Clone workspace, check PlacementContext
3. Assert allow_tag_creation is False

**Verifies:** Activity override in the other direction

## Annotation Tags -- Tag Management Workflow (Integration)

### Created tag appears in workspace_tags()
**File:** tests/integration/test_tag_management.py::TestQuickCreateWorkflow::test_created_tag_appears_in_workspace_tags
1. Create tag via create_tag
2. Call workspace_tags(ws_id)
3. Assert 1 TagInfo with correct name, colour, raw_key

**Verifies:** End-to-end create-to-render pipeline works

### Tag UUID usable as CRDT highlight tag
**File:** tests/integration/test_tag_management.py::TestQuickCreateWorkflow::test_tag_uuid_usable_as_crdt_highlight_tag
1. Create tag, get raw_key from workspace_tags()
2. Create CRDT highlight using raw_key as tag value
3. Assert highlight stores the tag UUID

**Verifies:** Tag UUIDs are valid CRDT highlight tag identifiers

### Creation denied when course disallows
**File:** tests/integration/test_tag_management.py::TestCreationGating::test_creation_denied_when_course_disallows
1. Create hierarchy with default_allow_tag_creation=False
2. Attempt create_tag
3. Assert PermissionError

**Verifies:** Permission gate works at workflow level

### Creation allowed when course allows
**File:** tests/integration/test_tag_management.py::TestCreationGating::test_creation_allowed_when_course_allows
1. Create hierarchy with default_allow_tag_creation=True
2. Create tag, assert success

**Verifies:** Permission gate permits when enabled

### Delete tag removes from workspace_tags
**File:** tests/integration/test_tag_management.py::TestDeleteWithCrdtCleanup::test_delete_tag_removes_from_workspace_tags
1. Create tag, verify workspace_tags returns 1
2. Delete tag
3. Assert workspace_tags returns 0

**Verifies:** Deleted tag disappears from rendering pipeline

### Delete tag cleans CRDT highlights
**File:** tests/integration/test_tag_management.py::TestDeleteWithCrdtCleanup::test_delete_tag_cleans_crdt_highlights
1. Create tag, build CRDT with 2 highlights for it, save state
2. Delete tag
3. Reload CRDT, assert 0 highlights for that tag

**Verifies:** CRDT cleanup integrated with delete workflow

### Imported tags appear in workspace_tags
**File:** tests/integration/test_tag_management.py::TestImportWorkflow::test_imported_tags_appear_in_workspace_tags
1. Create source activity with 2 tags
2. Create target activity, import tags
3. Assert workspace_tags returns 2 with correct names and colours

**Verifies:** Import-to-render pipeline works end-to-end

### Imported tags have different UUIDs
**File:** tests/integration/test_tag_management.py::TestImportWorkflow::test_imported_tags_have_different_uuids
1. Create source tag, get its raw_key
2. Import into target
3. Assert target tag has different raw_key but same name/colour

**Verifies:** Import creates independent copies, not references

## Annotation Tags -- workspace_tags() DB Query (Integration)

### workspace_tags returns correct TagInfo for 3 tags
**File:** tests/integration/test_workspace_tags.py::TestWorkspaceTags::test_workspace_with_three_tags
1. Create workspace, add 3 tags via direct session
2. Call workspace_tags()
3. Assert 3 TagInfo instances with correct name, colour, raw_key

**Verifies:** DB-to-TagInfo mapping is correct

### workspace_tags returns empty list for no tags
**File:** tests/integration/test_workspace_tags.py::TestWorkspaceTags::test_workspace_with_no_tags
1. Create empty workspace
2. Call workspace_tags()
3. Assert empty list

**Verifies:** No error on empty workspace

### workspace_tags respects order_index
**File:** tests/integration/test_workspace_tags.py::TestWorkspaceTagsOrdering::test_returns_tags_ordered_by_order_index
1. Create 3 tags inserted out of order (2, 0, 1)
2. Call workspace_tags()
3. Assert results ordered: First, Second, Third

**Verifies:** Tags sorted by order_index regardless of insertion order

## Annotation Tags -- Empty Template Tag Management (Integration)

### Empty workspace returns empty tag list
**File:** tests/integration/test_empty_template_tags.py::TestEmptyWorkspaceTags::test_empty_workspace_returns_empty_tag_list
1. Create course, week, and activity (provisions empty template workspace)
2. Call workspace_tags() on the template workspace
3. Assert result is empty list

**Verifies:** workspace_tags() returns empty list for a new workspace with no tags and no documents (AC1.1)

### Tags on empty workspace are retrievable
**File:** tests/integration/test_empty_template_tags.py::TestEmptyWorkspaceTags::test_tags_on_empty_workspace_are_retrievable
1. Create activity with empty template workspace
2. Create a tag group "Legal Issues" and tag "Jurisdiction" on the template
3. Call workspace_tags()
4. Assert one TagInfo returned with correct name, colour, raw_key, group_name

**Verifies:** Tags created on a workspace with zero WorkspaceDocument rows are returned by workspace_tags() (AC1.1)

### Import tags into empty template
**File:** tests/integration/test_empty_template_tags.py::TestImportTagsToEmptyTemplate::test_import_tags_into_empty_template
1. Create source activity, add two tags ("Damages", "Liability")
2. Create target activity (empty template, different course)
3. Verify target workspace_tags() returns empty list
4. Call import_tags_from_activity() from source to target
5. Assert 2 tags imported, workspace_tags() returns both names

**Verifies:** import_tags_from_activity() works for templates with no documents (AC1.3)

### Import tags with groups into empty template
**File:** tests/integration/test_empty_template_tags.py::TestImportTagsToEmptyTemplate::test_import_tags_with_groups_into_empty_template
1. Create source activity, add tag group "Core Issues" with tag "Negligence"
2. Create empty target activity
3. Import tags from source to target
4. Assert imported tag has correct name and group_name preserved

**Verifies:** Group assignment survives import into an empty template (AC1.3)

### Create then query reflects immediately
**File:** tests/integration/test_empty_template_tags.py::TestTagMutationsReflectedInWorkspaceTags::test_create_then_query
1. Create activity, verify workspace_tags() starts empty
2. Create tag "Tag A"
3. Call workspace_tags() again
4. Assert one tag returned with name "Tag A"

**Verifies:** Tag creation is immediately reflected in workspace_tags() (AC1.4)

### Rename then query reflects immediately
**File:** tests/integration/test_empty_template_tags.py::TestTagMutationsReflectedInWorkspaceTags::test_rename_then_query
1. Create tag "Old Name" on empty template
2. Rename via update_tag() to "New Name"
3. Call workspace_tags()
4. Assert tag name is "New Name"

**Verifies:** Tag rename is immediately reflected in workspace_tags() (AC1.4)

### Delete then query reflects immediately
**File:** tests/integration/test_empty_template_tags.py::TestTagMutationsReflectedInWorkspaceTags::test_delete_then_query
1. Create tag "To Delete" on empty template
2. Delete via delete_tag()
3. Call workspace_tags()
4. Assert empty list

**Verifies:** Tag deletion is immediately reflected in workspace_tags() (AC1.4)

### Sequential mutations all reflected
**File:** tests/integration/test_empty_template_tags.py::TestTagMutationsReflectedInWorkspaceTags::test_sequential_mutations
1. Create two tags ("Alpha", "Beta"), verify both returned
2. Rename "Alpha" to "Alpha Renamed", verify set is {"Alpha Renamed", "Beta"}
3. Delete "Beta", verify only "Alpha Renamed" remains
4. Create "Gamma", verify set is {"Alpha Renamed", "Gamma"}

**Verifies:** A sequence of create, rename, and delete mutations are all consistently reflected (AC1.4)

### Clone copies tags from empty template
**File:** tests/integration/test_empty_template_tags.py::TestCloneEmptyTemplateWithTags::test_clone_copies_tags_from_empty_template
1. Create activity, add tag group "Issues" with tags "Causation" and "Duty of Care"
2. Create a user, clone workspace via clone_workspace_from_activity()
3. Assert cloned workspace has same tag names and group assignment as template
4. Assert cloned tag UUIDs are different from template (independent copies)

**Verifies:** Tags and groups on an empty template are snapshot-copied during cloning (AC2.1)

### Tags returned identically with document present
**File:** tests/integration/test_empty_template_tags.py::TestWorkspaceWithDocumentsStillReturnsTags::test_tags_returned_with_document_present
1. Create activity, add a document via add_document()
2. Add tag group "Analysis" with tag "Key Finding"
3. Call workspace_tags()
4. Assert one TagInfo returned with correct name, colour, raw_key, group_name

**Verifies:** workspace_tags() returns tags the same way whether documents exist or not (AC3.1 -- non-regression)

**Overlap note:** test_empty_workspace_returns_empty_tag_list and test_tags_on_empty_workspace_are_retrievable overlap with tests/integration/test_workspace_tags.py (existing workspace_tags tests). The new tests specifically target workspaces created via the activity provisioning path (with zero WorkspaceDocument rows), while the existing tests use direct workspace creation.

## CLI Test Harness (Unit)

### test all selects unit-only marker expression
**File:** tests/unit/test_cli_testing.py::TestTestAll::test_test_all_excludes_e2e_and_nicegui_ui
1. Monkeypatch `_run_pytest` to capture args
2. Invoke `test all` via Typer runner
3. Assert marker expression is `not e2e and not nicegui_ui and not latexmk_full and not smoke`
4. Assert `tests/unit` is in default_args (path narrowing)

**Verifies:** `test all` runs only unit tests with the correct exclusion markers

### test smoke selects smoke marker
**File:** tests/unit/test_cli_testing.py::TestTestAll::test_test_smoke_selects_smoke_marker
1. Monkeypatch `_run_pytest` to capture args
2. Invoke `test smoke` via Typer runner
3. Assert marker expression is `smoke`

**Verifies:** `test smoke` collects only smoke-marked tests

### test smoke runs serially
**File:** tests/unit/test_cli_testing.py::TestTestAll::test_test_smoke_runs_serial
1. Monkeypatch `_run_pytest` to capture args
2. Invoke `test smoke`
3. Assert `-n` is NOT in default args

**Verifies:** Smoke tests do not use xdist parallelism

### test smoke clears addopts
**File:** tests/unit/test_cli_testing.py::TestTestAll::test_test_smoke_clears_addopts
1. Monkeypatch `_run_pytest` to capture args
2. Invoke `test smoke`
3. Assert `-o addopts=` is in default args

**Verifies:** Smoke lane overrides pyproject.toml addopts to prevent double-exclusion of smoke marker

### all-fixtures command removed
**File:** tests/unit/test_cli_testing.py::TestTestAll::test_test_all_fixtures_removed
1. Invoke `test all-fixtures` via Typer runner
2. Assert non-zero exit code

**Verifies:** The old `all-fixtures` subcommand no longer exists (replaced by `smoke` + lane model)

## CLI Utilities (Unit)

### _allocate_ports returns distinct ports
**File:** tests/unit/test_cli_parallel.py::test_allocate_ports_returns_distinct_ports
1. Call _allocate_ports(5)
2. Assert 5 ports returned, all distinct, all > 0

**Verifies:** Port allocator produces unique positive port numbers for parallel E2E workers

### _allocate_ports single port
**File:** tests/unit/test_cli_parallel.py::test_allocate_ports_single
1. Call _allocate_ports(1)
2. Assert exactly 1 port returned, > 0

**Verifies:** Edge case -- single worker gets one valid port

### _allocate_ports zero returns empty
**File:** tests/unit/test_cli_parallel.py::test_allocate_ports_zero
1. Call _allocate_ports(0)
2. Assert empty list returned

**Verifies:** Zero workers produces no ports (no crash)

## Database Bootstrap Helpers (Unit)

### terminate_connections executes correct SQL
**File:** tests/unit/test_db_schema.py::TestTerminateConnections::test_executes_correct_sql_with_db_name
1. Mock psycopg.connect
2. Call terminate_connections with a URL and db name
3. Assert SQL contains pg_terminate_backend and pg_stat_activity
4. Assert db name passed as parameter

**Verifies:** terminate_connections sends the right SQL to kill active connections

### terminate_connections uses postgres maintenance database
**File:** tests/unit/test_db_schema.py::TestTerminateConnections::test_connects_to_postgres_maintenance_database
1. Mock psycopg.connect
2. Call terminate_connections with an asyncpg URL
3. Assert connection URL ends with /postgres (not the target db)
4. Assert asyncpg driver replaced with sync driver

**Verifies:** Connects to postgres maintenance DB, not the target being terminated

### clone_database creates from template
**File:** tests/unit/test_db_schema.py::TestCloneDatabase::test_happy_path_creates_database_from_template
1. Mock psycopg.connect and terminate_connections
2. Call clone_database with source URL and target name
3. Assert SQL contains CREATE DATABASE and TEMPLATE with correct names
4. Assert returned URL has target db name

**Verifies:** clone_database generates correct CREATE DATABASE ... TEMPLATE SQL

### clone_database rejects invalid names
**File:** tests/unit/test_db_schema.py::TestCloneDatabase::test_invalid_target_name_raises_value_error
1. Call clone_database with "bad-name!" as target
2. Assert ValueError raised

**Verifies:** SQL injection protection via name validation

### clone_database terminates connections first
**File:** tests/unit/test_db_schema.py::TestCloneDatabase::test_terminate_connections_called_before_create
1. Track call order of terminate_connections and execute
2. Call clone_database
3. Assert terminate called before execute

**Verifies:** Active connections are killed before attempting template clone

### clone_database returns correct URL
**File:** tests/unit/test_db_schema.py::TestCloneDatabase::test_returns_url_with_target_name
1. Call clone_database with full URL including asyncpg driver and query params
2. Assert returned URL has target db name, preserves driver and params

**Verifies:** URL construction preserves all components except database name

### drop_database executes DROP DATABASE IF EXISTS
**File:** tests/unit/test_db_schema.py::TestDropDatabase::test_happy_path_drops_database
1. Mock psycopg.connect and terminate_connections
2. Call drop_database
3. Assert SQL contains DROP DATABASE IF EXISTS with correct db name

**Verifies:** drop_database generates correct DROP SQL

### drop_database rejects invalid names
**File:** tests/unit/test_db_schema.py::TestDropDatabase::test_invalid_db_name_in_url_raises_value_error
1. Call drop_database with "bad-name!" in URL
2. Assert ValueError raised

**Verifies:** SQL injection protection on drop path

### drop_database terminates connections first
**File:** tests/unit/test_db_schema.py::TestDropDatabase::test_terminate_connections_called_before_drop
1. Track call order of terminate_connections and execute
2. Call drop_database
3. Assert terminate called before execute

**Verifies:** Active connections are killed before attempting drop

### drop_database uses IF EXISTS for idempotency
**File:** tests/unit/test_db_schema.py::TestDropDatabase::test_idempotent_uses_if_exists
1. Call drop_database on a non-existent database
2. Assert SQL contains IF EXISTS

**Verifies:** Dropping a non-existent database does not raise

## Database Bootstrap Helpers (Integration)

### ensure_database_exists creates missing database
**File:** tests/integration/test_settings_db.py::TestEnsureDatabaseExistsIntegration::test_creates_missing_database
1. Build a URL pointing to a non-existent database (random name)
2. Call `ensure_database_exists(url)`
3. Query `pg_database` to confirm the database was created
4. Cleanup: DROP DATABASE

**Verifies:** AC10.1 -- `ensure_database_exists` creates a real PostgreSQL database when it does not exist

### ensure_database_exists is idempotent
**File:** tests/integration/test_settings_db.py::TestEnsureDatabaseExistsIntegration::test_idempotent_no_error_on_existing
1. Build a URL pointing to a non-existent database (random name)
2. Call `ensure_database_exists(url)` twice
3. Assert no error on second call
4. Cleanup: DROP DATABASE

**Verifies:** AC10.2 -- calling `ensure_database_exists` twice on the same database does not raise

**Overlap note:** These tests were moved from `tests/unit/test_settings.py` to integration because they connect to a real PostgreSQL server.

### clone and drop round-trip
**File:** tests/integration/test_db_cloning.py::test_clone_and_drop_round_trip
1. Clone the test database to a unique target name
2. Verify cloned database exists
3. Verify cloned database has same tables as source
4. Drop the cloned database
5. Verify cloned database no longer exists

**Verifies:** Full clone-from-template and drop lifecycle against real PostgreSQL

### drop is idempotent
**File:** tests/integration/test_db_cloning.py::test_drop_is_idempotent
1. Clone the test database
2. Drop it (first time)
3. Verify it does not exist
4. Drop it again (second time, should not raise)

**Verifies:** Dropping a non-existent database is safe (IF EXISTS)

## CRDT Text Extraction (FTS)

### None crdt_state returns empty string
**File:** tests/unit/test_search_extraction.py::TestExtractSearchableTextNone::test_none_crdt_state_returns_empty_string
1. Call extract_searchable_text with crdt_state=None and empty tag_names
2. Assert result is empty string

**Verifies:** AC8.5 -- None CRDT state is a no-op, returns empty string

### Highlight text included in extraction
**File:** tests/unit/test_search_extraction.py::TestExtractSearchableTextHighlights::test_highlight_text_included
1. Build CRDT state with one highlight containing text "negligence claim"
2. Call extract_searchable_text
3. Assert "negligence claim" appears in result

**Verifies:** Highlighted source text is extracted for FTS indexing

### Multiple highlights all included
**File:** tests/unit/test_search_extraction.py::TestExtractSearchableTextHighlights::test_multiple_highlights_all_included
1. Build CRDT state with two highlights ("first highlight", "second highlight")
2. Call extract_searchable_text
3. Assert both highlight texts appear in result

**Verifies:** All highlights are extracted, not just the first

### Tag UUID resolved to display name
**File:** tests/unit/test_search_extraction.py::TestExtractSearchableTextTagResolution::test_tag_uuid_resolved_to_name
1. Generate a random UUID, build CRDT state with highlight using that UUID as tag
2. Call extract_searchable_text with tag_names mapping UUID to "Jurisdiction"
3. Assert "Jurisdiction" appears in result

**Verifies:** Tag UUIDs are resolved to human-readable names via the tag_names dict

### Unresolved tag passes through as-is
**File:** tests/unit/test_search_extraction.py::TestExtractSearchableTextTagResolution::test_tag_uuid_not_in_tag_names_passes_through
1. Build CRDT state with highlight using tag string "BriefTag:damages"
2. Call extract_searchable_text with empty tag_names
3. Assert "BriefTag:damages" appears in result

**Verifies:** Legacy/unknown tag strings are included verbatim (fallback behaviour)

### Comment text included
**File:** tests/unit/test_search_extraction.py::TestExtractSearchableTextComments::test_comment_text_included
1. Build CRDT state with highlight that has one comment
2. Call extract_searchable_text
3. Assert comment text appears in result

**Verifies:** Comments on highlights are extracted for FTS

### Multiple comments all included
**File:** tests/unit/test_search_extraction.py::TestExtractSearchableTextComments::test_multiple_comments_all_included
1. Build CRDT state with highlight that has two comments
2. Call extract_searchable_text
3. Assert both comment texts appear in result

**Verifies:** All comments on a highlight are extracted, not just the first

### Response draft markdown included
**File:** tests/unit/test_search_extraction.py::TestExtractSearchableTextResponseDraft::test_response_draft_included
1. Build CRDT state with response_draft_markdown content
2. Call extract_searchable_text
3. Assert draft content appears in result

**Verifies:** Response draft (Tab 3) content is indexed

### General notes included
**File:** tests/unit/test_search_extraction.py::TestExtractSearchableTextGeneralNotes::test_general_notes_included
1. Build CRDT state with general_notes content
2. Call extract_searchable_text
3. Assert notes content appears in result

**Verifies:** General notes are indexed

### All sources combined
**File:** tests/unit/test_search_extraction.py::TestExtractSearchableTextCombined::test_all_sources_combined
1. Build CRDT state with highlight (text + tag + comment), general notes, and response draft
2. Call extract_searchable_text with tag_names mapping
3. Assert all five content pieces appear in result

**Verifies:** Extraction combines all annotation content sources into one searchable string

## Navigator Data Loader (Integration)

### Owned workspaces appear in my_work
**File:** tests/integration/test_navigator_loader.py::TestMyWork::test_owned_workspaces_appear
1. Create course/week/activity/student hierarchy
2. Call load_navigator_page for student
3. Filter rows to section="my_work"
4. Assert student's workspace ID is present
5. Assert context columns (activity_title, week_title, course_id, permission="owner")

**Verifies:** AC1.1 -- owned workspaces appear with full context in my_work section

### Template workspaces excluded from my_work
**File:** tests/integration/test_navigator_loader.py::TestMyWork::test_template_excluded_from_my_work
1. Create hierarchy (activity has a template workspace)
2. Call load_navigator_page for student
3. Assert template_workspace_id NOT in my_work rows

**Verifies:** Template workspaces (used for cloning) are invisible in the navigator

### Unstarted activities appear
**File:** tests/integration/test_navigator_loader.py::TestUnstarted::test_unstarted_activities_appear
1. Create published week + activity, enrol student, no workspace created
2. Call load_navigator_page
3. Assert activity appears in section="unstarted"

**Verifies:** AC1.2 -- published activities without a student workspace show as unstarted

### Unpublished activity excluded
**File:** tests/integration/test_navigator_loader.py::TestUnstarted::test_unpublished_activity_excluded
1. Create unpublished activity
2. Call load_navigator_page
3. Assert unpublished activity NOT in unstarted rows

**Verifies:** Unpublished activities are invisible to students

### Future visible_from excluded
**File:** tests/integration/test_navigator_loader.py::TestUnstarted::test_future_visible_from_excluded
1. Create published week with visible_from set to tomorrow
2. Call load_navigator_page
3. Assert future activity NOT in unstarted rows

**Verifies:** Activities with future visible_from dates are hidden

### Started activity not unstarted
**File:** tests/integration/test_navigator_loader.py::TestUnstarted::test_started_activity_not_unstarted
1. Create activity, then create student workspace for that activity
2. Call load_navigator_page
3. Assert activity NOT in unstarted rows (it moved to my_work)

**Verifies:** Once a student creates a workspace, the activity leaves the unstarted section

### Shared editor appears in shared_with_me
**File:** tests/integration/test_navigator_loader.py::TestSharedWithMe::test_shared_editor_appears
1. Create two students; student A owns workspace, grant editor to student B
2. Call load_navigator_page for student B
3. Assert workspace appears in section="shared_with_me" with permission="editor"

**Verifies:** Explicit ACL sharing surfaces workspaces in shared_with_me section

### Student sees peer shared workspaces
**File:** tests/integration/test_navigator_loader.py::TestSharedInUnit::test_student_sees_peer_shared_workspaces
1. Create course with sharing enabled, two students with workspaces shared_with_class=true
2. Call load_navigator_page for student 1
3. Assert student 2's workspace appears in section="shared_in_unit"

**Verifies:** Class-shared peer workspaces visible in shared_in_unit section

### Own workspace excluded from shared_in_unit
**File:** tests/integration/test_navigator_loader.py::TestSharedInUnit::test_student_own_workspace_excluded
1. Create hierarchy with two students sharing
2. Call load_navigator_page for student
3. Assert student's OWN workspace NOT in shared_in_unit rows

**Verifies:** A student never sees their own workspace in the "shared in unit" section

### Sharing disabled excludes peers
**File:** tests/integration/test_navigator_loader.py::TestSharedInUnit::test_sharing_disabled_excludes_peers
1. Create course with allow_sharing=false
2. Call load_navigator_page for non-privileged student
3. Assert shared_in_unit is empty

**Verifies:** Course-level sharing toggle prevents peer visibility

### Instructor sees all student workspaces
**File:** tests/integration/test_navigator_loader.py::TestSharedInUnit::test_instructor_sees_all_student_workspaces
1. Create course with sharing disabled, two students, instructor enrolled
2. Call load_navigator_page for instructor with is_privileged=true
3. Assert all student workspaces appear in shared_in_unit

**Verifies:** Privileged users (instructors) see all student work regardless of sharing settings

### Loose workspace in my_work
**File:** tests/integration/test_navigator_loader.py::TestLooseWorkspaces::test_loose_workspace_in_my_work
1. Create workspace placed in course (not activity), owned by student
2. Call load_navigator_page
3. Assert loose workspace appears in my_work

**Verifies:** Workspaces placed directly in a course (no activity) appear in owner's my_work

### Loose workspace in shared_in_unit for instructor
**File:** tests/integration/test_navigator_loader.py::TestLooseWorkspaces::test_loose_workspace_in_shared_in_unit_for_instructor
1. Create loose workspace shared_with_class, owned by student
2. Call load_navigator_page for instructor (privileged)
3. Assert workspace appears in shared_in_unit

**Verifies:** Loose course-level workspaces appear in peer/instructor views

### Loose workspace hidden when sharing disabled
**File:** tests/integration/test_navigator_loader.py::TestLooseWorkspaces::test_loose_workspace_hidden_when_sharing_disabled
1. Create course with sharing disabled, student's loose workspace shared_with_class
2. Call load_navigator_page for another non-privileged student
3. Assert workspace NOT in shared_in_unit

**Verifies:** Sharing toggle applies to loose workspaces too

### Empty sections produce zero rows
**File:** tests/integration/test_navigator_loader.py::TestEmptySections::test_empty_sections_produce_zero_rows
1. Create a fresh user with no workspaces or enrolments
2. Call load_navigator_page
3. Assert zero rows returned

**Verifies:** AC1.7 -- users with no data get an empty result, no errors

### Multi-course shared_in_unit
**File:** tests/integration/test_navigator_loader.py::TestMultiCourseEnrollment::test_multi_course_shared_in_unit
1. Create two courses, each with students sharing work
2. Enrol an observer in both courses
3. Call load_navigator_page with both enrolled_course_ids
4. Assert shared workspaces from both courses appear

**Verifies:** Multi-course enrolment surfaces peer work across all courses

### Pagination: fewer than limit returns no cursor
**File:** tests/integration/test_navigator_loader.py::TestCursorPagination::test_fewer_than_limit_no_cursor
1. Create fewer workspaces than the limit
2. Call load_navigator_page
3. Assert next_cursor is None

**Verifies:** No pagination cursor when all data fits in one page

### Pagination returns cursor and next page
**File:** tests/integration/test_navigator_loader.py::TestCursorPagination::test_pagination_returns_cursor
1. Create more workspaces than page limit
2. Call load_navigator_page with small limit
3. Assert next_cursor is not None
4. Call again with cursor
5. Assert second page has rows, no overlap with first

**Verifies:** Keyset pagination cursor correctly advances through pages

### Pagination no duplicates
**File:** tests/integration/test_navigator_loader.py::TestCursorPagination::test_pagination_no_duplicates
1. Create many workspaces
2. Paginate through all pages collecting row_ids
3. Assert no duplicates in collected IDs
4. Assert total equals expected count

**Verifies:** AC5.5 -- keyset pagination never produces duplicate rows

### Activity sharing override
**File:** tests/integration/test_navigator_loader.py::TestActivitySharingOverride::test_activity_sharing_false_overrides_course_true
1. Create course with sharing enabled
2. Set activity.allow_sharing = false
3. Call load_navigator_page for non-privileged peer
4. Assert shared_in_unit is empty

**Verifies:** Activity-level allow_sharing=false overrides course-level default

### Scale query performance
**File:** tests/integration/test_navigator_loader.py::TestScaleLoadTest::test_instructor_query_at_scale
1. Skip if no load-test data present
2. Find an instructor enrolled in a course
3. Call load_navigator_page
4. Assert query returns results without timeout

**Verifies:** AC5.5 -- navigator query performs acceptably at scale with load-test data

## FTS Search (Integration)

### search_dirty set on CRDT save
**File:** tests/integration/test_fts_search.py::TestSearchDirtyOnCRDTSave::test_search_dirty_set_on_crdt_save
1. Create workspace
2. Build CRDT state with a highlight, call save_workspace_crdt_state
3. Reload workspace
4. Assert search_dirty is True

**Verifies:** CRDT saves mark workspace for FTS re-extraction

### HTML stripped from document search
**File:** tests/integration/test_fts_search.py::TestFTSHTMLStripping::test_html_stripped_from_document_search
1. Create workspace with HTML document containing "brown fox" inside <b> tags
2. Call search_navigator for "brown fox"
3. Assert workspace appears in results

**Verifies:** HTML tags are stripped by the GIN index expression before FTS matching

### Snippet contains mark tags
**File:** tests/integration/test_fts_search.py::TestFTSSnippetHighlighting::test_snippet_contains_mark_tags
1. Create workspace with document about "negligence"
2. Search for "negligence"
3. Assert snippet contains <mark> and </mark> tags

**Verifies:** ts_headline wraps matched terms in <mark> for UI highlighting

### Two-char query returns empty
**File:** tests/integration/test_fts_search.py::TestFTSShortQueryGuard::test_two_char_query_returns_empty
1. Call search_navigator with query "ab" (2 chars)
2. Assert empty result list

**Verifies:** Short query guard rejects queries under 3 characters

### Whitespace-only query returns empty
**File:** tests/integration/test_fts_search.py::TestFTSShortQueryGuard::test_whitespace_only_query_returns_empty
1. Call search_navigator with query "   " (whitespace only)
2. Assert empty result list

**Verifies:** Whitespace-only queries are rejected

### Empty query returns empty
**File:** tests/integration/test_fts_search.py::TestFTSShortQueryGuard::test_empty_query_returns_empty
1. Call search_navigator with empty string
2. Assert empty result list

**Verifies:** Empty string queries are rejected

### Empty content no error
**File:** tests/integration/test_fts_search.py::TestFTSEmptyContent::test_empty_content_no_error
1. Create workspace with empty document content
2. Search for "anything"
3. Assert workspace NOT in results (no error thrown)

**Verifies:** AC8.5 -- empty documents produce valid empty tsvectors, no SQL errors

### Document content match returns snippet
**File:** tests/integration/test_fts_search.py::TestFTSContentMatches::test_search_returns_snippet_for_document
1. Create workspace with document about "duty of care"
2. Search for "duty of care"
3. Assert matching result with non-empty snippet

**Verifies:** FTS returns results with snippets for document content matches

### CRDT search_text match
**File:** tests/integration/test_fts_search.py::TestFTSContentMatches::test_search_crdt_search_text
1. Create workspace with unrelated document content but search_text about "statute of limitations"
2. Search for "statute limitations"
3. Assert workspace found via search_text field

**Verifies:** FTS searches both workspace_document.content AND workspace.search_text

### Malformed query handled gracefully
**File:** tests/integration/test_fts_search.py::TestFTSMalformedQuery::test_malformed_query_no_error
1. Create workspace with legal content
2. Search for "legal &" (trailing operator)
3. Assert results returned, no SQL error

**Verifies:** _build_prefix_query strips non-word characters, gracefully handles malformed input

### ACL restricts search results
**File:** tests/integration/test_fts_search.py::TestFTSACLRestriction::test_other_users_workspaces_not_visible
1. User A creates workspace with "negligence"
2. User B creates workspace with "negligence"
3. Search as User A for "negligence"
4. Assert User A's workspace in results, User B's workspace NOT in results

**Verifies:** FTS search is ACL-scoped -- users only see their own visible workspaces

### More matches rank higher
**File:** tests/integration/test_fts_search.py::TestFTSRelevanceOrdering::test_more_matches_rank_higher
1. User creates workspace 1 with "negligence" once
2. User creates workspace 2 with "negligence" repeated 4 times
3. Search for "negligence"
4. Assert workspace 2 ranks before workspace 1 in results

**Verifies:** ts_rank orders results by relevance (more term occurrences = higher rank)

### NULL search_text no error
**File:** tests/integration/test_fts_search.py::TestFTSNullSearchText::test_null_search_text_no_error
1. Create workspace with document content but search_text left as NULL
2. Search for unrelated term
3. Assert no error, workspace not in results

**Verifies:** NULL search_text handled via COALESCE in index expression, no SQL errors

### Metadata search by owner display name
**File:** tests/integration/test_fts_search.py::TestMetadataSearchOwnerName::test_search_by_owner_display_name
1. Create workspace with full hierarchy, owner display name "Bartholomew Greenfield"
2. Search for "Bartholomew"
3. Assert workspace found

**Verifies:** AC1.1 -- metadata FTS leg matches owner display name

### Metadata search by activity title
**File:** tests/integration/test_fts_search.py::TestMetadataSearchActivityTitle::test_search_by_activity_title
1. Create workspace with activity title "Contractual Obligations Analysis"
2. Search for "Contractual Obligations"
3. Assert workspace found

**Verifies:** AC2.1 -- metadata FTS leg matches activity title

### Metadata search by week title
**File:** tests/integration/test_fts_search.py::TestMetadataSearchWeekTitle::test_search_by_week_title
1. Create workspace with week title "Foundations of Tort"
2. Search for "Foundations Tort"
3. Assert workspace found

**Verifies:** AC3.1 -- metadata FTS leg matches week title

### Metadata search by course code
**File:** tests/integration/test_fts_search.py::TestMetadataSearchCourseCode::test_search_by_course_code
1. Create workspace with course code "LAWS3100"
2. Search for "LAWS3100"
3. Assert workspace found

**Verifies:** AC4.1 -- metadata FTS leg matches course code

### Metadata search by course name
**File:** tests/integration/test_fts_search.py::TestMetadataSearchCourseName::test_search_by_course_name
1. Create workspace with course name "Environmental Regulation"
2. Search for "Environmental Regulation"
3. Assert workspace found

**Verifies:** AC5.1 -- metadata FTS leg matches course name

### Metadata search by workspace title
**File:** tests/integration/test_fts_search.py::TestMetadataSearchWorkspaceTitle::test_search_by_workspace_title
1. Create workspace with title "Jurisprudential Analysis Portfolio"
2. Search for "Jurisprudential Analysis"
3. Assert workspace found

**Verifies:** Metadata FTS leg matches workspace title

### Metadata snippet has mark tags
**File:** tests/integration/test_fts_search.py::TestMetadataSearchSnippetHighlight::test_metadata_snippet_has_mark_tags
1. Create workspace with course code "LAWS3100"
2. Search for "LAWS3100"
3. Assert snippet contains <mark> and </mark> tags

**Verifies:** AC6.1 -- metadata hit snippets use ts_headline with <mark> highlighting

### Metadata snippet shows author label
**File:** tests/integration/test_fts_search.py::TestMetadataSearchSnippetLabelled::test_snippet_shows_author_label
1. Create workspace with unique owner display name
2. Search for owner name
3. Assert snippet contains "Author:" label

**Verifies:** Metadata snippets include field labels for context

### Metadata snippet shows unit label
**File:** tests/integration/test_fts_search.py::TestMetadataSearchSnippetLabelled::test_snippet_shows_unit_label
1. Create workspace with course code "XYZQ9999"
2. Search for "XYZQ9999"
3. Assert snippet contains "Unit:" label

**Verifies:** Metadata snippets include "Unit:" label (not "Course:")

### Prefix matches course code
**File:** tests/integration/test_fts_search.py::TestPrefixMatchCourseCode::test_prefix_matches_course_code
1. Create workspace with course code "LAWS3100"
2. Search for "LAWS" (prefix only)
3. Assert workspace found

**Verifies:** Prefix matching via :* suffix enables partial course code search

### Numeric suffix matches course code
**File:** tests/integration/test_fts_search.py::TestPrefixMatchCourseCode::test_numeric_suffix_matches_course_code
1. Create workspace with course code "ZZQX7742"
2. Search for "7742" (numeric part only)
3. Assert workspace found

**Verifies:** regexp_replace splits course codes (ZZQX7742 -> ZZQX + 7742) for partial matching

### Orphan workspace searchable by title
**File:** tests/integration/test_fts_search.py::TestMetadataSearchOrphanWorkspace::test_orphan_workspace_found_by_title
1. Create workspace with title but no activity/week/course hierarchy
2. Search for workspace title
3. Assert workspace found

**Verifies:** AC9.1 -- orphan workspaces (no activity) still appear in metadata search via title

### Document content still searchable alongside metadata
**File:** tests/integration/test_fts_search.py::TestMetadataSearchRegressionDocumentContent::test_document_content_still_searchable
1. Create workspace with full hierarchy and document about "promissory estoppel"
2. Search for "promissory estoppel"
3. Assert workspace found

**Verifies:** AC7.1 -- adding metadata leg does not break existing document content search

### CRDT search_text still searchable alongside metadata
**File:** tests/integration/test_fts_search.py::TestMetadataSearchRegressionCRDTSearchText::test_crdt_search_text_still_searchable
1. Create workspace with search_text about "quantum meruit restitution"
2. Search for "quantum meruit"
3. Assert workspace found

**Verifies:** AC7.2 -- adding metadata leg does not break existing CRDT search_text search

### Metadata search latency at scale
**File:** tests/integration/test_fts_search.py::TestMetadataSearchPerformance::test_metadata_search_latency_at_scale
1. Skip if fewer than 1000 workspaces in database
2. Find a privileged staff user with enrollments
3. Search for "LAWS" prefix as privileged user
4. Assert results returned in under 2 seconds

**Verifies:** Metadata search performs acceptably at 1k-workspace scale without GIN index

### Privileged user sees unshared peer workspace
**File:** tests/integration/test_fts_search.py::TestFTSACLRestriction::test_privileged_sees_unshared_peer_workspace
1. Create instructor and student in same course
2. Student creates workspace with "tortfeasor" content, NOT shared
3. Non-privileged instructor searches -- assert workspace NOT visible
4. Privileged instructor searches -- assert workspace visible

**Verifies:** Privileged users bypass sharing restrictions in FTS search (consistent with navigator ACL)

## Load-Test CRDT Tag Validity (Integration)

### Highlight tags are valid UUIDs
**File:** tests/integration/test_loadtest_crdt_validity.py::TestLoadtestCrdtTagValidity::test_highlight_tags_are_valid_uuids
1. Create workspace, seed tags, build CRDT state via build_crdt_state
2. Deserialise CRDT, get all highlights
3. For each highlight, parse tag value as UUID
4. Assert round-trip (str -> UUID -> str) matches

**Verifies:** build_crdt_state stores UUID strings (not tag names) in highlight tag fields

### Highlight tag UUIDs are from seed
**File:** tests/integration/test_loadtest_crdt_validity.py::TestLoadtestCrdtTagValidity::test_highlight_tag_uuids_are_from_seed
1. Build CRDT fixture (workspace + seeded tags + highlights)
2. Collect tag_ids from seed
3. For each highlight, assert tag value is in seeded tag_id set

**Verifies:** All tag UUIDs in highlights came from _seed_tags_for_template, not fabricated

### Highlight tag UUIDs exist in database
**File:** tests/integration/test_loadtest_crdt_validity.py::TestLoadtestCrdtTagValidity::test_highlight_tag_uuids_exist_in_database
1. Build CRDT fixture
2. Query Tag table for workspace's tags
3. Assert every highlight tag UUID exists as a row in the database

**Verifies:** Tag UUIDs in CRDT highlights reference real Tag rows (foreign key integrity)

## I18n Configuration (Unit)

### Default unit_label is "Unit"
**File:** tests/unit/test_config.py::TestI18nConfig::test_default_unit_label_is_unit
1. Clear environment and create Settings
2. Assert settings.i18n.unit_label == "Unit"

**Verifies:** The i18n unit_label defaults to "Unit" (Australian terminology)

### Override unit_label
**File:** tests/unit/test_config.py::TestI18nConfig::test_override_unit_label
1. Create I18nConfig with unit_label="Course"
2. Assert unit_label == "Course"

**Verifies:** I18nConfig accepts custom unit_label values

### Override via environment variable
**File:** tests/unit/test_config.py::TestI18nConfig::test_override_via_settings
1. Set I18N__UNIT_LABEL="Subject" in environment
2. Create Settings
3. Assert settings.i18n.unit_label == "Subject"

**Verifies:** Unit label is configurable via nested environment variable

## Navigator (E2E)

### Unauthenticated redirect
**File:** tests/e2e/test_navigator.py::TestNavigator::test_unauthenticated_redirect
1. Navigate to / without authentication
2. Assert redirect to /login

**Verifies:** AC2.5 -- unauthenticated access redirects to login

### My Work section renders with owned workspace
**File:** tests/e2e/test_navigator.py::TestNavigator::test_navigator_renders_my_work
1. Authenticate as student, create owned workspace via DB
2. Navigate to /
3. Assert "My Work" section header visible
4. Assert workspace entry visible with data-workspace-id attribute
5. Assert empty sections ("Unstarted Work", "Shared With Me") absent
6. Click workspace title, assert navigation to /annotation?workspace_id=...
7. Navigate back, click action button, assert same navigation

**Verifies:** AC1.1, AC1.7, AC2.1, AC2.2 -- My Work section renders, empty sections hidden, clicks navigate

### Unstarted Work section renders
**File:** tests/e2e/test_navigator.py::TestNavigator::test_navigator_renders_unstarted_work
1. Instructor creates course with published activity via UI
2. Student is enrolled
3. Student navigates to /
4. Assert "Unstarted Work" section header visible
5. Assert activity title visible
6. Assert Start button visible

**Verifies:** AC1.2 -- enrolled students see published activities they haven't started

### Start button clones and navigates
**File:** tests/e2e/test_navigator.py::TestNavigator::test_start_activity_clones_and_navigates
1. Instructor creates course with published activity + template
2. Student navigates to /
3. Click Start on unstarted activity
4. Assert navigation to /annotation?workspace_id=...
5. Navigate back to /
6. Assert activity now under "My Work", not "Unstarted Work"

**Verifies:** AC2.3 -- Start clones template, navigates to annotation, moves activity to My Work

### Search filters and restores
**File:** tests/e2e/test_navigator.py::TestNavigator::test_search_filters_and_restores
1. Create two workspaces with unique marker content
2. Navigate to /
3. Type 2-char query -- assert no filtering (both visible)
4. Type full marker matching one workspace -- assert only match visible with snippet
5. Clear search -- assert full unfiltered view returns
6. Type nonsense query -- assert "No workspaces match" message
7. Click "Clear search" -- assert full view returns

**Verifies:** AC3.2, AC3.5, AC3.6, AC8.4 -- search debounce, filtering, restore, empty state

### Inline title rename
**File:** tests/e2e/test_navigator.py::TestNavigator::test_inline_title_rename
1. Create owned workspace, navigate to /
2. Click pencil icon -- assert URL unchanged (AC4.5)
3. Assert input switches to editable/outlined mode (AC4.1)
4. Type new title, press Escape -- assert revert (AC4.3)
5. Type new title, press Enter -- assert save (AC4.2)
6. Refresh page -- assert title persists
7. Type title, blur -- assert save on blur (AC4.2)

**Verifies:** AC4.1-AC4.3, AC4.5 -- inline title editing with save/revert/persist

### Default title on start
**File:** tests/e2e/test_navigator.py::TestNavigator::test_default_title_on_start
1. Instructor creates course with activity titled "Annotate Becky Bennett"
2. Student clicks Start
3. Navigate back to /
4. Assert workspace title input value equals activity title

**Verifies:** AC4.4 -- cloned workspace defaults its title to the activity name

### Infinite scroll loads more rows
**File:** tests/e2e/test_navigator.py::TestNavigator::test_infinite_scroll_loads_more_rows
1. Create 60 workspaces for one user
2. Navigate to / -- assert initial load is 40-50 entries
3. Scroll to bottom -- assert more entries loaded
4. Assert no duplicate workspace IDs
5. Keep scrolling -- assert all 60 rows eventually loaded

**Verifies:** AC5.1, AC5.2, AC5.5 -- keyset pagination via infinite scroll, no duplicates

### No extra load under 50
**File:** tests/e2e/test_navigator.py::TestNavigator::test_infinite_scroll_no_extra_load_under_50
1. Create 10 workspaces
2. Navigate to / -- assert all 10 visible
3. Scroll to bottom -- assert count unchanged

**Verifies:** AC5.4 -- no spurious pagination when all data fits in one page

### Pagination disabled during search
**File:** tests/e2e/test_navigator.py::TestNavigator::test_pagination_disabled_during_search
1. Create 60 workspaces (57 generic + 3 with marker)
2. Type marker in search -- assert 3 or fewer results
3. Scroll to bottom during search -- assert no extra rows loaded
4. Clear search -- assert paginated view restores (40-50 entries)
5. Scroll after clear -- assert pagination resumes (more rows loaded)

**Verifies:** AC5.2 -- search replaces pagination; clearing search restores it

### Annotation home icon navigates to navigator
**File:** tests/e2e/test_navigator.py::TestNavigationChrome::test_annotation_home_icon_navigates_to_navigator
1. Authenticate, create workspace, navigate to /annotation page
2. Find home button (role="button", name="home")
3. Click home button
4. Assert navigation to /

**Verifies:** AC6.1 -- home icon on annotation tab bar returns to navigator

### Annotation page has no global header bar
**File:** tests/e2e/test_navigator.py::TestNavigationChrome::test_annotation_no_global_header_bar
1. Navigate to annotation page
2. Assert home button is visible and has q-btn--flat class
3. Assert tabs still exist and are visible

**Verifies:** AC6.3 -- home icon is a small flat button, not an intrusive header bar

### Roleplay nav drawer Home navigates to navigator
**File:** tests/e2e/test_navigator.py::TestNavigationChrome::test_roleplay_home_icon_navigates_to_navigator
1. Skip if roleplay feature flag is disabled
2. Authenticate, navigate to /roleplay
3. Open nav drawer via header menu button (if not already visible)
4. Click "Home" nav item in drawer
5. Assert navigation to /

**Verifies:** AC6.2 -- nav drawer Home link on roleplay page returns to navigator (roleplay now uses shared page_layout)

### Courses home icon navigates to navigator
**File:** tests/e2e/test_navigator.py::TestNavigationChrome::test_courses_home_icon_navigates_to_navigator
1. Navigate to /courses
2. Click home button
3. Assert navigation to /

**Verifies:** AC6.2 -- home icon on courses page returns to navigator

### Navigator displays "Unit" not "Course"
**File:** tests/e2e/test_navigator.py::TestI18nTerminology::test_navigator_displays_unit_not_course
1. Authenticate, navigate to /
2. Extract all visible text from page body
3. Search for "Course" or "Courses" (case-sensitive, word boundary)
4. Assert no matches found

**Verifies:** AC7.1 -- no user-facing text on navigator contains "Course" (uses "Unit" per AU convention)

## Documentation Generation (make-docs CLI)

### Server starts with mock auth and a free port
**File:** tests/unit/test_make_docs.py::TestMakeDocsServerLifecycle::test_make_docs_starts_server_with_mock_auth
1. Delete DEV__AUTH_MOCK from environment
2. Patch all external dependencies (shutil.which, server start/stop, subprocess.run)
3. Capture environment state at the moment _start_e2e_server is called
4. Call make_docs()
5. Assert _start_e2e_server called once with an integer port > 0
6. Assert DEV__AUTH_MOCK was "true" at the time the server started

**Verifies:** AC1.1 -- make_docs sets mock auth before starting the E2E server on a random free port

### Capture scripts receive base URL
**File:** tests/unit/test_make_docs.py::TestMakeDocsServerLifecycle::test_make_docs_invokes_scripts_with_base_url
1. Patch all external dependencies for happy path
2. Call make_docs()
3. Filter subprocess.run calls for those containing "generate-"
4. Assert at least 2 script calls
5. Assert each script call includes "http://localhost:<port>" as an argument

**Verifies:** AC1.1 -- both capture scripts are invoked with the server's base URL

### Script failure reports context
**File:** tests/unit/test_make_docs.py::TestMakeDocsErrorReporting::test_make_docs_error_reports_script_name_and_context
1. Patch all external dependencies; make bash calls fail with stderr containing wait_for context
2. Call make_docs(), expect SystemExit
3. Assert output includes the failing script name ("generate-instructor-setup.sh")
4. Assert output includes the wait_for failure context message

**Verifies:** AC1.6 -- script failures report which script failed and include diagnostic context

## Empty-Tag Annotation UX (E2E)

### Zero-tag workspace shows "+ New" button and tooltip
**File:** tests/e2e/test_empty_tag_ux.py::TestEmptyTagFloatingMenu::test_zero_tag_new_button_and_tooltip
1. Create workspace with content but no tags (owner has tag creation permission)
2. Navigate to annotation page, wait for text walker
3. Select text in document
4. Assert floating highlight menu shows "+ New" button (AC1.1)
5. Assert "No tags available" label is NOT present
6. Hover "+ New" button, assert tooltip "Create a new tag and apply it to your selection" (AC3.1)
7. Click "+ New", cancel quick-create dialog
8. Assert no annotation card was created (AC1.5 -- cancel produces no highlight)

**Verifies:** AC1.1 (new button in zero-tag workspace), AC1.5 (cancel creates no highlight), AC3.1 (tooltip on new button)

### Create tag via "+ New" and verify alongside existing tags
**File:** tests/e2e/test_empty_tag_ux.py::TestEmptyTagFloatingMenu::test_create_tag_and_alongside_existing
1. Create zero-tag workspace, navigate to annotation page
2. Select text, click "+ New" in floating menu
3. Fill tag name "TestTag" in quick-create dialog, click Create
4. Assert annotation card appears (AC1.2 -- tag created and highlight applied)
5. Clear selection, re-select different text
6. Assert floating menu shows both tag buttons AND "+ New" button (AC1.3)

**Verifies:** AC1.2 (new button creates tag and applies highlight), AC1.3 (new button alongside existing tag buttons)

### No-permission dead end
**File:** tests/e2e/test_empty_tag_ux.py::TestEmptyTagNoPermission::test_no_tags_no_permission_shows_dead_end
1. Create workspace under activity with tag creation disabled (course default_allow_tag_creation=False)
2. User has editor permission (can annotate but not create tags)
3. Select text in document
4. Assert "No tags available" label is visible (AC1.4)
5. Assert "+ New" button is NOT attached to DOM
6. Hover "No tags available" label, assert tooltip "Ask your instructor" (AC1.4)

**Verifies:** AC1.4 (dead-end message when user lacks tag creation permission)

### Expanded toolbar labels at zero tags
**File:** tests/e2e/test_empty_tag_ux.py::TestToolbarExpandedLabels::test_expanded_labels_at_zero_tags
1. Create zero-tag workspace, navigate to annotation page
2. Assert create button shows "Create New Tag" text (AC2.1)
3. Assert manage button shows "Manage Tags" text (AC2.2)

**Verifies:** AC2.1 (create button label), AC2.2 (manage button label) below compact threshold

### Compact buttons at 5+ tags
**File:** tests/e2e/test_empty_tag_ux.py::TestToolbarExpandedLabels::test_compact_buttons_at_five_plus_tags
1. Create workspace with 10 seeded tags, navigate to annotation page
2. Assert create button does NOT contain "Create New Tag" text (AC2.3)
3. Assert manage button does NOT contain "Manage Tags" text (AC2.3)

**Verifies:** AC2.3 (compact icon-only buttons at or above threshold)

### Live transition to compact on 5th tag creation
**File:** tests/e2e/test_empty_tag_ux.py::TestToolbarExpandedLabels::test_transition_to_compact_on_fifth_tag
1. Create zero-tag workspace, navigate to annotation page
2. Create 4 tags via toolbar create button + quick-create dialog
3. Assert buttons still show expanded labels ("Create New Tag", "Manage Tags")
4. Create 5th tag
5. Assert buttons switched to compact (no text labels) (AC2.4)

**Verifies:** AC2.4 (live rebuild triggers compact style at threshold)

### Tooltips at zero tags
**File:** tests/e2e/test_empty_tag_ux.py::TestToolbarTooltips::test_tooltips_at_zero_tags
1. Create zero-tag workspace, navigate to annotation page
2. Hover create button, assert tooltip "Create a new tag for highlighting and annotating text" (AC3.2)
3. Hover manage button, assert tooltip "Manage tags -- create, edit, reorder, and import tags" (AC3.3)

**Verifies:** AC3.2 (create tooltip), AC3.3 (manage tooltip) at zero tags

### Tooltips at 5+ tags
**File:** tests/e2e/test_empty_tag_ux.py::TestToolbarTooltips::test_tooltips_at_five_plus_tags
1. Create workspace with 10 seeded tags, navigate to annotation page
2. Hover create button, assert tooltip visible (AC3.2 at 5+)
3. Hover manage button, assert tooltip visible (AC3.3 at 5+)

**Verifies:** AC3.4 (tooltips display at all tag counts, including compact mode)
## Platform Handler -- OpenRouter (Unit)

### Matches OpenRouter HTML with playground-container
**File:** tests/unit/export/platforms/test_openrouter.py::TestOpenRouterHandlerMatches::test_matches_openrouter_html_with_playground_container
1. Create OpenRouterHandler
2. Pass HTML containing `data-testid="playground-container"`
3. Assert matches() returns True

**Verifies:** Handler detects OpenRouter by its unique data-testid attribute

### Does not match other platform HTML
**File:** tests/unit/export/platforms/test_openrouter.py::TestOpenRouterHandlerMatches::test_does_not_match_*
1. Create OpenRouterHandler
2. Pass Claude, OpenAI, Gemini, ChatCraft, and empty HTML
3. Assert matches() returns False for each

**Verifies:** No false positives against other platform exports

### Removes playground composer
**File:** tests/unit/export/platforms/test_openrouter.py::TestOpenRouterHandlerPreprocess::test_removes_playground_composer
1. Build HTML with playground-container, messages, and playground-composer
2. Call preprocess()
3. Assert "playground-composer" and textarea content are gone

**Verifies:** Input area chrome is stripped

### Strips assistant message metadata (timestamp, model link, actions)
**File:** tests/unit/export/platforms/test_openrouter.py::TestOpenRouterHandlerPreprocess::test_strips_timestamp_from_assistant_messages, test_strips_model_link_from_assistant_messages, test_strips_actions_from_assistant_messages
1. Build realistic assistant-message HTML with 4 child divs (timestamp, model link, content wrapper, actions)
2. Call preprocess()
3. Assert timestamp ("21 hours ago"), model link ("openrouter.ai"), and action children are removed
4. Assert only the content wrapper's last child (response div) remains

**Verifies:** All non-content metadata is stripped from assistant turns

### Strips thinking content
**File:** tests/unit/export/platforms/test_openrouter.py::TestOpenRouterHandlerPreprocess::test_strips_thinking_content
1. Build assistant-message with thinking div and response div inside content wrapper
2. Call preprocess()
3. Assert "Thinking Process" and thinking text are gone, response text remains

**Verifies:** Reasoning/thinking blocks are removed, only final response kept

### Sets data-speaker-name from model link URL
**File:** tests/unit/export/platforms/test_openrouter.py::TestOpenRouterHandlerPreprocess::test_sets_data_speaker_name_from_model_link, test_sets_data_speaker_name_with_trailing_slash
1. Build assistant-message with model link href containing slug (e.g. "qwen/qwen3.5-35b-a3b")
2. Call preprocess()
3. Assert data-speaker-name attribute equals the model name portion ("qwen3.5-35b-a3b")
4. Repeat with trailing slash in URL

**Verifies:** Model identity is preserved for CSS label override

### Turn markers match data-testid attributes
**File:** tests/unit/export/platforms/test_openrouter.py::TestOpenRouterHandlerTurnMarkers
1. Get turn markers from handler
2. Assert "user" and "assistant" keys exist
3. Apply each regex to matching HTML; assert match found

**Verifies:** Regex patterns correctly identify user and assistant turns

## Platform Handler -- ChatCraft (Unit)

### Matches ChatCraft HTML requiring both signals
**File:** tests/unit/export/platforms/test_chatcraft.py::TestChatCraftHandlerMatches
1. Create ChatCraftHandler
2. Pass HTML with both chakra-card class AND chatcraft.org text -- assert True
3. Pass HTML with only chakra-card (no chatcraft.org) -- assert False
4. Pass HTML with only chatcraft.org text (no chakra-card) -- assert False
5. Pass Claude, OpenAI, OpenRouter, empty HTML -- assert False for each

**Verifies:** Two-signal detection prevents false positives from other Chakra UI apps

### Preprocess removes chrome and injects speaker attributes
**File:** tests/unit/export/platforms/test_chatcraft.py::TestChatCraftHandlerPreprocess
1. Build HTML with accordion item, form, menu item, and three chakra-cards (user "Alice Smith", assistant "claude-sonnet-4", system "System Prompt")
2. Call preprocess()
3. Assert accordion, form, and menu items are removed
4. Assert cards have data-speaker attributes: ["user", "assistant", "system"]
5. Assert cards have data-speaker-name attributes: ["Alice Smith", "claude-sonnet-4", "System Prompt"]
6. Assert card headers (name, date, avatar) are removed
7. Assert card body content is preserved

**Verifies:** Chrome is stripped, speaker roles classified correctly, identity preserved

### Speaker classification heuristic
**File:** tests/unit/export/platforms/test_chatcraft.py::TestClassifySpeaker
1. "System Prompt" -> "system" (exact match)
2. "claude-sonnet-4", "gpt-4", "qwen3.5-35B-A3B" -> "assistant" (hyphens, no spaces)
3. "Alice Smith" -> "user" (spaces)
4. "ChatCraft" -> "user" (single word, no hyphen)
5. "" -> "user" (fallback)

**Verifies:** Heuristic: hyphens-no-spaces = model = assistant; spaces = human = user; "System Prompt" = system

### Turn markers include system role
**File:** tests/unit/export/platforms/test_chatcraft.py::TestChatCraftHandlerTurnMarkers
1. Get turn markers from handler
2. Assert "user", "assistant", and "system" keys exist
3. Apply each regex to matching HTML; assert match found

**Verifies:** ChatCraft is the only handler declaring all three roles including system

## Platform Handler -- OpenAI (Unit)

### Matches OpenAI HTML with agent-turn class
**File:** tests/unit/export/platforms/test_openai.py::TestOpenAIHandlerMatches
1. Pass HTML with `class="agent-turn"` -- assert True
2. Pass HTML with agent-turn among multiple classes -- assert True
3. Pass Claude HTML, empty HTML -- assert False

**Verifies:** Detection by agent-turn class, no false positives

### Preprocess strips sr-only, badges, and tool-use buttons
**File:** tests/unit/export/platforms/test_openai.py::TestOpenAIHandlerPreprocess
1. Build HTML with sr-only elements ("You said:", "ChatGPT"), model request badge ("Request for GPT-5 Pro"), reasoning badge ("Reasoned for 8m 11s"), and tool-use buttons ("Analyzed", "Analysis errored")
2. Call preprocess()
3. Assert all metadata removed, conversation content preserved

**Verifies:** OpenAI-specific chrome (labels, badges, tool buttons) is stripped

### Turn markers use data-message-author-role
**File:** tests/unit/export/platforms/test_openai.py::TestOpenAIHandlerTurnMarkers
1. Get turn markers, verify user and assistant keys reference data-message-author-role
2. Apply regex to sample HTML, assert matches

**Verifies:** Regex correctly identifies OpenAI turn boundaries

## Platform Handler -- AI Studio (Unit)

### Matches AI Studio HTML with ms-chat-turn element
**File:** tests/unit/export/platforms/test_aistudio.py::TestAIStudioHandlerMatches
1. Pass HTML with `<ms-chat-turn>` element -- assert True
2. Pass with attributes on element -- assert True
3. Pass Gemini HTML, empty HTML -- assert False

**Verifies:** Detection by custom element, no false positives

### Preprocess strips metadata and virtual scroll spacers
**File:** tests/unit/export/platforms/test_aistudio.py::TestAIStudioHandlerPreprocess
1. Build HTML with author labels, file chunks (filenames/token counts), thought chunks, toolbar, token counts, virtual scroll spacer divs, and chat-turn-options
2. Call preprocess() for each
3. Assert all metadata removed, conversation content preserved
4. Virtual scroll spacers (empty divs with fixed pixel heights) specifically removed

**Verifies:** AI Studio chrome is stripped including virtual-scrolling artefacts

### Turn markers use data-turn-role with "User"/"Model" values
**File:** tests/unit/export/platforms/test_aistudio.py::TestAIStudioHandlerTurnMarkers
1. Get turn markers, verify user/assistant keys reference data-turn-role
2. Apply regex to sample HTML with "User" and "Model" values, assert matches

**Verifies:** Regex correctly identifies AI Studio turn boundaries (note: "Model" not "Assistant")

## Platform Handler -- Registry (Unit)

### Autodiscovery finds all 8 handlers
**File:** tests/unit/export/platforms/test_registry.py::TestDiscoverHandlers
1. Import _handlers from platforms package
2. Assert each named handler exists: openai, claude, gemini, aistudio, scienceos, wikimedia, openrouter, chatcraft
3. Assert total count is exactly 8

**Verifies:** Autodiscovery finds every handler module in the package

### get_handler dispatches correctly
**File:** tests/unit/export/platforms/test_registry.py::TestGetHandler
1. Pass OpenAI HTML -- assert handler.name == "openai"
2. Pass Claude HTML -- assert handler.name == "claude"
3. Pass unknown/empty HTML -- assert returns None

**Verifies:** Detection dispatches to correct handler, unknown HTML returns None

### preprocess_for_export end-to-end
**File:** tests/unit/export/platforms/test_registry.py::TestPreprocessForExport
1. Process OpenAI HTML -- assert sr-only removed, content preserved
2. Process unknown HTML -- assert content unchanged (graceful degradation)
3. Use platform_hint="claude" on OpenAI HTML -- assert Claude handler used (sr-only preserved)
4. Use invalid platform_hint -- assert warning logged, falls back to autodiscovery
5. Use mock 3-role handler -- assert data-speaker divs injected for all three roles
6. Use mock handler with unsafe role name ("invalid role!") -- assert ValueError
7. Use mock handler with uppercase role name -- assert ValueError

**Verifies:** Entry point handles detection, hint override, fallback, multi-role injection, and role name sanitisation

### All handlers implement PlatformHandler protocol
**File:** tests/unit/export/platforms/test_registry.py::TestPlatformHandlerProtocol
1. Iterate all registered handlers
2. Assert each is instance of PlatformHandler protocol
3. Assert each has name, matches, preprocess, get_turn_markers
4. Assert handler.name matches its registry key

**Verifies:** Protocol compliance and registry consistency

## Platform Handler -- Role Styling Coverage (Unit Guard)

### Every handler role has CSS, LaTeX, and Lua styling
**File:** tests/unit/export/platforms/test_role_coverage.py::TestRoleStylingCoverage
1. Collect all role names from all registered handlers' get_turn_markers()
2. For each role, read css.py, .sty file, and libreoffice.lua
3. Assert CSS has `[data-speaker="<role>"]` selector
4. Assert .sty has `{<role>turn}` environment definition
5. Assert Lua has `env = '<role>turn'` in speaker_roles table

**Verifies:** Adding a new role without all three styling definitions will fail CI

### Unknown role raises AssertionError
**File:** tests/unit/export/platforms/test_role_coverage.py::TestNegativeCoverage
1. Pass "unknown_role" to the assertion helper with real file contents
2. Assert AssertionError is raised

**Verifies:** The guard helper actually catches missing styling (not vacuously passing)

## System Turn LaTeX Definitions (Unit Guard)

### systemcolor and systemturn defined in .sty
**File:** tests/unit/export/test_sty_system_turn.py::TestSystemTurnLatexDefinitions
1. Read promptgrimoire-export.sty content
2. Assert `\definecolor{systemcolor}{HTML}{E65100}` exists
3. Assert systemcolor appears after assistantcolor
4. Assert `{systemturn}` environment exists
5. Assert systemturn uses `linecolor=systemcolor`
6. Assert systemturn appears after assistantturn

**Verifies:** System turn has correct LaTeX styling with orange colour, defined after assistant definitions

## Annotation CSS Speaker Rules (Unit Guard)

### Speaker CSS rules exist for user, assistant, and system
**File:** tests/unit/test_annotation_css.py::TestSpeakerCssRules
1. Import _PAGE_CSS from annotation css module
2. Assert `[data-speaker="user"]::before` exists with blue colour (#1a5f7a)
3. Assert `[data-speaker="assistant"]::before` exists with green colour (#2e7d32)
4. Assert `[data-speaker="system"]::before` exists with orange colour (#e65100)
5. Assert system label content is "System:"
6. Assert system colour is distinct from user and assistant
7. Assert system background is light amber (#fff3e0)

**Verifies:** All three speaker roles have distinct, visible CSS pseudo-element labels

## Chatbot Fixture Integration (Integration -- modified)

### ChatCraft system label appears in LaTeX output
**File:** tests/integration/test_chatbot_fixtures.py::TestChatbotConversationFixtures::test_system_label_in_chatcraft_latex
1. Load chatcraft_prd.html fixture
2. Run through preprocess_for_export
3. Convert to LaTeX via Pandoc pipeline
4. Assert "System:" label appears in LaTeX output

**Verifies:** AC3.7 -- system prompt cards produce System: labels end-to-end through the full pipeline

### OpenRouter and ChatCraft fixtures in marker injection test
**File:** tests/integration/test_chatbot_fixtures.py (FIXTURES_WITH_MARKERS list)
1. openrouter_fizzbuzz.html and chatcraft_prd.html added to fixture list
2. Both run through the existing parametrised marker injection integration test

**Verifies:** New fixtures produce data-speaker markers in LaTeX output

## Paragraph Map Builder (Unit)

### Auto-numbered paragraphs get sequential numbers
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestAutoNumberParagraphs::test_ac1_1_simple_paragraphs
1. Build paragraph map from `<p>First</p><p>Second</p><p>Third</p>` with auto_number=True
2. Assert 3 entries with values [1, 2, 3]
3. Assert offsets point to "First" at 0, "Second" at 5, "Third" at 11

**Verifies:** AC1.1 -- plain prose with `<p>` elements gets sequential numbers

### Mixed block elements numbered correctly
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestAutoNumberParagraphs::test_ac1_2_mixed_block_elements
1. Build map from `<p>`, `<blockquote>`, `<ul><li>` with auto_number=True
2. Assert 2 entries (p and blockquote numbered; li skipped in auto-number mode)

**Verifies:** AC1.2 -- list items are sub-structure, not discourse-level paragraphs

### Blockquote wrapping `<p>` is not double-counted
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestAutoNumberParagraphs::test_blockquote_wrapping_p_not_double_counted
1. Build map from `<p>Before</p><blockquote><p>Quoted text</p></blockquote><p>After</p>`
2. Assert values are [1, 2, 3] with no gaps

**Verifies:** Regression -- blockquote acting as wrapper delegates numbering to inner `<p>`

### Double `<br><br>` creates new paragraph
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestAutoNumberParagraphs::test_ac1_3_br_br_creates_new_paragraph
1. Build map from `<p>Line one<br><br>Line two</p>` with auto_number=True
2. Assert 2 entries -- "Line one" is para 1, "Line two" is para 2

**Verifies:** AC1.3 -- br-br sequences within a block create new paragraph boundaries

### Single `<br>` does not split
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestAutoNumberParagraphs::test_ac1_4_single_br_no_split
1. Build map from `<p>Line one<br>Line two</p>`
2. Assert only 1 entry

**Verifies:** AC1.4 -- single br is a line break, not a paragraph boundary

### Headers not numbered
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestAutoNumberParagraphs::test_ac1_5_headers_skipped
1. Build map from `<h1>Title</h1><p>Body</p>`
2. Assert 1 entry for `<p>` only

**Verifies:** AC1.5 -- h1-h6 elements are excluded from paragraph numbering

### Empty/whitespace blocks skipped
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestAutoNumberParagraphs::test_ac1_6_empty_whitespace_blocks_skipped
1. Build map from `<p>   </p><p>Real content</p>`
2. Assert 1 entry for "Real content" only

**Verifies:** AC1.6 -- whitespace-only blocks do not consume paragraph numbers

## Source-Number Paragraphs (Unit)

### AustLII-style numbered list uses li[value] numbers
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestSourceNumberParagraphs::test_ac2_1_numbered_list
1. Build 42 `<li value="N">` items in an `<ol>`
2. Build map with auto_number=False
3. Assert 42 entries with values 1..42

**Verifies:** AC2.1 -- source-number mode reads paragraph numbers from HTML attributes

### Gaps in source numbering preserved
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestSourceNumberParagraphs::test_ac2_2_gaps_preserved
1. Build map from `<li value="1">` and `<li value="5">`
2. Assert values are [1, 5]

**Verifies:** AC2.2 -- non-sequential paragraph numbers from source are preserved exactly

### Non-numbered blocks have no entry in source mode
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestSourceNumberParagraphs::test_ac2_3_non_numbered_blocks_no_entry
1. Build map from `<li value="1">` followed by `<p>Unnumbered</p>` with auto_number=False
2. Assert only 1 entry (the numbered `<li>`)

**Verifies:** AC2.3 -- plain blocks between numbered items get no paragraph number

## Source Numbering Detection (Unit)

### Detects 2+ li[value] as source-numbered
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestDetectSourceNumbering::test_ac3_1_detects_source_numbered
1. Call detect_source_numbering on HTML with 3 `<li value>` elements
2. Assert returns True

**Verifies:** AC3.1 -- threshold of 2+ numbered list items triggers source-number mode

### Zero or one li[value] returns False
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestDetectSourceNumbering::test_ac3_2_no_source_numbering_zero / test_ac3_2_no_source_numbering_one
1. Call detect_source_numbering on plain paragraphs (0 li[value]) and on 1 li[value]
2. Assert both return False

**Verifies:** AC3.2 -- below threshold does not trigger source-number mode

## Char-Offset Alignment (Unit)

### Offsets align with extract_text_from_html
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestCharOffsetAlignment (6 tests)
1. For each HTML variant (simple, mixed, br-br, source-numbered, header+body, whitespace)
2. Extract text via _extract_text helper (mirrors extract_text_from_html)
3. Build paragraph map
4. Assert every offset key is a valid index into the extracted text

**Verifies:** AC8 -- paragraph map char offsets are consistent with the text walker

### Offsets point to correct text characters
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestCharOffsetAlignment::test_ac8_1_offsets_point_to_correct_text
1. Build map and extract text from `<p>Alpha</p><p>Beta</p>`
2. Assert first offset points to 'A', second points to 'B'

**Verifies:** AC8.1 -- offsets point to the first character of each paragraph's content

## Paragraph Attribute Injection (Unit)

### Auto-numbered HTML gets data-para attributes
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestInjectParagraphAttributes::test_ac4_1_auto_numbered_paragraphs
1. Build paragraph map and inject attributes into 3 `<p>` elements
2. Parse result, assert 3 `p[data-para]` elements with values "1", "2", "3"

**Verifies:** AC4.1 -- inject_paragraph_attributes adds data-para to each block

### Source-numbered li gets data-para from map
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestInjectParagraphAttributes::test_ac4_2_source_numbered_li
1. Build map from `<li value="5">` and `<li value="10">` with auto_number=False
2. Inject attributes, assert li[data-para] values are "5" and "10"

**Verifies:** AC4.2 -- source paragraph numbers appear as data-para attributes

### Blockquote wrapping `<p>` -- no double data-para
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestInjectParagraphAttributes::test_blockquote_wrapping_p_no_double_attribute
1. Inject attributes into `<blockquote><p>Quoted</p></blockquote>`
2. Assert blockquote has NO data-para, only inner `<p>` elements do
3. Assert sequential values [1, 2, 3] with no gaps

**Verifies:** Regression -- wrapper blockquote does not get a duplicate data-para

### br-br pseudo-paragraph gets span wrapper
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestInjectParagraphAttributes::test_br_br_pseudo_paragraph
1. Inject attributes into `<p>Line one<br><br>Line two</p>`
2. Assert `<p data-para="1">` and `<span data-para="2">` for the second segment

**Verifies:** br-br text that cannot be a block element gets a `<span data-para>` wrapper

## Paragraph Reference Lookup (Unit)

### Single-paragraph highlight returns [N]
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestLookupParaRef::test_ac5_1_single_paragraph
1. Call lookup_para_ref with start/end within paragraph 2
2. Assert returns "[2]"

**Verifies:** AC5.1 -- highlight in one paragraph shows that paragraph's number

### Multi-paragraph highlight returns [N]-[M]
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestLookupParaRef::test_ac5_2_spanning_paragraphs
1. Call lookup_para_ref with range spanning paragraphs 2-3
2. Assert returns "[2]-[3]"

**Verifies:** AC5.2 -- spanning highlights show the range

### Highlight before first paragraph returns empty
**File:** tests/unit/input_pipeline/test_paragraph_map.py::TestLookupParaRef::test_ac5_4_before_first_paragraph
1. Call lookup_para_ref with range before any mapped paragraph
2. Assert returns ""

**Verifies:** AC5.4 -- no paragraph reference when highlight precedes first mapped block

## Paragraph Numbering DB Columns (Integration)

### Default values on new document
**File:** tests/integration/test_paragraph_numbering.py::TestWorkspaceDocumentParagraphFields::test_defaults_on_new_document
1. Create WorkspaceDocument with no paragraph args
2. Commit and reload from DB
3. Assert auto_number_paragraphs=True and paragraph_map={}

**Verifies:** Schema defaults -- new documents get auto-number mode and empty map

### paragraph_map JSON round-trip
**File:** tests/integration/test_paragraph_numbering.py::TestWorkspaceDocumentParagraphFields::test_paragraph_map_round_trip
1. Create document with paragraph_map={"0": 1, "50": 2, "120": 3}
2. Commit and reload
3. Assert map round-trips with string keys and int values

**Verifies:** PostgreSQL JSON column preserves string-keyed paragraph map

### source-number mode persists
**File:** tests/integration/test_paragraph_numbering.py::TestWorkspaceDocumentParagraphFields::test_source_number_mode
1. Create document with auto_number_paragraphs=False
2. Commit and reload
3. Assert auto_number_paragraphs=False

**Verifies:** Boolean column persists False for source-number mode

### add_document with explicit paragraph fields
**File:** tests/integration/test_paragraph_numbering.py::TestAddDocumentWithParagraphFields::test_explicit_paragraph_fields_persist
1. Call add_document() with auto_number_paragraphs=False and a test paragraph_map
2. Reload via get_document()
3. Assert both fields match

**Verifies:** add_document() API accepts and persists paragraph numbering fields

### add_document defaults when no paragraph args
**File:** tests/integration/test_paragraph_numbering.py::TestAddDocumentWithParagraphFields::test_defaults_when_no_paragraph_args
1. Call add_document() without paragraph args
2. Reload and assert defaults (True, {})

**Verifies:** Backward compatibility -- existing callers get sensible defaults

### Clone copies paragraph numbering fields
**File:** tests/integration/test_paragraph_numbering.py::TestCloneParagraphFields::test_clone_copies_auto_number_paragraphs_and_paragraph_map
1. Create course/week/activity/student infrastructure
2. Add template document with auto_number_paragraphs=False and test map
3. Clone workspace via clone_workspace_from_activity()
4. Reload cloned document
5. Assert auto_number_paragraphs=False and paragraph_map match template

**Verifies:** Cloning propagates paragraph numbering fields from template to student workspace

### update_document_paragraph_settings persists changes
**File:** tests/integration/test_paragraph_numbering.py::TestUpdateDocumentParagraphSettings::test_update_toggles_auto_number_and_rebuilds_map
1. Create document with auto_number=True and initial map
2. Call update_document_paragraph_settings with auto_number=False and new map
3. Reload and assert new values

**Verifies:** AC7.2 -- toggle handler can persist new numbering mode and rebuilt map

### update non-existent document raises ValueError
**File:** tests/integration/test_paragraph_numbering.py::TestUpdateDocumentParagraphSettings::test_update_nonexistent_document_raises
1. Call update_document_paragraph_settings with random UUID
2. Assert raises ValueError matching "not found"

**Verifies:** Error handling for missing documents

## Highlight para_ref Wiring (Integration)

### Single-paragraph highlight round-trips through CRDT
**File:** tests/integration/test_paragraph_numbering.py::TestHighlightParaRefWiring::test_single_paragraph_highlight_has_para_ref
1. Compute para_ref via lookup_para_ref from paragraph_map
2. Add highlight to AnnotationDocument CRDT with para_ref="[3]"
3. Retrieve highlights and assert para_ref preserved

**Verifies:** AC5.1 -- paragraph reference survives CRDT round-trip

### Multi-paragraph highlight range round-trips
**File:** tests/integration/test_paragraph_numbering.py::TestHighlightParaRefWiring::test_multi_paragraph_highlight_has_range_para_ref
1. Compute para_ref for range spanning paragraphs 2-4
2. Store in CRDT, retrieve, assert para_ref="[2]-[4]"

**Verifies:** AC5.2 -- range references survive CRDT round-trip

### Toggle rebuilds paragraph_map in DB
**File:** tests/integration/test_paragraph_numbering.py::TestToggleParagraphNumbering::test_toggle_rebuilds_paragraph_map_in_db
1. Create document with auto_number=True and auto-built map
2. Rebuild map with auto_number=False (source mode), persist via update
3. Reload and assert new mode and map
4. Toggle back to auto_number=True, persist, reload, assert original map

**Verifies:** AC7.2 -- full toggle cycle works end-to-end through DB

### Toggle does not modify existing highlight para_ref
**File:** tests/integration/test_paragraph_numbering.py::TestToggleParagraphNumbering::test_toggle_does_not_modify_highlight_para_ref
1. Create CRDT doc with two highlights having para_ref="[1]" and "[2]"
2. Rebuild paragraph maps for both modes (auto and source)
3. Assert highlight para_ref values unchanged after rebuild

**Verifies:** AC7.3 -- toggling numbering mode is non-destructive to existing annotations

## Upload Dialog Contract (Integration)

### Dialog accepts source_numbering_detected parameter
**File:** tests/integration/test_paragraph_numbering.py::TestUploadDialogAutoDetect::test_dialog_function_accepts_source_numbering_parameter
1. Inspect signature of show_content_type_dialog
2. Assert source_numbering_detected parameter exists with default=False

**Verifies:** AC3.3 -- dialog API supports source-numbering detection

### Dialog return type includes auto-number bool
**File:** tests/integration/test_paragraph_numbering.py::TestUploadDialogAutoDetect::test_dialog_return_type_includes_bool
1. Get type hints for show_content_type_dialog
2. Assert return type includes tuple, bool, and None

**Verifies:** AC3.3 -- dialog returns (ContentType, auto_number_bool) | None

### Paste handler uses auto-detect, bypasses dialog
**File:** tests/integration/test_paragraph_numbering.py::TestUploadDialogAutoDetect::test_paste_handler_auto_detect_bypasses_dialog
1. Call _detect_paragraph_numbering on plain HTML
2. Assert auto_number=True and 2-entry map
3. Call on AustLII HTML
4. Assert auto_number=False and non-empty map

**Verifies:** AC3.3 -- paste path auto-detects numbering mode without user dialog

## CRDT para_ref Update (Unit)

### update_highlight_para_ref changes value
**File:** tests/unit/test_annotation_doc.py::TestUpdateHighlightParaRef::test_update_highlight_para_ref_changes_value
1. Add highlight with para_ref="[1]"
2. Call update_highlight_para_ref with new_para_ref="[5]"
3. Assert returns True and highlight now has para_ref="[5]"

**Verifies:** AC5.3 -- para_ref can be updated after creation

### update_highlight_para_ref with unknown ID returns False
**File:** tests/unit/test_annotation_doc.py::TestUpdateHighlightParaRef::test_update_unknown_highlight_returns_false
1. Call update_highlight_para_ref with non-existent highlight_id
2. Assert returns False

**Verifies:** Error handling for unknown highlights

### update_highlight_para_ref preserves other fields
**File:** tests/unit/test_annotation_doc.py::TestUpdateHighlightParaRef::test_update_preserves_other_fields
1. Add highlight with all fields set
2. Update para_ref to new value
3. Assert start_char, end_char, tag, text, author, document_id unchanged

**Verifies:** para_ref update is targeted -- no side effects on other highlight fields

### update_highlight_para_ref syncs via CRDT
**File:** tests/unit/test_annotation_doc.py::TestUpdateHighlightParaRef::test_update_syncs_across_docs
1. Create two AnnotationDocument instances, sync initial state
2. Update para_ref on doc1, extract update bytes
3. Apply update to doc2
4. Assert doc2 now has the updated para_ref

**Verifies:** para_ref changes propagate through CRDT sync protocol

## PDF Export Paragraph Map Conversion (Unit)

### String keys convert to int keys
**File:** tests/unit/export/test_pdf_export_para_map.py::TestParagraphMapKeyConversion::test_normal_conversion
1. Convert {"0": 1, "50": 2, "120": 3} to int-keyed dict
2. Assert result is {0: 1, 50: 2, 120: 3}

**Verifies:** JSON string keys from DB are converted to int keys for export pipeline

### Empty map becomes None
**File:** tests/unit/export/test_pdf_export_para_map.py::TestParagraphMapKeyConversion::test_empty_map_becomes_none
1. Convert empty dict
2. Assert result is None

**Verifies:** Documents without paragraph maps skip paragraph numbering in export

### Source-numbered gaps preserved in conversion
**File:** tests/unit/export/test_pdf_export_para_map.py::TestParagraphMapKeyConversion::test_source_numbered_with_gaps
1. Convert {"0": 1, "100": 5, "200": 12, "350": 13}
2. Assert non-sequential values preserved

**Verifies:** Source-numbered document gaps survive the key conversion

## PDF Export Paragraph References in Margin Notes (Unit)

### Margin notes include [N] paragraph references
**File:** tests/unit/export/test_highlight_spans.py::TestAC6_ParaRefInMarginNotes (6 tests)
1. Create highlights at known char offsets
2. Call compute_highlight_spans with word_to_legal_para mapping
3. Parse data-annots attributes on resulting spans
4. Assert "[N]" references appear in annotation strings
5. Test single-paragraph, multi-paragraph range, no-map, and format variants

**Verifies:** AC6 -- PDF margin notes display paragraph references from the paragraph map

## Upload Dialog Parameter (Unit)

### Dialog has source_numbering_detected parameter
**File:** tests/unit/pages/test_dialogs.py (2 tests)
1. Inspect show_content_type_dialog signature
2. Assert source_numbering_detected parameter exists
3. Assert default value is False

**Verifies:** Upload dialog API contract includes source numbering detection

## Paragraph Screenshot Visual Verification (E2E)

### Fixture screenshots with paragraph numbering
**File:** tests/e2e/test_para_screenshot.py::TestParagraphScreenshots::test_fixture_screenshots
1. Create workspace, authenticate, navigate to annotation page
2. Paste HTML fixture via clipboard simulation (19 fixtures parametrised)
3. Wait for document render (text walker ready)
4. Evaluate JS to count data-para elements
5. Evaluate landmark detection JS (speakers, headings, lists, blockquotes, tables, code blocks, first/last data-para)
6. Scroll to each landmark and take screenshot
7. Assert data-para elements > 0 and screenshots taken

**Verifies:** Visual regression -- paragraph numbers render correctly across diverse HTML formats (AustLII, ChatCraft, Claude, Gemini, OpenAI, translations, Wikipedia, etc.)

## Word Count -- Multilingual Tokenisation

### Text normalisation (NFKC, zero-width, markdown URLs)
**File:** tests/unit/test_word_count.py::TestNormaliseText
1. Pass fullwidth characters (U+FF21-FF23) through normalise_text
2. Assert NFKC converts them to ASCII ("ABC")
3. Pass text with zero-width spaces; assert they are stripped
4. Pass markdown links `[text](url)` and images `![alt](url)`; assert URLs removed, text kept
5. Edge cases: reference-style links preserved, multiple links, nested bold, only-zero-width chars become empty

**Verifies:** Pre-tokenisation normalisation handles Unicode gaming vectors and markdown URL inflation

### Script-based segmentation (Latin, Chinese, Japanese, Korean)
**File:** tests/unit/test_word_count.py::TestSegmentByScript
1. Pass pure English text; assert single ("latin", ...) segment
2. Pass pure Chinese; assert single ("zh", ...) segment
3. Pass Japanese with hiragana+kanji; assert single ("ja", ...) segment (neighbour resolution reclassifies adjacent kanji)
4. Pass Korean hangul; assert single ("ko", ...) segment
5. Pass mixed English+Chinese; assert two segments
6. Pass mixed all-four-scripts; assert correct segmentation per codepoint ranges
7. Edge cases: empty string, whitespace, CJK punctuation as latin, emoji as latin, standalone kanji without hiragana classified as zh

**Verifies:** Unicode codepoints are correctly classified into script groups for per-script tokenisation

### word_count() exact and CJK tolerance
**File:** tests/unit/test_word_count.py::TestWordCount
1. Pass "well-known fact"; assert 3 (hyphens split into separate words)
2. Pass "write-like-this-to-game"; assert 5 (anti-gaming hyphen splitting)
3. Pass empty string; assert 0
4. Pass "42" (numbers only); assert 0
5. Pass Chinese text; assert count in range 6-8 (jieba dictionary variance)
6. Pass Japanese text; assert count in range 7-9 (MeCab dictionary variance)
7. Pass Korean space-delimited text; assert exactly 4

**Verifies:** Full pipeline (normalise -> segment -> tokenise -> filter -> count) produces correct counts with anti-gaming measures

### Anti-gaming integration
**File:** tests/unit/test_word_count.py::TestWordCountAntiGaming
1. Pass mixed English+Japanese; assert count >= 5 (both segments counted)
2. Pass markdown link; assert count == 2 (URL excluded, link text counted)
3. Pass text with zero-width space between words; assert merged to 1 word
4. Pass fullwidth text; assert NFKC normalises before counting
5. Pass combined anti-gaming text; assert correct count
6. Pass pure punctuation; assert 0 words
7. Pass mixed CJK+English; assert >= 3

**Verifies:** Anti-gaming measures (zero-width stripping, NFKC, URL removal, hyphen splitting) work in combination

## Word Count -- Model Fields

### Activity word count field defaults
**File:** tests/unit/test_word_count_models.py::TestActivityWordCountFields
1. Create Activity with no overrides
2. Assert word_minimum=None, word_limit=None, word_limit_enforcement=None
3. Create Activity with explicit positive integers; verify they are stored
4. Create Activity with enforcement=True/False/None; verify tri-state

**Verifies:** Activity model accepts word count fields with correct defaults (all nullable)

### Course word count field defaults
**File:** tests/unit/test_word_count_models.py::TestCourseWordCountFields
1. Create Course with defaults
2. Assert default_word_limit_enforcement is False
3. Create Course with default_word_limit_enforcement=True; verify stored

**Verifies:** Course carries the enforcement default that activities inherit via resolve_tristate

### Cross-field validation (word_minimum vs word_limit)
**File:** tests/unit/test_word_count_models.py::TestWordCountValidation
1. Call validate_word_count_limits with minimum=500, limit=200; assert ValueError
2. Call with minimum=500, limit=500 (equal); assert ValueError
3. Call with minimum=200, limit=500; assert no error
4. Call with one or both None; assert no error

**Verifies:** Setting word_minimum >= word_limit is rejected at the validation layer

### Tri-state UI helper existence
**File:** tests/unit/test_word_count_models.py::TestActivityTriStateConfig
1. Import _tri_state_options from pages.courses
2. Call with "Hard", "Soft" labels; verify keys "on", "off", "inherit" exist

**Verifies:** Activity settings UI uses the standard tri-state pattern for enforcement

## Word Count -- Badge Formatting

### Badge text and CSS classes
**File:** tests/unit/test_word_count_badge.py::TestFormatWordCountBadge
1. Call format_word_count_badge with various (count, min, limit) combos
2. Assert neutral badge text includes comma-formatted count and limit
3. Assert amber badge appears at 90% of limit ("approaching limit")
4. Assert red badge for over limit ("over limit") or below minimum ("below minimum")
5. Assert CSS classes match _NEUTRAL, _AMBER, or _RED constants

**Verifies:** Badge state correctly represents word count status with visual severity

### Badge edge cases
**File:** tests/unit/test_word_count_badge.py::TestBadgeEdgeCases
1. Zero count with various limit configs
2. Exactly-at-limit is red (over)
3. Exactly 90% is amber; just below 90% is neutral
4. Both limits set with count below minimum

**Verifies:** Boundary conditions at limit thresholds produce correct badge states

### Badge with both min and max limits
**File:** tests/unit/test_word_count_badge.py::TestBadgeCombinedMinMax
1. Count below minimum -> red
2. Count within range -> neutral
3. Count approaching limit -> amber
4. Count over limit -> red

**Verifies:** Combined min+max configuration shows correct badge at each threshold

## Word Count -- Enforcement (Export-Time)

### Violation detection (check_word_count_violation)
**File:** tests/unit/test_word_count_enforcement.py::TestCheckWordCountViolation
1. count=150, limit=100 -> over_limit=True, over_by=50
2. count=50, min=100 -> under_minimum=True, under_by=50
3. count=150, min=100, limit=200 -> no violation
4. No limits -> no violation
5. At exactly limit (count==limit) -> over_limit=True (at-limit is over)
6. At exactly minimum (count==minimum) -> not under (at-minimum is OK)
7. Violation preserves count, min, limit values

**Verifies:** Pure function correctly detects over-limit and under-minimum violations

### Violation message formatting
**File:** tests/unit/test_word_count_enforcement.py::TestFormatViolationMessage
1. Over-limit violation -> message includes limit and current count
2. Under-minimum violation -> message includes minimum and current count
3. Both violated (synthetic) -> combined message
4. Large count -> comma-separated formatting
5. No violation -> empty string

**Verifies:** Human-readable violation messages for export-time dialogs

### AC7: Enforcement only imported by export code
**File:** tests/unit/test_word_count_enforcement.py::TestAC7NonBlockingBehaviour
1. Import promptgrimoire.crdt; assert no enforcement symbols (AC7.1: save path clean)
2. Import pages.annotation.respond; assert no enforcement symbols (AC7.2: edit path clean)
3. Import db.acl; assert no enforcement symbols (AC7.3: share path clean)
4. Import pages.annotation.pdf_export; assert enforcement symbols present (AC7.4: export uses it)

**Verifies:** Word count enforcement is architecturally isolated to export -- save/edit/share paths never block on word count

## Word Count -- PDF Snitch Badge

### LaTeX badge generation
**File:** tests/unit/test_word_count_pdf_badge.py::TestBuildWordCountBadge
1. Over limit -> red fcolorbox with "Word Count: N / N (Exceeded)"
2. Within limits -> italic neutral line with "Word Count: N / N"
3. No limits -> empty string
4. Under minimum -> red fcolorbox with "(Below Minimum)"
5. At exactly limit -> red badge
6. At exactly minimum -> neutral badge
7. Both limits within range -> neutral showing max
8. Badge includes vspace for separation

**Verifies:** LaTeX export produces correct visual badge (red box or neutral italic) based on violation state

## Word Count -- PageState Fields

### PageState word count defaults
**File:** tests/unit/test_page_state_word_count.py::TestPageStateWordCountDefaults
1. Create PageState with only workspace_id
2. Assert word_minimum=None, word_limit=None, word_limit_enforcement=False, word_count_badge=None

**Verifies:** PageState fields have safe defaults when no limits configured

### PageState explicit values
**File:** tests/unit/test_page_state_word_count.py::TestPageStateWordCountExplicit
1. Set word_minimum=500; assert stored
2. Set word_limit=1500; assert stored
3. Set word_limit_enforcement=True; assert stored
4. Set all three together; assert all stored, badge still None

**Verifies:** PageState accepts word count fields from PlacementContext resolution

## Word Count -- PlacementContext Resolution (Integration)

### Enforcement tri-state resolution
**File:** tests/integration/test_word_count_placement.py::TestPlacementContextWordCountResolution
1. Activity enforcement=True, course default=False -> ctx.word_limit_enforcement=True
2. Activity enforcement=None, course default=False -> ctx.word_limit_enforcement=False (inherited)
3. Activity enforcement=False, course default=True -> ctx.word_limit_enforcement=False (override wins)
4. Activity with no word count fields -> all None/default

**Verifies:** resolve_tristate correctly resolves activity-level override vs course-level default for enforcement

### Edge cases: course-placed, loose, partial configs
**File:** tests/integration/test_word_count_placement.py::TestPlacementContextWordCountEdgeCases
1. Course-placed workspace -> word_minimum/limit=None, enforcement from course default
2. Loose workspace -> no limits, enforcement=False
3. Activity with minimum-only -> word_limit stays None
4. Activity with limit-only -> word_minimum stays None

**Verifies:** Placement resolution handles all workspace placement types and partial limit configurations

### update_activity() word count support
**File:** tests/integration/test_word_count_placement.py::TestUpdateActivityWordCountFields
1. Set word_minimum via update_activity; read back
2. Set word_limit; read back
3. Set enforcement=True; read back
4. Reset enforcement to None (inherit); read back
5. Set minimum >= limit -> ValueError
6. Update only one field when other already set, exceeding limit -> ValueError
7. Omit word count params; verify existing values preserved

**Verifies:** update_activity() correctly handles word count CRUD with cross-field validation

## Word Count -- PageState from PlacementContext (Integration)

### PlacementContext fields propagate to PageState
**File:** tests/integration/test_pagestate_word_count.py::TestPageStateWordCountFromPlacementContext
1. Seed activity with word_limit=500; create workspace; get PlacementContext
2. Construct PageState with ctx fields; assert word_limit=500, others default
3. Seed with word_minimum=100; assert word_minimum=100 in PageState
4. Seed with all three fields; assert all propagate
5. Seed with no limits; assert PageState has defaults

**Verifies:** Data path from Activity -> PlacementContext -> PageState correctly carries word count configuration

## Word Count -- E2E

### Activity settings UI
**File:** tests/e2e/test_word_count.py::TestWordCountSettings
1. Create course and activity via UI
2. Open activity settings dialog
3. Fill word minimum input (data-testid="activity-word-minimum-input") with "200"
4. Fill word limit input (data-testid="activity-word-limit-input") with "500"
5. Select enforcement "Hard" from tri-state dropdown
6. Save settings; verify dialog closes
7. Reload page; reopen settings; verify values persisted
8. Toggle course-level default word limit enforcement; reload; verify persisted

**Verifies:** Word count settings round-trip through the activity settings dialog and survive page reloads

### Soft enforcement warning on export
**File:** tests/e2e/test_word_count.py::TestWordCountExport::test_soft_enforcement_warning
1. Create workspace with word_limit=10, enforcement=False (soft), HTML content
2. Navigate to annotation page
3. Trigger PDF export
4. Assert warning dialog appears (not blocking)
5. Confirm export proceeds

**Verifies:** Soft enforcement shows a dismissable warning but allows export to continue

## Roleplay -- Session-to-HTML Export (Unit)

### User turn has correct speaker attributes
**File:** tests/unit/test_roleplay_export.py::TestSessionToHtml::test_user_turn_has_correct_speaker_attrs
1. Create session with character "Becky Bennett" and user "Jane"
2. Add a user turn "Hello Becky"
3. Call session_to_html(session)
4. Assert HTML contains data-speaker="user" and data-speaker-name="Jane"

**Verifies:** AC3.2 -- user turns produce correct speaker marker attributes

### AI turn has correct speaker attributes
**File:** tests/unit/test_roleplay_export.py::TestSessionToHtml::test_ai_turn_has_correct_speaker_attrs
1. Create session, add an AI turn
2. Call session_to_html(session)
3. Assert HTML contains data-speaker="assistant" and data-speaker-name="Becky Bennett"

**Verifies:** AC3.2 -- AI turns produce assistant speaker markers with character name

### Markdown converts to HTML
**File:** tests/unit/test_roleplay_export.py::TestSessionToHtml::test_markdown_converts_to_html
1. Create session, add AI turn with "*italics* and **bold**"
2. Call session_to_html(session)
3. Assert output contains <em>italics</em> and <strong>bold</strong>

**Verifies:** Markdown formatting in turn content is rendered to HTML

### Marker divs are siblings not parents
**File:** tests/unit/test_roleplay_export.py::TestSessionToHtml::test_marker_divs_are_siblings_not_parents
1. Create session, add user turn "Hello"
2. Call session_to_html(session)
3. Assert marker div is followed by content as sibling (</div>\n<p>) not child

**Verifies:** Speaker marker divs are empty siblings of content, not wrappers

### Multiple turns alternate correctly
**File:** tests/unit/test_roleplay_export.py::TestSessionToHtml::test_multiple_turns_alternate_correctly
1. Create session, add user turn then AI turn
2. Call session_to_html(session)
3. Assert both data-speaker="user" and data-speaker="assistant" present
4. Assert user marker appears before assistant marker in output

**Verifies:** Multi-turn sessions produce correctly ordered marker+content blocks

### Empty session returns empty string
**File:** tests/unit/test_roleplay_export.py::TestSessionToHtml::test_empty_session_returns_empty_string
1. Create session with no turns
2. Call session_to_html(session)
3. Assert result is ""

**Verifies:** Edge case -- no turns produces no output

### System turn has system role
**File:** tests/unit/test_roleplay_export.py::TestSessionToHtml::test_system_turn_has_system_role
1. Create session, manually append Turn with is_system=True
2. Call session_to_html(session)
3. Assert HTML contains data-speaker="system"

**Verifies:** System turns (context injections) are distinguished from user/assistant turns

## Roleplay -- Visual Integration (Unit)

### User turn gets user avatar in _render_messages
**File:** tests/unit/test_roleplay_visual.py::TestRenderMessagesAvatarWiring::test_user_turn_gets_user_avatar
1. Patch _create_chat_message
2. Create session with one user turn
3. Call _render_messages(session, container, scroll_area)
4. Assert _create_chat_message was called with avatar=_USER_AVATAR

**Verifies:** AC1.2 -- _render_messages passes correct user avatar constant

### AI turn gets AI avatar in _render_messages
**File:** tests/unit/test_roleplay_visual.py::TestRenderMessagesAvatarWiring::test_ai_turn_gets_ai_avatar
1. Patch _create_chat_message
2. Create session with one AI turn
3. Call _render_messages(session, container, scroll_area)
4. Assert _create_chat_message was called with avatar=_AI_AVATAR

**Verifies:** AC1.3 -- _render_messages passes correct AI avatar constant

### Mixed turns get correct avatars
**File:** tests/unit/test_roleplay_visual.py::TestRenderMessagesAvatarWiring::test_mixed_turns_get_correct_avatars
1. Patch _create_chat_message
2. Create session with user turn then AI turn
3. Call _render_messages(session, container, scroll_area)
4. Assert first call uses _USER_AVATAR, second call uses _AI_AVATAR

**Verifies:** Both avatar constants are correctly dispatched based on turn type

### User message passes user avatar to ui.chat_message
**File:** tests/unit/test_roleplay_visual.py::TestAvatarParameter::test_user_message_passes_user_avatar
1. Patch nicegui ui module
2. Call _create_chat_message("Hello", "Jane", sent=True, avatar=user_avatar_path)
3. Assert ui.chat_message called with avatar="/static/roleplay/user-default.png"

**Verifies:** AC1.2 -- avatar URL is forwarded to NiceGUI chat_message component

### AI message passes AI avatar to ui.chat_message
**File:** tests/unit/test_roleplay_visual.py::TestAvatarParameter::test_ai_message_passes_ai_avatar
1. Patch nicegui ui module
2. Call _create_chat_message("Hi", "Becky Bennett", sent=False, avatar=ai_avatar_path)
3. Assert ui.chat_message called with avatar="/static/roleplay/becky-bennett.png"

**Verifies:** AC1.3 -- AI avatar URL is forwarded to NiceGUI chat_message component

### Avatar defaults to None
**File:** tests/unit/test_roleplay_visual.py::TestAvatarParameter::test_avatar_defaults_to_none
1. Patch nicegui ui module
2. Call _create_chat_message("Test", "User", sent=True) without avatar argument
3. Assert ui.chat_message called with avatar=None

**Verifies:** Backward compatibility -- omitting avatar parameter passes None

### Export button starts disabled without session
**File:** tests/unit/test_roleplay_visual.py::TestExportButtonState::test_export_button_disabled_without_session
1. Import _EXPORT_BTN_INITIAL_DISABLED constant from roleplay module
2. Assert it is True

**Verifies:** AC3.4 -- export button is disabled until a session is loaded

### Export button disabled constant is consumed in page function
**File:** tests/unit/test_roleplay_visual.py::TestExportButtonState::test_constant_is_consumed_in_page_function
1. Get source code of roleplay_page function via inspect.getsource
2. Assert "_EXPORT_BTN_INITIAL_DISABLED" appears in the source

**Verifies:** Guard test -- the disabled constant is actually referenced in the page builder

## Roleplay -- Workspace Export (Integration)

### Export creates workspace with ai_conversation document
**File:** tests/integration/test_roleplay_workspace_export.py::TestRoleplayWorkspaceExport::test_export_creates_workspace_with_ai_conversation_doc
1. Create session with two turns (user + AI)
2. Convert to HTML via session_to_html()
3. Create workspace and add document with type="ai_conversation"
4. Retrieve workspace, assert it exists
5. List documents, assert exactly one with type "ai_conversation"

**Verifies:** AC3.1 -- export pipeline creates a loose workspace with correct document type

### Exported document contains speaker markers
**File:** tests/integration/test_roleplay_workspace_export.py::TestRoleplayWorkspaceExport::test_exported_document_contains_speaker_markers
1. Create session with user and AI turns
2. Convert to HTML, create workspace, add document
3. Retrieve document content
4. Assert content contains data-speaker="user", data-speaker="assistant", and both speaker names

**Verifies:** AC3.1+AC3.2 -- stored document preserves speaker marker attributes for annotation

### Export grants owner permission
**File:** tests/integration/test_roleplay_workspace_export.py::TestRoleplayWorkspaceExport::test_export_grants_owner_permission
1. Create test user and workspace
2. Grant "owner" permission via grant_permission()
3. Resolve permission for that user/workspace pair
4. Assert resolved permission is "owner"

**Verifies:** AC3.1 -- exported workspace has owner ACL for the exporting user

## Wargame Model Validation (Unit)

### Activity rejects unknown type
**File:** tests/unit/test_wargame_models.py::TestActivityTypeValidation::test_activity_rejects_unknown_type
1. model_validate Activity with type="unknown"
2. Assert ValueError matching "activity type must be 'annotation' or 'wargame'"

**Verifies:** Activity type discriminator rejects values outside the known domain

### Annotation activity requires template workspace
**File:** tests/unit/test_wargame_models.py::TestActivityTypeValidation::test_annotation_activity_requires_template_workspace
1. model_validate Activity with type="annotation" and no template_workspace_id
2. Assert ValueError matching "annotation activities require template_workspace_id"

**Verifies:** Annotation activities enforce template workspace requirement at model level

### Wargame activity must not define template workspace
**File:** tests/unit/test_wargame_models.py::TestActivityTypeValidation::test_wargame_activity_must_not_define_template_workspace
1. model_validate Activity with type="wargame" and a template_workspace_id set
2. Assert ValueError matching "wargame activities must not set template_workspace_id"

**Verifies:** Wargame activities reject template workspace at model level

### WargameConfig accepts timer_delta only
**File:** tests/unit/test_wargame_models.py::TestWargameConfigValidation::test_accepts_timer_delta_only
1. model_validate WargameConfig with timer_delta=15min, timer_wall_clock=None
2. Assert activity_type defaults to "wargame", timer fields correct

**Verifies:** Relative timer mode is a valid configuration

### WargameConfig accepts timer_wall_clock only
**File:** tests/unit/test_wargame_models.py::TestWargameConfigValidation::test_accepts_timer_wall_clock_only
1. model_validate WargameConfig with timer_delta=None, timer_wall_clock=09:30
2. Assert activity_type defaults to "wargame", timer fields correct

**Verifies:** Wall-clock timer mode is a valid configuration

### WargameConfig rejects both timer fields unset
**File:** tests/unit/test_wargame_models.py::TestWargameConfigValidation::test_rejects_both_timer_fields_unset
1. model_validate WargameConfig with both timer fields None
2. Assert ValueError matching "exactly one of timer_delta or timer_wall_clock"

**Verifies:** Timer exclusivity -- at least one must be set

### WargameConfig rejects both timer fields set
**File:** tests/unit/test_wargame_models.py::TestWargameConfigValidation::test_rejects_both_timer_fields_set
1. model_validate WargameConfig with both timer fields populated
2. Assert ValueError matching "exactly one of timer_delta or timer_wall_clock"

**Verifies:** Timer exclusivity -- at most one must be set

### WargameConfig rejects non-wargame activity type
**File:** tests/unit/test_wargame_models.py::TestWargameConfigValidation::test_rejects_non_wargame_activity_type
1. model_validate WargameConfig with activity_type="annotation"
2. Assert ValueError matching "wargame config activity_type must be 'wargame'"

**Verifies:** Child discriminator stays fixed at "wargame"

### WargameTeam defaults activity_type to wargame
**File:** tests/unit/test_wargame_models.py::TestWargameTeamValidation::test_defaults_activity_type_to_wargame
1. model_validate WargameTeam with activity_id and codename only
2. Assert activity_type is "wargame"

**Verifies:** Team discriminator defaults correctly

### WargameTeam rejects non-wargame activity type
**File:** tests/unit/test_wargame_models.py::TestWargameTeamValidation::test_rejects_non_wargame_activity_type
1. model_validate WargameTeam with activity_type="annotation"
2. Assert ValueError matching "wargame team activity_type must be 'wargame'"

**Verifies:** Team discriminator rejects wrong parent type

### ACLEntry workspace target is valid
**File:** tests/unit/test_wargame_models.py::TestAclEntryTargetValidation::test_workspace_target_is_valid
1. model_validate ACLEntry with workspace_id set, team_id=None
2. Assert both fields are correct

**Verifies:** Existing workspace-target ACL shape still valid

### ACLEntry team target is valid
**File:** tests/unit/test_wargame_models.py::TestAclEntryTargetValidation::test_team_target_is_valid
1. model_validate ACLEntry with workspace_id=None, team_id set
2. Assert both fields are correct

**Verifies:** New team-target ACL shape is accepted

### ACLEntry rejects both targets set
**File:** tests/unit/test_wargame_models.py::TestAclEntryTargetValidation::test_rejects_both_workspace_and_team_targets
1. model_validate ACLEntry with both workspace_id and team_id set
2. Assert ValueError matching "exactly one of workspace_id or team_id"

**Verifies:** Exactly-one-target invariant at model level

### ACLEntry rejects no targets set
**File:** tests/unit/test_wargame_models.py::TestAclEntryTargetValidation::test_rejects_missing_workspace_and_team_targets
1. model_validate ACLEntry with both workspace_id and team_id None
2. Assert ValueError matching "exactly one of workspace_id or team_id"

**Verifies:** Exactly-one-target invariant at model level (neither set case)

## Wargame Schema Constraints (Integration)

### Activity type discriminator

#### Insert without type uses annotation default
**File:** tests/integration/test_wargame_schema.py::TestActivityTypeDiscriminator::test_insert_without_type_uses_annotation_default
1. Raw SQL INSERT into activity without type column
2. Read back via get_activity
3. Assert type defaults to "annotation"

**Verifies:** Backward compatibility -- legacy inserts without type get annotation default

#### Rejects unknown activity type
**File:** tests/integration/test_wargame_schema.py::TestActivityTypeDiscriminator::test_rejects_unknown_activity_type
1. Raw SQL INSERT with type="unknown"
2. Assert IntegrityError matching ck_activity_type_known

**Verifies:** Database CHECK constraint rejects invalid discriminator values

#### create_activity defaults to annotation type
**File:** tests/integration/test_wargame_schema.py::TestActivityTypeDiscriminator::test_create_activity_defaults_to_annotation_type
1. Call create_activity with title only
2. Assert type="annotation" and template_workspace_id is not None

**Verifies:** High-level CRUD preserves existing annotation default path

#### Accepts wargame activity without template workspace
**File:** tests/integration/test_wargame_schema.py::TestActivityTypeDiscriminator::test_accepts_wargame_activity_without_template_workspace
1. Create Activity with type="wargame", no template_workspace_id
2. Assert type="wargame" and template_workspace_id is None

**Verifies:** Wargame activities are valid without template workspaces

#### Rejects annotation without template workspace
**File:** tests/integration/test_wargame_schema.py::TestActivityTypeDiscriminator::test_rejects_annotation_activity_without_template_workspace
1. Insert Activity with type="annotation" and no template_workspace_id
2. Assert IntegrityError matching ck_activity_annotation_requires_template

**Verifies:** Database CHECK enforces annotation template requirement

#### Rejects wargame with template workspace
**File:** tests/integration/test_wargame_schema.py::TestActivityTypeDiscriminator::test_rejects_wargame_activity_with_template_workspace
1. Insert Activity with type="wargame" and a template_workspace_id
2. Assert IntegrityError matching ck_activity_wargame_no_template

**Verifies:** Database CHECK prevents wargame activities from having templates

### WargameConfig table

#### Accepts timer_delta only
**File:** tests/integration/test_wargame_schema.py::TestWargameConfigTable::test_accepts_timer_delta_only
1. Create wargame activity, insert WargameConfig with timer_delta=30min
2. Flush and refresh, assert timer fields and activity_type correct

**Verifies:** Relative timer mode persists to database

#### Accepts timer_wall_clock only
**File:** tests/integration/test_wargame_schema.py::TestWargameConfigTable::test_accepts_timer_wall_clock_only
1. Create wargame activity, insert WargameConfig with timer_wall_clock=09:00
2. Flush and refresh, assert timer fields and activity_type correct

**Verifies:** Wall-clock timer mode persists to database

#### Rejects both timer fields null
**File:** tests/integration/test_wargame_schema.py::TestWargameConfigTable::test_rejects_both_timer_fields_null
1. Insert WargameConfig with both timer fields None
2. Assert IntegrityError matching ck_wargame_config_timer_exactly_one

**Verifies:** Database CHECK enforces timer exclusivity

#### Rejects both timer fields set
**File:** tests/integration/test_wargame_schema.py::TestWargameConfigTable::test_rejects_both_timer_fields_set
1. Insert WargameConfig with both timer fields populated
2. Assert IntegrityError matching ck_wargame_config_timer_exactly_one

**Verifies:** Database CHECK enforces timer exclusivity (both set)

#### Rejects config for annotation activity
**File:** tests/integration/test_wargame_schema.py::TestWargameConfigTable::test_rejects_config_for_annotation_activity
1. Create annotation activity, try to insert WargameConfig
2. Assert IntegrityError matching fk_wargame_config_activity_wargame

**Verifies:** Composite FK prevents config attachment to non-wargame activities

#### Rejects non-wargame child discriminator
**File:** tests/integration/test_wargame_schema.py::TestWargameConfigTable::test_rejects_non_wargame_child_discriminator
1. Create wargame activity, insert WargameConfig with activity_type="annotation"
2. Assert IntegrityError matching ck_wargame_config_activity_type

**Verifies:** Child-side CHECK constraint rejects wrong discriminator

#### Deleting activity cascades to config
**File:** tests/integration/test_wargame_schema.py::TestWargameConfigTable::test_deleting_activity_cascades_to_config
1. Create wargame activity with config, delete the activity
2. Assert config row is None

**Verifies:** CASCADE DELETE propagates from Activity to WargameConfig

### WargameTeam table

#### Defaults and unique codename within activity
**File:** tests/integration/test_wargame_schema.py::TestWargameTeamTable::test_defaults_and_unique_codename_within_activity
1. Create two teams (Alpha, Bravo) under same activity
2. Assert defaults: current_round=0, round_state="drafting", etc.
3. Try to create duplicate "Alpha", assert IntegrityError matching uq_wargame_team_activity_codename

**Verifies:** Team defaults apply and codename uniqueness is scoped per activity

#### Rejects team for annotation activity
**File:** tests/integration/test_wargame_schema.py::TestWargameTeamTable::test_rejects_team_for_annotation_activity
1. Create annotation activity, try to insert WargameTeam
2. Assert IntegrityError matching fk_wargame_team_activity_wargame

**Verifies:** Composite FK prevents team attachment to non-wargame activities

#### Deleting activity cascades to teams
**File:** tests/integration/test_wargame_schema.py::TestWargameTeamTable::test_deleting_activity_cascades_to_teams
1. Create wargame activity with team, delete the activity
2. Assert team row is None

**Verifies:** CASCADE DELETE propagates from Activity to WargameTeam

### WargameMessage table

#### Orders messages by sequence number not timestamps
**File:** tests/integration/test_wargame_schema.py::TestWargameMessageTable::test_orders_messages_by_sequence_number_not_timestamps
1. Insert 3 messages with sequence_no 2,1,3 and deliberately reversed created_at timestamps
2. Query ORDER BY sequence_no
3. Assert order is [1,2,3] and content matches expected order
4. Assert message with seq 1 has later created_at than seq 2

**Verifies:** Canonical order is sequence_no, not timestamps

#### Roles and unique sequence per team
**File:** tests/integration/test_wargame_schema.py::TestWargameMessageTable::test_roles_and_unique_sequence_per_team
1. Insert messages with roles "user", "assistant", "system" at seq 1,2,3
2. Try to insert duplicate seq 2, assert IntegrityError matching uq_wargame_message_team_sequence

**Verifies:** Multiple roles accepted; duplicate sequence_no rejected

#### Updates earlier message in place without reordering
**File:** tests/integration/test_wargame_schema.py::TestWargameMessageTable::test_updates_earlier_message_in_place_without_reordering
1. Insert 2 messages (seq 1 and 2)
2. Update seq 1: change content, set thinking, metadata_json, edited_at
3. Re-query ORDER BY sequence_no
4. Assert seq order unchanged, content/thinking/metadata updated, edited_at set

**Verifies:** In-place edits preserve canonical order and update payload fields

#### Deleting team cascades to messages
**File:** tests/integration/test_wargame_schema.py::TestWargameMessageTable::test_deleting_team_cascades_to_messages
1. Create team with one message, delete the team
2. Assert message row is None

**Verifies:** CASCADE DELETE propagates from WargameTeam to WargameMessage

### ACL team extension

#### Workspace target entry remains valid
**File:** tests/integration/test_wargame_schema.py::TestAclEntryTeamExtension::test_workspace_target_entry_remains_valid
1. Create user and workspace, insert ACLEntry with workspace_id set, team_id=None
2. Assert entry persists with correct fields

**Verifies:** Existing workspace-target ACL path unbroken by team extension

#### Team target entry is valid
**File:** tests/integration/test_wargame_schema.py::TestAclEntryTeamExtension::test_team_target_entry_is_valid
1. Create wargame team and user, insert ACLEntry with team_id set, workspace_id=None
2. Assert entry persists with correct fields

**Verifies:** New team-target ACL path works at database level

#### Rejects ACL entry with both targets set
**File:** tests/integration/test_wargame_schema.py::TestAclEntryTeamExtension::test_rejects_acl_entry_with_both_targets_set
1. Insert ACLEntry with both workspace_id and team_id set
2. Assert IntegrityError matching ck_acl_entry_exactly_one_target

**Verifies:** Database CHECK enforces exactly-one-target invariant

#### Rejects ACL entry with no target set
**File:** tests/integration/test_wargame_schema.py::TestAclEntryTeamExtension::test_rejects_acl_entry_with_no_target_set
1. Insert ACLEntry with both workspace_id and team_id None
2. Assert IntegrityError matching ck_acl_entry_exactly_one_target

**Verifies:** Database CHECK enforces exactly-one-target invariant (neither set)

#### Workspace target uniqueness preserved
**File:** tests/integration/test_wargame_schema.py::TestAclEntryTeamExtension::test_workspace_target_uniqueness_preserved
1. Insert workspace ACL entry, try to insert duplicate (workspace_id, user_id)
2. Assert IntegrityError matching uq_acl_entry_workspace_user

**Verifies:** Partial unique index on workspace-target entries

#### Team target uniqueness enforced
**File:** tests/integration/test_wargame_schema.py::TestAclEntryTeamExtension::test_team_target_uniqueness_enforced
1. Insert team ACL entry, try to insert duplicate (team_id, user_id)
2. Assert IntegrityError matching uq_acl_entry_team_user

**Verifies:** Partial unique index on team-target entries

#### Deleting team cascades team ACL entries
**File:** tests/integration/test_wargame_schema.py::TestAclEntryTeamExtension::test_deleting_team_cascades_team_acl_entries
1. Create team with ACL entry, delete the team
2. Assert ACL entry row is None

**Verifies:** CASCADE DELETE propagates from WargameTeam to team-target ACLEntry

#### list_entries_for_user returns workspace and team targets
**File:** tests/integration/test_wargame_schema.py::TestAclEntryTeamExtension::test_list_entries_for_user_returns_workspace_and_team_targets
1. Create user with one workspace ACL and one team ACL entry
2. Call list_entries_for_user
3. Assert 2 entries returned, one workspace-target and one team-target

**Verifies:** ACL listing includes both target types

#### Workspace owner subquery ignores team entries
**File:** tests/integration/test_wargame_schema.py::TestAclEntryTeamExtension::test_workspace_owner_subquery_ignores_team_entries
1. Create user with team ACL (workspace_id=NULL) and a shared workspace
2. Call list_peer_workspaces
3. Assert returns shared workspace without NULL poisoning error

**Verifies:** NULL-safe workspace owner subquery in peer listing

#### Workspace owner lookup with names ignores team entries
**File:** tests/integration/test_wargame_schema.py::TestAclEntryTeamExtension::test_workspace_owner_lookup_with_names_ignores_team_entries
1. Create requester with team ACL (workspace_id=NULL), owner with workspace ACL, shared workspace
2. Call list_peer_workspaces_with_owners
3. Assert returns workspace with correct owner name

**Verifies:** NULL-safe owner-name peer listing ignores team ACL rows

## Sharing Controls (Integration -- modified for wargame-schema-294)

**File:** tests/integration/test_sharing_controls.py (modified)
- Existing grant_share tests now additionally assert `entry.team_id is None` to confirm workspace-target shape after ACL polymorphism was added

**Verifies:** Existing sharing flow produces workspace-target ACL entries (not accidentally team-target)

## Card Positioning (E2E)

### Initial positioning -- non-zero, no overlap
**File:** tests/e2e/test_card_layout.py::TestCardPositioning::test_initial_positioning_non_zero_no_overlap
1. Create workspace with a paragraph of text, seed tags
2. Create 3 highlights at different character offsets (0-20, 40-60, 80-100)
3. Wait for positionCards() via requestAnimationFrame
4. Read computed `style.top` for each card
5. Assert all tops >= 0 and strictly increasing

**Verifies:** AC1.1 -- cards get non-zero top values and do not overlap after initial positioning

### Scroll recovery -- no solitaire collapse
**File:** tests/e2e/test_card_layout.py::TestCardPositioning::test_scroll_recovery_no_solitaire_collapse
1. Create workspace with long document (top paragraph + 40 filler paragraphs)
2. Create 2 highlights near the top, record their top positions
3. Scroll doc-container to bottom, then back to top
4. Wait for positionCards() and cards to become visible
5. Assert positions restored within 5px tolerance

**Verifies:** AC1.3 -- cards restore at original positions after scroll away and back

### Height cache on hidden cards
**File:** tests/e2e/test_card_layout.py::TestCardPositioning::test_height_cache_on_hidden_cards
1. Create workspace with long document
2. Create a highlight near the top, wait for card visible
3. Scroll to bottom so card is hidden
4. Read `data-cached-height` attribute from the card element
5. Assert attribute exists and has a positive integer value

**Verifies:** AC1.4 -- hidden cards have data-cached-height with positive value for layout calculations

### Race condition -- highlights ready flag
**File:** tests/e2e/test_card_layout.py::TestCardPositioning::test_race_condition_highlights_ready
1. Create workspace, visit annotation page, create a highlight
2. Navigate away (/) then back to annotation page (SPA navigation)
3. Wait for `window._highlightsReady === true`
4. Wait for positionCards() via requestAnimationFrame
5. Assert card is visible with non-negative top value

**Verifies:** AC1.2 -- cards positioned correctly after SPA navigation with pre-existing highlights

### Fallback height when never cached
**File:** tests/e2e/test_card_layout.py::TestCardPositioning::test_fallback_height_when_height_never_cached
1. Create workspace with long document
2. Create a highlight near top, wait for card visible
3. Immediately scroll to bottom before positionCards() can cache height
4. Scroll back to top
5. Assert card is visible with non-negative top (using 80px fallback)

**Verifies:** AC1.5 -- card uses 80px fallback when data-cached-height was never set

## Collapsed Cards (E2E)

### Default collapsed with compact header
**File:** tests/e2e/test_card_layout.py::TestCollapsedCards::test_default_collapsed_with_compact_header
1. Create workspace, create a highlight
2. Assert card is visible
3. Assert card-detail section is hidden (collapsed by default)
4. Assert card-expand-btn is visible in compact header

**Verifies:** AC2.1 -- cards are collapsed by default with compact header visible

### Expand and collapse toggle
**File:** tests/e2e/test_card_layout.py::TestCollapsedCards::test_expand_collapse_toggle
1. Create workspace, create a highlight
2. Call expand_card() -- click expand button, wait for detail visible
3. Assert tag-select and comment-input are visible in expanded detail
4. Call collapse_card() -- click collapse button, wait for detail hidden
5. Assert card-detail is hidden again

**Verifies:** AC2.2 + AC2.3 -- expand shows full detail section, collapse hides it

### Author initials in compact header
**File:** tests/e2e/test_card_layout.py::TestCollapsedCards::test_author_initials_in_compact_header
1. Create workspace, create a highlight
2. Read card inner text while collapsed
3. Assert text matches regex `[A-Z]\.` (dot-separated initials pattern)

**Verifies:** AC2.4 -- compact header shows author initials (e.g. "B.B.S.")

### Push down on expand
**File:** tests/e2e/test_card_layout.py::TestCollapsedCards::test_push_down_on_expand
1. Create workspace, create 2 highlights
2. Record second card's top position
3. Expand the first card
4. Wait for positionCards() to re-run
5. Assert second card's top position increased

**Verifies:** AC2.5 -- expanding first card pushes subsequent cards down

### Viewer sees no tag select or comment input
**File:** tests/e2e/test_card_layout.py::TestCollapsedCards::test_viewer_sees_no_tag_select_or_comment_input
1. Owner creates workspace with a highlight (separate browser context)
2. Close owner context
3. Viewer opens same workspace with "viewer" permission (separate browser context)
4. Expand the card
5. Assert tag-select count is 0
6. Assert comment-input count is 0

**Verifies:** AC2.6 + AC2.7 -- viewer cannot see tag dropdown or comment input in expanded cards

## Wargame Codename Generation (Unit)

### Returns uppercase slug from patched generator
**File:** tests/unit/test_codenames.py::TestGenerateCodename::test_returns_uppercase_slug_from_patched_generator
1. Patch coolname generate_slug to return "bold-griffin"
2. Call generate_codename with empty existing set
3. Assert result is "BOLD-GRIFFIN"

**Verifies:** Codenames are normalized to uppercase

### Retries until it finds a unique slug
**File:** tests/unit/test_codenames.py::TestGenerateCodename::test_retries_until_it_finds_a_unique_slug
1. Patch generate_slug to yield "bold-griffin" then "calm-otter"
2. Call generate_codename with {"BOLD-GRIFFIN"} as existing set
3. Assert result is "CALM-OTTER" and generator was called twice

**Verifies:** Collision retry loop works correctly

### Raises after max attempts when all candidates collide
**File:** tests/unit/test_codenames.py::TestGenerateCodename::test_raises_after_max_attempts_when_all_candidates_collide
1. Patch generate_slug to always return "bold-griffin"
2. Call generate_codename with {"BOLD-GRIFFIN"} existing, max_attempts=3
3. Assert RuntimeError raised

**Verifies:** Exhausting the retry cap raises rather than looping forever

## Wargame Roster Parsing (Unit)

### Parses full email/team/role rows
**File:** tests/unit/test_roster.py::TestParseRoster::test_parses_full_email_team_role_rows
1. Parse CSV with email, team, role columns (mixed whitespace/case)
2. Assert two RosterEntry objects with normalized email (lowercase), trimmed team, lowercase role

**Verifies:** Full roster rows become concrete RosterEntry values with normalization

### Defaults role when header is missing
**File:** tests/unit/test_roster.py::TestParseRoster::test_defaults_role_when_header_is_missing
1. Parse CSV with only email and team columns
2. Assert every entry has role="editor"

**Verifies:** Missing role header defaults every row to editor

### Defaults role when cell is blank
**File:** tests/unit/test_roster.py::TestParseRoster::test_defaults_role_when_cell_is_blank
1. Parse CSV where one row has blank role cell
2. Assert blank-role row gets "editor", non-blank row keeps its value

**Verifies:** Blank role cells default to editor per-row

### Returns None for every team when team header is missing
**File:** tests/unit/test_roster.py::TestParseRoster::test_returns_none_for_every_team_when_team_header_is_missing
1. Parse CSV with only email and role columns
2. Assert every entry has team=None

**Verifies:** Missing team header produces explicit None team values

### Empty CSV reports empty file error
**File:** tests/unit/test_roster.py::TestParseRosterValidation::test_empty_csv_reports_empty_file_error
1. Parse empty string
2. Assert RosterParseError with "empty roster csv" and empty line_numbers

**Verifies:** Empty CSV is distinguished from a missing email header

### Missing email header reports structural header error
**File:** tests/unit/test_roster.py::TestParseRosterValidation::test_missing_email_header_reports_structural_header_error
1. Parse CSV with team/role headers but no email header
2. Assert RosterParseError with "missing required email header"

**Verifies:** Missing required header is a structural error

### Duplicate email reports both physical line numbers
**File:** tests/unit/test_roster.py::TestParseRosterValidation::test_duplicate_email_reports_both_physical_line_numbers
1. Parse CSV with same email in mixed case on lines 2 and 3
2. Assert RosterParseError with "duplicate email" and line_numbers=(2, 3)

**Verifies:** Duplicate normalized emails include both line numbers for diagnostics

### Malformed email reports its line number
**File:** tests/unit/test_roster.py::TestParseRosterValidation::test_malformed_email_reports_its_line_number
1. Parse CSV with "not-an-email" on line 2
2. Assert RosterParseError with "malformed email" and line_numbers=(2,)

**Verifies:** Malformed email raises with the offending line number

### Invalid role reports line number and value
**File:** tests/unit/test_roster.py::TestParseRosterValidation::test_invalid_role_reports_line_number_and_value
1. Parse CSV with role="observer" on line 2
2. Assert RosterParseError matching "observer" with line_numbers=(2,)

**Verifies:** Unsupported roles are rejected with context

### Auto-assign assigns entries in strict round-robin order
**File:** tests/unit/test_roster.py::TestAutoAssignTeams::test_assigns_entries_in_strict_round_robin_order
1. Create 5 entries with team=None
2. Call auto_assign_teams with team_count=3
3. Assert returned entries have teams AUTO-1, AUTO-2, AUTO-3, AUTO-1, AUTO-2
4. Assert original entries are unmodified (immutability)

**Verifies:** Round-robin team labels cycle by position

### Auto-assign rejects non-positive team count
**File:** tests/unit/test_roster.py::TestAutoAssignTeams::test_rejects_non_positive_team_count
1. Call auto_assign_teams with team_count=0
2. Assert ValueError raised

**Verifies:** Non-positive team counts are rejected

## Wargame Team CRUD Error Types (Unit)

### DuplicateCodenameError stores activity_id, codename, and message
**File:** tests/unit/test_wargame_team_crud.py::TestDuplicateCodenameError::test_stores_activity_id_codename_and_message
1. Create DuplicateCodenameError with activity_id and "RED-FOX"
2. Assert activity_id, codename attributes correct
3. Assert "RED-FOX" in str(error)

**Verifies:** Exception exposes duplicate context for callers

## User Find-or-Create (Integration)

### First call creates user
**File:** tests/integration/test_user_find_or_create.py::TestFindOrCreateUser::test_first_call_creates_user
1. Call find_or_create_user with unique email
2. Assert created=True and user fields match

**Verifies:** First call creates a user row

### Second call reuses existing user
**File:** tests/integration/test_user_find_or_create.py::TestFindOrCreateUser::test_second_call_reuses_existing_user
1. Call find_or_create_user twice with same email
2. Assert first created=True, second created=False, same user.id

**Verifies:** Idempotent find-or-create returns existing row

### Mixed case email reuses lowercased user
**File:** tests/integration/test_user_find_or_create.py::TestFindOrCreateUser::test_mixed_case_email_reuses_lowercased_user
1. Create user with mixed-case email
2. Find with lowercased email
3. Assert same user.id returned

**Verifies:** Email normalization prevents case-sensitive duplicates

### Second call preserves original display name
**File:** tests/integration/test_user_find_or_create.py::TestFindOrCreateUser::test_second_call_preserves_original_display_name
1. Create user with display_name="Original Name"
2. Find again with display_name="Updated Name"
3. Assert display_name is still "Original Name"

**Verifies:** Upsert ON CONFLICT DO NOTHING preserves existing display_name

### Session helper reuses user within one session
**File:** tests/integration/test_user_find_or_create.py::TestFindOrCreateUserWithSession::test_helper_reuses_user_within_one_session
1. Open one async session
2. Call _find_or_create_user_with_session twice with same email
3. Assert one DB row, same user.id, first display_name preserved

**Verifies:** Helper composes inside one session without creating duplicates

## Wargame Team CRUD (Integration)

### Create team persists generated codename and get_team round-trips
**File:** tests/integration/test_wargame_team_crud.py::TestCreateAndGetTeam::test_create_team_persists_generated_codename_and_get_team_round_trips
1. Create wargame activity, patch codename generator to return "RED-FOX"
2. Call create_team, then get_team
3. Assert both return matching id, activity_id, codename

**Verifies:** create_team persists through the public service boundary

### Get team returns None for missing team
**File:** tests/integration/test_wargame_team_crud.py::TestCreateAndGetTeam::test_get_team_returns_none_for_missing_team
1. Call get_team with random UUID
2. Assert None returned

**Verifies:** Missing teams return None rather than raising

### Create team uses explicit empty codename without generating
**File:** tests/integration/test_wargame_team_crud.py::TestCreateAndGetTeam::test_create_team_uses_explicit_empty_codename_without_generating
1. Create team with codename=""
2. Assert generator was never called and codename is ""

**Verifies:** Explicit codenames (even empty string) bypass generation

### Batch create teams avoids codename collisions
**File:** tests/integration/test_wargame_team_crud.py::TestCreateAndListTeams::test_create_teams_persists_distinct_codenames_after_existing_team
1. Create one existing team "EXISTING", patch generator with candidate list
2. Call create_teams(3) -- generator skips "EXISTING"
3. Assert 3 new teams with distinct codenames, all 4 visible via list_teams

**Verifies:** Batch creation avoids collisions within one activity

### List teams filters to one activity in creation order
**File:** tests/integration/test_wargame_team_crud.py::TestCreateAndListTeams::test_list_teams_filters_to_one_activity_in_created_order
1. Create teams in two activities
2. list_teams for activity_one
3. Assert only activity_one teams returned, in creation order

**Verifies:** list_teams scopes to one activity and preserves order

### Create teams rejects non-positive count
**File:** tests/integration/test_wargame_team_crud.py::TestCreateAndListTeams::test_create_teams_rejects_non_positive_count_without_new_rows
1. Create one existing team, then create_teams(0)
2. Assert ValueError raised, existing team preserved

**Verifies:** Non-positive team counts rejected without side effects

### Rename team updates persisted codename
**File:** tests/integration/test_wargame_team_crud.py::TestRenameTeam::test_rename_team_updates_persisted_codename
1. Create team "ALPHA", rename to "BRAVO"
2. Assert get_team and list_teams both show "BRAVO"

**Verifies:** Rename persists through service boundary

### Rename team raises DuplicateCodenameError and preserves original
**File:** tests/integration/test_wargame_team_crud.py::TestRenameTeam::test_rename_team_raises_duplicate_codename_and_preserves_original
1. Create "ALPHA" and "BRAVO" teams
2. Attempt rename BRAVO to "ALPHA"
3. Assert DuplicateCodenameError, both teams unchanged

**Verifies:** Duplicate rename is translated and rolled back

### Rename team returns None for missing team
**File:** tests/integration/test_wargame_team_crud.py::TestRenameTeam::test_rename_team_returns_none_for_missing_team
1. Call rename_team with random UUID
2. Assert None returned

**Verifies:** Missing teams return None rather than raising

### Delete team cascades through ACL and messages
**File:** tests/integration/test_wargame_team_crud.py::TestDeleteTeam::test_delete_team_removes_team_acl_entries_and_messages
1. Create team, add ACL entry and message
2. Delete team
3. Assert team, ACL entry, and message all gone

**Verifies:** CASCADE deletion removes dependent rows

### Delete team returns False for missing team
**File:** tests/integration/test_wargame_team_crud.py::TestDeleteTeam::test_delete_team_returns_false_for_missing_team
1. Create one team, delete random UUID
2. Assert False returned, existing team preserved

**Verifies:** Missing teams return False without side effects

## Wargame Team ACL (Integration)

### Resolve returns None when no team ACL entry exists
**File:** tests/integration/test_wargame_team_acl.py::TestResolveTeamPermission::test_resolve_team_permission_returns_none_when_no_team_acl_entry_exists
1. Create team and user with no ACL entry
2. Assert resolve_team_permission returns None

**Verifies:** Missing team ACL entries resolve to None

### Resolve returns exact stored permission
**File:** tests/integration/test_wargame_team_acl.py::TestResolveTeamPermission::test_resolve_team_permission_returns_exact_stored_permission
1. Create team, user, insert ACL entry with "editor" directly
2. Assert resolve_team_permission returns "editor"

**Verifies:** Exact stored permission round-trips unchanged

### Resolve returns owner permission unchanged
**File:** tests/integration/test_wargame_team_acl.py::TestResolveTeamPermission::test_resolve_team_permission_owner_permission_round_trips_unchanged
1. Create team, user, insert ACL entry with "owner" directly
2. Assert resolve_team_permission returns "owner"

**Verifies:** Service uses real permission names, not hardcoded mappings

### List team members returns deterministic order
**File:** tests/integration/test_wargame_team_acl.py::TestListTeamMembers::test_list_team_members_returns_deterministic_member_order
1. Create team with owner, editor, two viewers (inserted in random order)
2. Call list_team_members
3. Assert order: owner first, then editor, then viewers by name then email

**Verifies:** Members ordered by can_edit DESC, level DESC, display_name, email

### Grant creates new team ACL row
**File:** tests/integration/test_wargame_team_acl.py::TestGrantTeamPermission::test_grant_team_permission_creates_new_team_acl_row
1. Create team and user, grant "viewer"
2. Assert ACL entry created with correct team_id, user_id, permission
3. Verify exactly one DB row exists

**Verifies:** Granting a new permission creates a team ACL row

### Grant upsert updates existing row without duplicate
**File:** tests/integration/test_wargame_team_acl.py::TestGrantTeamPermission::test_grant_team_permission_upsert_updates_existing_row_without_duplicate
1. Grant "viewer" then grant "editor" to same user/team
2. Assert same row id, permission updated, exactly one DB row

**Verifies:** Upsert semantics -- ON CONFLICT DO UPDATE

### Grant raises ZeroEditorError for last editor downgrade
**File:** tests/integration/test_wargame_team_acl.py::TestGrantTeamPermission::test_grant_team_permission_raises_zero_editor_error_for_last_editor
1. Grant "editor" to sole team member
2. Attempt to downgrade to "viewer"
3. Assert ZeroEditorError with correct team_id, user_id, current/attempted permissions
4. Assert permission unchanged at "editor"

**Verifies:** Zero-editor invariant prevents leaving team without editable member

### Grant allows downgrade when owner still can_edit
**File:** tests/integration/test_wargame_team_acl.py::TestGrantTeamPermission::test_grant_team_permission_allows_downgrade_when_owner_still_can_edit
1. Grant "owner" and "editor" to two users
2. Downgrade editor to "viewer"
3. Assert success -- owner preserves the can_edit invariant

**Verifies:** Classifier-based downgrade succeeds when another editable member remains

### Grant rejects unknown permission name
**File:** tests/integration/test_wargame_team_acl.py::TestGrantTeamPermission::test_grant_team_permission_rejects_unknown_permission_name
1. Grant "viewer" to user, then attempt "observer"
2. Assert ValueError("unknown permission"), original permission unchanged

**Verifies:** Unknown permissions rejected without side effects

### Revoke raises ZeroEditorError for last editor
**File:** tests/integration/test_wargame_team_acl.py::TestRevokeTeamPermission::test_revoke_team_permission_raises_zero_editor_error_for_last_editor
1. Grant "editor" to sole team member
2. Attempt revoke
3. Assert ZeroEditorError, permission unchanged

**Verifies:** Zero-editor invariant applies to revocations too

### Revoke succeeds when owner survives
**File:** tests/integration/test_wargame_team_acl.py::TestRevokeTeamPermission::test_revoke_team_permission_succeeds_when_owner_survives
1. Grant "owner" and "editor" to two users
2. Revoke the editor
3. Assert True returned, editor's permission is None, owner unchanged

**Verifies:** Revocation succeeds when another can_edit member remains

### Revoke returns False for missing entry
**File:** tests/integration/test_wargame_team_acl.py::TestRevokeTeamPermission::test_revoke_team_permission_returns_false_for_missing_entry
1. Grant "owner" to one user, revoke a different user
2. Assert False returned, owner ACL unchanged

**Verifies:** Missing entries return False rather than raising

### Wrapper update_team_permission enforces zero-editor invariant
**File:** tests/integration/test_wargame_team_acl.py::TestTeamPermissionWrappers::test_update_team_permission_raises_zero_editor_error_for_last_editor
1. Grant "editor" to sole member
2. Call update_team_permission to "viewer"
3. Assert ZeroEditorError, permission unchanged

**Verifies:** Wrapper delegates to grant path with invariant enforcement

### Wrapper names support promotion and viewer removal
**File:** tests/integration/test_wargame_team_acl.py::TestTeamPermissionWrappers::test_wrapper_names_support_promotion_and_viewer_removal
1. Create owner, viewer-to-promote, viewer-to-remove
2. Call update_team_permission (promote to editor) and remove_team_member
3. Assert promotion succeeded, removal succeeded, owner unchanged

**Verifies:** Convenience wrappers correctly compose grant/revoke paths

### Public db package exports full Phase 3 ACL surface
**File:** tests/integration/test_wargame_team_acl.py::TestTeamPermissionWrappers::test_promptgrimoire_db_exports_full_phase_three_api
1. Import ZeroEditorError and all ACL functions from promptgrimoire.db
2. Assert all are importable and callable

**Verifies:** Public API surface is complete and importable

## Wargame Roster Ingestion (Integration)

### Explicit-team ingest creates users, teams, ACL, and report
**File:** tests/integration/test_roster_ingestion.py::TestNamedTeamRosterIngestion::test_explicit_team_ingest_creates_users_teams_acl_and_report
1. Create wargame activity
2. Ingest CSV with alice=ALPHA/editor, bob=BRAVO/viewer
3. Assert report: 2 entries, 2 teams, 2 users, 2 memberships, 0 updates
4. Verify persisted teams, users, and memberships match

**Verifies:** Named-team ingest persists users, teams, and ACL rows atomically

### Named-team ingest reuses existing team codename
**File:** tests/integration/test_roster_ingestion.py::TestNamedTeamRosterIngestion::test_named_team_ingest_reuses_existing_team_codename
1. Pre-create team "ALPHA"
2. Ingest CSV referencing "ALPHA" and new "BRAVO"
3. Assert teams_created=1 (only BRAVO), ALPHA team.id preserved

**Verifies:** Existing codenames are reused rather than duplicated

### Auto-assign distributes members round-robin across generated teams
**File:** tests/integration/test_roster_ingestion.py::TestAutoAssignRosterIngestion::test_auto_assign_distributes_members_round_robin_across_generated_teams
1. Ingest 4-member teamless CSV with team_count=2
2. Assert 2 teams created with real codenames (not AUTO-*)
3. Assert round-robin distribution: team1 gets members 1,3; team2 gets members 2,4

**Verifies:** Auto-assign mode creates teams and distributes via round-robin

### Auto-assign without team_count raises and leaves no rows
**File:** tests/integration/test_roster_ingestion.py::TestAutoAssignRosterIngestion::test_auto_assign_without_team_count_raises_and_leaves_no_rows
1. Ingest teamless CSV without team_count
2. Assert ValueError("team_count")
3. Verify zero teams, users, and memberships in DB

**Verifies:** Atomicity -- validation failure rolls back everything

### Mixed mode raises and leaves no rows
**File:** tests/integration/test_roster_ingestion.py::TestAutoAssignRosterIngestion::test_mixed_mode_raises_and_leaves_no_rows
1. Ingest CSV where some entries have team names and others are blank
2. Assert ValueError("mixed")
3. Verify zero teams, users, and memberships in DB

**Verifies:** Mixed named+blank teams rejected with zero side effects

### Auto-assign reuses existing teams by created_at order
**File:** tests/integration/test_roster_ingestion.py::TestAutoAssignRosterIngestion::test_auto_assign_reuses_existing_teams_by_created_at_order
1. First ingest creates 2 teams via team_count=2
2. Second ingest with same team_count reuses existing teams
3. Assert teams_created=0 and team IDs unchanged

**Verifies:** Repeat auto-assign re-imports reuse teams by creation order

### Auto-assign team_count mismatch raises with rows unchanged
**File:** tests/integration/test_roster_ingestion.py::TestAutoAssignRosterIngestion::test_auto_assign_team_count_mismatch_raises_and_leaves_rows_unchanged
1. First ingest with team_count=2 creates 2 teams
2. Second ingest with team_count=3
3. Assert ValueError("team_count"), existing teams and memberships unchanged

**Verifies:** Team count mismatch rejected, existing state preserved

### Re-import updates role and retains omitted member
**File:** tests/integration/test_roster_ingestion.py::TestAdditiveReimport::test_reimport_updates_role_and_retains_omitted_member
1. Import alice=editor, bob=viewer, carol=viewer on ALPHA
2. Re-import alice=editor, bob=editor (carol omitted)
3. Assert bob updated to editor, carol still viewer (additive)

**Verifies:** Re-imports are additive -- omitted members keep their ACL

### Re-import preserves existing user display name
**File:** tests/integration/test_roster_ingestion.py::TestAdditiveReimport::test_reimport_preserves_existing_user_display_name
1. Import alice, manually set display_name to "Dr Alice Custom"
2. Re-import same alice
3. Assert display_name still "Dr Alice Custom"

**Verifies:** Upsert ON CONFLICT DO NOTHING preserves existing user data

### Editor handoff swap succeeds with can_edit ordering
**File:** tests/integration/test_roster_ingestion.py::TestAdditiveReimport::test_editor_handoff_swap_succeeds_with_can_edit_ordering
1. Import Alice=editor, Bob=viewer on ALPHA
2. Re-import Alice=viewer, Bob=editor (simultaneous swap)
3. Assert both permissions updated without ZeroEditorError

**Verifies:** Editor-first grant ordering prevents false zero-editor violations

### Auto-assign re-import preserves existing ACL rows
**File:** tests/integration/test_roster_ingestion.py::TestAdditiveReimport::test_auto_assign_reimport_preserves_existing_acl_rows
1. First auto-assign import creates teams and ACL rows
2. Second auto-assign import adds new members
3. Assert first-import ACL rows survive (additive)

**Verifies:** Auto-assign re-imports are additive like named-team re-imports

### Failure after partial writes rolls back all rows
**File:** tests/integration/test_roster_ingestion.py::TestAtomicRollback::test_failure_after_partial_writes_rolls_back_all_rows
1. Monkeypatch grant to succeed once then raise RuntimeError
2. Ingest CSV with 2 entries
3. Assert RuntimeError raised, zero teams/users/memberships in DB

**Verifies:** Any mid-ingest failure rolls back the entire transaction

### Public API export smoke test
**File:** tests/integration/test_roster_ingestion.py::TestPublicAPIExport::test_roster_report_and_ingest_importable_from_db_package
1. Import RosterReport and ingest_roster from promptgrimoire.db
2. Assert callable and expected attributes present

**Verifies:** Public API surface is importable from the db package

## PDF Export Filename Policy

### Name splitting: two-token, multi-token, single-token, blank
**File:** tests/unit/export/test_filename_policy.py::TestSplitOwnerDisplayName
1. Two-token name → (last, first): "Ada Lovelace" → ("Lovelace", "Ada")
2. Multi-token → first and last tokens only: "Mary Jane Smith" → ("Smith", "Mary")
3. Single-token → duplicated: "Plato" → ("Plato", "Plato")
4. None, empty, whitespace → ("Unknown", "Unknown")

**Verifies:** AC2.1–AC2.4 -- deterministic name parsing heuristic

### Safe segment: transliteration, punctuation, emoji
**File:** tests/unit/export/test_filename_policy.py::TestSafeSegment
1. Diacritics transliterated: "José" → "Jose", "Núñez" → "Nunez"
2. Punctuation/path separators → underscore: "draft: final!" → "draft_final"
3. Repeated underscores collapsed, leading/trailing stripped
4. Emoji-only input → empty string; mixed emoji+ASCII → ASCII preserved

**Verifies:** AC2.4–AC2.6 -- ASCII-safe filename sanitisation

### Stem assembly: short, truncation cascade, budget
**File:** tests/unit/export/test_filename_policy.py::TestBuildPdfExportStem
1. Short stem returned without truncation
2. Overlong workspace trimmed before activity
3. Non-negotiable segments (course, last, date) never truncated
4. Activity trimmed after workspace exhausted
5. First name reduced to 1-char initial when workspace+activity both exhausted
6. Pathological overflow (90-char last name) preserved — budget exceeded intentionally
7. Non-pathological cases fit within 100 chars

**Verifies:** AC3.1–AC3.7 -- truncation priority and filename budget

### Workspace deduplication and fallbacks
**File:** tests/unit/export/test_filename_policy.py::TestBuildPdfExportStem
1. Workspace suppressed when raw title equals activity title (default clone title)
2. Workspace kept when raw titles differ even if slugs normalise identically ("José"/"Jose")
3. Workspace fallback "Workspace" not suppressed by activity normalising to same slug
4. Blank workspace → "Workspace", blank owner → "Unknown_Unknown", blank course → "Unplaced", blank activity → "Loose_Work"

**Verifies:** Deduplication uses raw comparison; fallbacks applied by builder

### Workspace export metadata resolution
**File:** tests/integration/test_workspace_export_metadata.py::TestGetWorkspaceExportMetadata
1. Activity-placed workspace returns owner display name, course code, activity title, workspace title from DB
2. Course-placed workspace returns course code, activity_title=None
3. Fully loose workspace returns course_code=None, activity_title=None
4. Blank workspace title returned as-is (fallback applied by builder)
5. Blank owner display name returned as-is (fallback applied by builder)
6. Missing workspace returns None

**Verifies:** AC1.1–AC1.6 -- viewer-agnostic metadata resolution via ACL join

### Workspace export metadata filename contract
**File:** tests/integration/test_workspace_export_metadata.py::TestWorkspaceExportMetadataFilenameContract
1. Activity-placed: stem uses owner's surname, not viewer's name
2. Course-placed: stem contains course code + "Loose_Work" fallback
3. Loose: stem starts with "Unplaced_" and contains "Loose_Work"
4. Blank title: stem contains "Workspace" segment
5. Blank owner: stem contains "Unknown_Unknown"
6. Missing workspace: metadata is None (no stem built)

**Verifies:** Integration of metadata resolver with filename builder

### Annotation page export filename wiring
**File:** tests/integration/test_annotation_pdf_export_filename_ui.py
1. Annotate tab export uses policy-based filename (not workspace_{id})
2. Respond tab export uses same filename for same workspace
3. Loose workspace export uses "Unplaced" and "Loose_Work" fallbacks

**Verifies:** AC4.3 -- NiceGUI annotation page passes correct context to builder

### E2E browser suggested filename
**File:** tests/e2e/test_pdf_export_filename.py
1. Fast-lane (.tex): browser suggested filename matches policy stem
2. Slow-lane (.pdf): when E2E_SKIP_LATEXMK unset, suggested filename ends in .pdf
3. Cross-tab consistency: annotate and respond tabs produce identical filenames

**Verifies:** AC5.3, AC5.4, AC4.3 -- browser download filename matches policy end-to-end

## Document Management (Unit)

### Document edit eligibility
**File:** tests/unit/test_document_management.py::TestCanEditDocument
1. Document with zero annotations and no source_document_id is editable
2. Document with annotations (count > 0) is not editable
3. Template clone (has source_document_id) with zero annotations is not editable
4. Template clone with annotations is not editable

**Verifies:** can_edit_document() enforces the edit guard: only user-uploaded documents with no annotations may be edited

## Workspace Document CRUD (Integration)

### Update document content
**File:** tests/integration/test_workspace_documents.py::TestUpdateDocumentContent
1. Create workspace and document, update content with new HTML, verify content persisted
2. Update content, verify paragraph_map rebuilt to match new HTML (3 paragraphs = 3 entries)
3. Clear search_dirty, update content, verify workspace.search_dirty set to True
4. Attempt update with non-existent document_id, expect ValueError("not found")
5. Create doc in workspace A, attempt update with workspace B id, expect ValueError("belongs to workspace")

**Verifies:** update_document_content() persists HTML, rebuilds paragraph map, marks FTS dirty, and validates ownership

## Document Upload & Paste E2E

### Paste renders without page reload
**File:** tests/e2e/test_document_upload.py::TestDocumentUploadNoReload::test_paste_renders_without_url_change
1. Capture URL before paste
2. Paste HTML via clipboard and click Add Document
3. Wait for text walker initialisation
4. Assert document text visible in doc-container
5. Assert URL unchanged
6. Assert content form hidden (multi-document disabled)

**Verifies:** AC4.1 -- pasted document renders in-place without navigation or reload

### DOCX upload renders without page reload
**File:** tests/e2e/test_document_upload.py::TestDocumentUploadNoReload::test_docx_upload_renders_without_url_change
1. Set file input to DOCX fixture path
2. Confirm content type dialog
3. Wait for text walker (30s timeout for conversion)
4. Assert text from DOCX visible in doc-container
5. Assert URL unchanged
6. Assert content form hidden

**Verifies:** AC1.2, AC4.1 -- DOCX upload-to-annotate pipeline works end-to-end

### PDF upload renders without page reload
**File:** tests/e2e/test_document_upload.py::TestDocumentUploadNoReload::test_pdf_upload_renders_without_url_change
1. Set file input to PDF fixture path
2. Confirm content type dialog
3. Wait for text walker (30s timeout for extraction)
4. Assert text from PDF ("Lawlis") visible in doc-container
5. Assert URL unchanged
6. Assert content form hidden

**Verifies:** AC2.2, AC4.1 -- PDF upload-to-annotate pipeline works end-to-end

## Document Edit Mode E2E

### Edit button shown for editable documents
**File:** tests/e2e/test_edit_mode.py::TestEditModeButton
1. Paste document into workspace, open Manage Documents dialog
2. Assert edit button visible for document with zero annotations
3. Add highlight annotation, reopen dialog
4. Assert edit button NOT visible for annotated document

**Verifies:** AC3.1, AC3.2 -- edit button visibility tracks annotation count

### Edit mode save persists content
**File:** tests/e2e/test_edit_mode.py::TestEditModeSave
1. Paste document, open Manage Documents, click edit
2. Verify editor pre-populated with document content
3. Clear editor and type new content
4. Click save, wait for dialog to close
5. Verify new content visible in document container
6. Query DB directly to verify content persisted and paragraph_map rebuilt

**Verifies:** AC3.1, AC3.3 -- edit mode WYSIWYG save persists HTML and rebuilds paragraph map

## Wargame Turn Cycle -- Pure Domain Helpers (Unit)

### Bootstrap template expansion
**File:** tests/unit/test_turn_cycle.py::TestExpandBootstrap
1. Call expand_bootstrap with template containing {codename} placeholder
2. Assert codename substituted into output
3. Verify JSON-like braces ({}) in template are not corrupted
4. Verify template without {codename} returned unchanged

**Verifies:** str.replace-based expansion is safe for user-authored templates with arbitrary brace content

### Deadline calculation
**File:** tests/unit/test_turn_cycle.py::TestCalculateDeadline
1. Delta mode: publish_time + timer_delta returns correct future datetime
2. Wall-clock future today: returns same day at specified time
3. Wall-clock past today: rolls to next day
4. Wall-clock equal to publish time: rolls to next day
5. Both fields set: raises ValueError
6. Neither field set: raises ValueError

**Verifies:** XOR enforcement between timer_delta and timer_wall_clock, correct next-occurrence logic

### CRDT move buffer extraction
**File:** tests/unit/test_turn_cycle.py::TestExtractMoveText
1. Create CRDT doc with content_markdown text, extract via extract_move_text
2. Assert populated buffer returns markdown string
3. Assert None input returns NO_MOVE_SENTINEL
4. Assert whitespace-only content returns NO_MOVE_SENTINEL
5. Assert empty CRDT document (no content_markdown key) returns NO_MOVE_SENTINEL

**Verifies:** AC4.1-AC4.3 -- move buffer extraction handles all edge cases with sentinel fallback

### t-string prompt rendering
**File:** tests/unit/test_turn_cycle.py::TestRenderPrompt
1. Render static t-string, assert exact text output
2. Render t-string with interpolated variable, assert stringified
3. Test !r conversion (repr), !s conversion (str), !a conversion (ascii)

**Verifies:** render_prompt correctly handles all Python conversion specifiers on t-string Interpolation objects

### Turn prompt assembly
**File:** tests/unit/test_turn_cycle.py::TestBuildTurnPrompt
1. Call build_turn_prompt with move text and game state
2. Assert output contains both values and XML tags (game_state, cadet_orders)

**Verifies:** Turn agent user prompt includes game_state and cadet_orders in XML structure

### Summary prompt assembly
**File:** tests/unit/test_turn_cycle.py::TestBuildSummaryPrompt
1. Call build_summary_prompt with response text
2. Assert output contains response text and XML response tags

**Verifies:** Summary agent user prompt wraps response in XML structure

## Wargame Turn Cycle -- PydanticAI Agents (Unit)

### turn_agent returns structured TurnResult
**File:** tests/unit/test_wargame_agents.py::TestTurnAgent
1. Override turn_agent model with TestModel, run with test prompt
2. Assert output is TurnResult with response_text and game_state strings
3. Test with custom instructions (runtime system_prompt injection)
4. Test message history round-trip: serialise via pydantic_core, deserialise via ModelMessagesTypeAdapter, run second call with restored history

**Verifies:** AC5.1 -- turn_agent produces structured TurnResult; message history survives serialisation cycle

### summary_agent returns structured StudentSummary
**File:** tests/unit/test_wargame_agents.py::TestSummaryAgent
1. Override summary_agent model with TestModel, run with test prompt
2. Assert output is StudentSummary with summary string
3. Test with custom instructions (summary_system_prompt injection)

**Verifies:** AC5.4 -- summary_agent produces structured StudentSummary

### Output type structure
**File:** tests/unit/test_wargame_agents.py::TestOutputTypes
1. Construct TurnResult directly, verify response_text and game_state fields
2. Construct StudentSummary directly, verify summary field

**Verifies:** Pydantic model field access works as expected

## Wargame Turn Cycle -- Deadline Worker (Unit)

### Expired deadline fires callback
**File:** tests/unit/test_deadline_worker.py::test_check_expired_deadlines_fires_for_expired
1. Mock DB session returning one expired activity ID
2. Mock on_deadline_fired callback
3. Call check_expired_deadlines, assert callback called with correct activity ID
4. Assert return value is 1 (one activity processed)

**Verifies:** Worker correctly dispatches expired deadlines to on_deadline_fired

### Future deadlines not fired
**File:** tests/unit/test_deadline_worker.py::test_check_expired_deadlines_skips_future
1. Mock DB session returning empty result set
2. Call check_expired_deadlines, assert returns 0

**Verifies:** Worker does not fire callbacks when no deadlines are expired

### Exception isolation between activities
**File:** tests/unit/test_deadline_worker.py::test_check_expired_deadlines_exception_doesnt_prevent_others
1. Mock DB returning two activity IDs
2. Mock on_deadline_fired to raise on first, succeed on second
3. Assert return value is 1 (only second succeeded)
4. Assert both activities were attempted (call log has 2 entries)

**Verifies:** Exception in one activity does not prevent processing others

### No pending deadlines returns None
**File:** tests/unit/test_deadline_worker.py::test_next_deadline_seconds_returns_none_when_no_deadlines
1. Mock DB returning None for MIN(current_deadline)
2. Call _next_deadline_seconds, assert returns None

**Verifies:** Adaptive sleep correctly identifies when no deadlines are pending

## Wargame Turn Cycle -- Deadline Worker (Integration)

### AC2.1: Expired deadline fires callback
**File:** tests/integration/test_deadline_worker.py::TestDeadlineWorkerIntegration::test_ac2_1_fires_for_expired_deadline
1. Create wargame activity with team having current_deadline 1 minute in the past
2. Monkeypatch on_deadline_fired to record calls
3. Call check_expired_deadlines against real database
4. Assert activity_id appears in fired list

**Verifies:** AC2.1 -- real database query finds expired deadlines and dispatches callback

### AC2.2: Misfire recovery
**File:** tests/integration/test_deadline_worker.py::TestDeadlineWorkerIntegration::test_ac2_2_misfire_recovery
1. Create wargame activity with team having current_deadline 1 hour in the past
2. Monkeypatch on_deadline_fired, call check_expired_deadlines
3. Assert stale activity fires (simulates server-was-down recovery)

**Verifies:** AC2.2 -- stale deadlines from server downtime fire on next poll cycle

### AC2.3: Cancelled deadline ignored
**File:** tests/integration/test_deadline_worker.py::TestDeadlineWorkerIntegration::test_ac2_3_cancelled_deadline_ignored
1. Create wargame activity with team having current_deadline=None
2. Monkeypatch on_deadline_fired, call check_expired_deadlines
3. Assert activity_id NOT in fired list

**Verifies:** AC2.3 -- NULL current_deadline means team is not polled

### Idempotency: locked teams skipped
**File:** tests/integration/test_deadline_worker.py::TestDeadlineWorkerIntegration::test_idempotency_locked_teams_skipped
1. Create wargame activity with team having expired deadline but round_state='locked'
2. Monkeypatch on_deadline_fired, call check_expired_deadlines
3. Assert activity_id NOT in fired list

**Verifies:** Already-locked teams are not reprocessed on subsequent poll cycles

## Wargame Turn Cycle -- Service Layer (Integration)

### AC1.1: Bootstrap expanded with codename
**File:** tests/integration/test_turn_cycle_service.py::TestStartGame::test_ac1_1_bootstrap_expanded_with_codename
1. Create wargame activity with config and 2 teams
2. Call start_game with TestModel override
3. Query seq=1 user message for each team
4. Assert codename appears in message content

**Verifies:** AC1.1 -- scenario bootstrap template is expanded with each team's codename

### AC1.2: AI response with PydanticAI history
**File:** tests/integration/test_turn_cycle_service.py::TestStartGame::test_ac1_2_assistant_message_with_pydantic_history
1. Start game, query seq=2 assistant message for each team
2. Assert metadata_json is not None
3. Deserialise via ModelMessagesTypeAdapter, assert non-empty

**Verifies:** AC1.2 -- assistant message stores serialised PydanticAI message history

### AC1.3: game_state_text populated
**File:** tests/integration/test_turn_cycle_service.py::TestStartGame::test_ac1_3_game_state_text_populated
1. Start game, reload teams
2. Assert game_state_text is not None on each team

**Verifies:** AC1.3 -- TurnResult.game_state is stored on WargameTeam

### AC1.4: Rejects already-started game
**File:** tests/integration/test_turn_cycle_service.py::TestStartGame::test_ac1_4_rejects_already_started
1. Start game once
2. Call start_game again, assert ValueError("game already started")

**Verifies:** AC1.4 -- idempotency guard prevents double-start

### AC5.2/5.3: Message history round-trip
**File:** tests/integration/test_turn_cycle_service.py::TestStartGame::test_ac5_2_ac5_3_metadata_history_round_trip
1. Start game, retrieve assistant message's metadata_json
2. Deserialise via ModelMessagesTypeAdapter
3. Make follow-up turn_agent.run call with restored history
4. Assert second call produces valid TurnResult

**Verifies:** AC5.2-5.3 -- PydanticAI history can be serialised to DB and restored for multi-turn conversation

### AC3.1-3.3: Lock round
**File:** tests/integration/test_turn_cycle_service.py::TestLockRound
1. Set teams to drafting with deadlines, call lock_round
2. Assert all teams have round_state='locked' (AC3.1)
3. Assert current_deadline is None for all teams (AC3.2)
4. Lock teams, try lock_round again, assert ValueError (AC3.3)

**Verifies:** AC3.1-3.3 -- hard-deadline lock transitions, deadline clearing, and state guard

### AC4.1-AC4.3 + AC5.1-AC5.3: Run preprocessing
**File:** tests/integration/test_turn_cycle_service.py::TestRunPreprocessing
1. Start game, advance teams to round 2 locked
2. Set CRDT move buffers on teams, call run_preprocessing with TestModel
3. Assert user message (seq=3) contains extracted markdown (AC4.1)
4. Assert assistant message (seq=4) exists with metadata_json (AC5.1)
5. Test None move buffer produces "No move submitted" sentinel (AC4.2)
6. Test whitespace-only CRDT returns sentinel (AC4.3)
7. Verify PydanticAI history restored from previous round's metadata_json (AC5.2)
8. Verify updated history stored on new assistant message (AC5.3)

**Verifies:** Full preprocessing pipeline: CRDT extraction, turn agent call, history accumulation

### AC8.1: One-response invariant (duplicate preprocessing)
**File:** tests/integration/test_turn_cycle_service.py::TestOneResponseInvariant::test_ac8_1_duplicate_preprocessing_rejected
1. Start game, advance to round 2, run preprocessing once
2. Call run_preprocessing again
3. Assert no duplicate assistant messages (still exactly 1 per round per team)

**Verifies:** AC8.1 -- sequence-number check prevents duplicate assistant messages from repeated preprocessing

### AC6.1-6.5: Publish pipeline
**File:** tests/integration/test_turn_cycle_service.py::TestPublishAll
1. Start game, call publish_all with TestModel overrides
2. Assert student_summary_text populated on each team (AC6.1)
3. Assert current_round incremented (AC6.2)
4. Assert round_state='drafting' (AC6.3)
5. Assert move_buffer_crdt cleared to None (AC6.4)
6. Assert current_deadline set to future datetime (AC6.5)

**Verifies:** AC6.1-6.5 -- publish generates summaries, advances round, resets state, sets next deadline

### AC7.1-7.2: Publish gating
**File:** tests/integration/test_turn_cycle_service.py::TestPublishGating
1. Create activity but do NOT run preprocessing
2. Call publish_all, assert ValueError("missing assistant responses") (AC7.1)
3. Set teams to 'drafting' state, call publish_all, assert ValueError("not all teams in locked state") (AC7.2)

**Verifies:** AC7.1-7.2 -- publish_all rejects if preprocessing incomplete or teams not locked

### AC8.2: One-response invariant on publish
**File:** tests/integration/test_turn_cycle_service.py::TestOneResponseInvariant::test_ac8_2_duplicate_detection_on_publish
1. Start game, publish round 1, run deadline/preprocessing for round 2
2. Publish round 2
3. Assert exactly 2 assistant messages per team (one per round)

**Verifies:** AC8.2 -- no duplicate assistant messages across full round cycle

### AC2.4: Wall-clock deadline rollover
**File:** tests/integration/test_turn_cycle_service.py::TestWallClockDeadline
1. Create config with timer_wall_clock instead of timer_delta
2. Start game, publish_all
3. Assert current_deadline set to next occurrence of wall-clock time
4. Assert deadline timezone is UTC

**Verifies:** AC2.4 -- wall-clock timer mode calculates correct next-day rollover

## Wargame Turn Cycle -- Full Round Trip (Integration)

### Two complete rounds
**File:** tests/integration/test_turn_cycle_e2e.py::TestFullRoundTrip::test_two_full_rounds
1. Create wargame activity with config and 2 teams
2. start_game: verify round=1, state=locked, 2 messages per team (bootstrap)
3. publish_all: verify round=2, state=drafting, summaries populated, deadlines set
4. Simulate player moves via CRDT move buffers
5. on_deadline_fired: verify teams locked, 4 messages per team (move + AI response)
6. publish_all: verify round=3, state=drafting, no duplicate assistant messages

**Verifies:** AC1-AC8 end-to-end -- complete two-round cycle exercises all turn cycle operations

### Empty moves (all teams)
**File:** tests/integration/test_turn_cycle_e2e.py::TestEdgeCases::test_empty_moves_all_teams
1. Start game, publish round 1
2. on_deadline_fired with no move buffers set (all None)
3. Assert user messages contain "No move submitted" sentinel
4. publish_all succeeds, round advances to 3

**Verifies:** Turn cycle handles all-empty moves gracefully (sentinel substitution)

### Mixed moves (some teams have content, others None)
**File:** tests/integration/test_turn_cycle_e2e.py::TestEdgeCases::test_mixed_moves
1. Start game, publish round 1
2. Set CRDT move on first team only, leave second team None
3. on_deadline_fired
4. Assert first team's user message contains move text
5. Assert second team's user message is "No move submitted"
6. publish_all succeeds for both teams

**Verifies:** Mixed move states within an activity are handled correctly per-team

### AC8.3: No duplicate assistants across rounds
**File:** tests/integration/test_turn_cycle_e2e.py::TestEdgeCases::test_ac8_3_no_duplicate_assistants_across_rounds
1. Run two full rounds: start -> publish -> deadline -> publish
2. Query assistant messages per team
3. Assert exactly 2 assistant messages per team (seq=2 bootstrap, seq=4 round 2)

**Verifies:** AC8.3 -- one-response invariant holds across multiple rounds

## Structured Logging -- Core Pipeline (Unit)

### Log file path for main branch
**File:** tests/unit/test_structured_logging.py::TestLogFilePath::test_main_branch_produces_promptgrimoire_jsonl
1. Call _setup_logging with branch="main"
2. Assert `promptgrimoire.jsonl` exists in log directory

**Verifies:** Main/master branch produces the default log filename

### Log file path for feature branch
**File:** tests/unit/test_structured_logging.py::TestLogFilePath::test_feature_branch_produces_slugged_filename
1. Call _setup_logging with branch="structured-logging-339"
2. Assert `promptgrimoire-structured_logging_339.jsonl` exists

**Verifies:** Feature branches get branch-slugged log filenames for isolation

### Log file path for None branch
**File:** tests/unit/test_structured_logging.py::TestLogFilePath::test_none_branch_produces_promptgrimoire_jsonl
1. Call _setup_logging with branch=None
2. Assert `promptgrimoire.jsonl` exists

**Verifies:** Absent branch info falls back to default filename

### RotatingFileHandler configuration
**File:** tests/unit/test_structured_logging.py::TestLogFilePath::test_rotating_file_handler_config
1. Call _setup_logging
2. Find RotatingFileHandler in root logger handlers
3. Assert exactly one, with maxBytes=10MB and backupCount=5

**Verifies:** Log rotation configured correctly (AC6.1)

### Log file permissions 0644
**File:** tests/unit/test_structured_logging.py::TestLogFilePermissions::test_log_file_has_644_permissions
1. Call _setup_logging
2. Stat the log file
3. Assert mode is 0o644

**Verifies:** Log files readable by SSH users without sudo (AC6.2)

### stdlib logger produces valid JSON
**File:** tests/unit/test_structured_logging.py::TestJsonOutput::test_stdlib_logger_produces_valid_json
1. Set up logging, emit via stdlib `logging.getLogger("test.stdlib")`
2. Read last line of log file, parse as JSON
3. Assert event field matches message

**Verifies:** stdlib loggers routed through ProcessorFormatter produce JSON (AC6.3)

### structlog logger produces valid JSON
**File:** tests/unit/test_structured_logging.py::TestJsonOutput::test_structlog_logger_produces_valid_json
1. Set up logging, emit via `structlog.get_logger("test.structlog")`
2. Parse last JSON line
3. Assert event field matches

**Verifies:** structlog loggers produce JSON output (AC6.3)

### Third-party stdlib logger produces JSON with standard fields
**File:** tests/unit/test_structured_logging.py::TestThirdPartyJsonOutput::test_third_party_logger_produces_json_with_standard_fields
1. Set up logging on branch "test-branch"
2. Emit via `logging.getLogger("nicegui.helpers")`
3. Parse JSON from branch-slugged log file
4. Assert standard fields (timestamp, pid, branch, commit) present

**Verifies:** Third-party libraries using stdlib logging get JSON with global fields (AC2.3)

### Append mode (no clobber on restart)
**File:** tests/unit/test_structured_logging.py::TestAppendMode::test_second_setup_appends_not_clobbers
1. Set up logging, emit one message, flush
2. Count lines
3. Reset, set up again, emit second message
4. Assert line count increased (not reset)

**Verifies:** Restarting logging appends to existing file (AC6.4)

### INFO inside except has no traceback
**File:** tests/unit/test_structured_logging.py::TestTracebackPolicy::test_info_inside_except_has_no_traceback
1. Set up logging
2. Inside a `try/except`, log at INFO with `exc_info=True`
3. Parse JSON, assert no traceback/exc_info fields

**Verifies:** DEBUG/INFO suppress tracebacks even when exc_info passed (AC7.1)

### ERROR inside except has traceback
**File:** tests/unit/test_structured_logging.py::TestTracebackPolicy::test_error_inside_except_has_traceback
1. Set up logging
2. Inside a `try/except`, log at ERROR with `exc_info=True`
3. Parse JSON, assert traceback present

**Verifies:** WARNING+ include tracebacks (AC7.2)

### Null context fields when unbound (stdlib and structlog)
**File:** tests/unit/test_structured_logging.py::TestNullContextFields
1. Set up logging, emit without binding context
2. Parse JSON
3. Assert user_id, workspace_id, request_path are all null

**Verifies:** Context fields default to null when not bound (AC7.3)

### Context propagation -- authenticated, unauthenticated, workspace, isolation
**File:** tests/unit/test_structured_logging.py::TestContextPropagation
1. Bind user_id and request_path via contextvars, emit, assert they appear in JSON
2. Emit without binding, assert user_id and request_path are null
3. Bind workspace_id, emit, assert it appears
4. Bind workspace_id, clear, bind user_id only, emit, assert workspace_id is null

**Verifies:** structlog.contextvars propagation and isolation (AC1.1--AC1.4)

### Global fields present
**File:** tests/unit/test_structured_logging.py::TestGlobalFields::test_global_fields_present
1. Set up logging with branch="test-branch"
2. Emit, parse JSON
3. Assert pid, branch, commit, level, timestamp, event all present

**Verifies:** Every log line includes global correlation fields

## Structured Logging -- Discord Alerting (Unit)

### Empty webhook URL is no-op
**File:** tests/unit/test_logging_discord.py::TestNoOpWhenUnconfigured
1. Create DiscordAlertProcessor with empty webhook URL
2. Call with ERROR event
3. Assert event dict returned unchanged, no POST attempted

**Verifies:** Unconfigured webhook does not send (AC5.2)

### Non-error levels ignored
**File:** tests/unit/test_logging_discord.py::TestNonErrorLevelsIgnored
1. Create processor with valid URL
2. Call with INFO and DEBUG events
3. Assert no webhook fired for either

**Verifies:** Only ERROR and CRITICAL trigger Discord alerts

### ERROR fires webhook with correct embed
**File:** tests/unit/test_logging_discord.py::TestErrorTriggersWebhook
1. Call processor with ERROR event, mock _fire_and_forget
2. Assert called once with payload containing embed
3. Verify embed title has "[ERROR]" and event name
4. Verify colour is red (15548997), CRITICAL is dark red (10040115)
5. Verify context fields (user_id, workspace_id, logger, pid) in embed fields
6. Verify None-valued fields omitted from embed
7. Verify timestamp present in embed

**Verifies:** ERROR/CRITICAL events produce correctly formatted Discord embeds (AC5.1)

### Deduplication within window
**File:** tests/unit/test_logging_discord.py::TestDeduplication
1. Fire same error twice -- assert only one webhook
2. Fire same error with different logger -- assert two webhooks
3. Fire errors with different exc_info types -- assert two webhooks
4. Fire same error, sleep past dedup window, fire again -- assert two webhooks

**Verifies:** Same (exc_type, logger) deduplicated within 60s window (AC5.3)

### Webhook failure does not disrupt logging
**File:** tests/unit/test_logging_discord.py::TestWebhookFailureSafe
1. Mock httpx.AsyncClient.post to raise TimeoutException -- no exception propagated
2. Mock to raise ConnectError -- no exception propagated
3. Mock 429 response -- logged to stderr, no exception
4. Mock successful 204 -- post called once
5. Mock _fire_and_forget to raise RuntimeError -- processor swallows it

**Verifies:** Webhook failures never disrupt the logging pipeline (AC5.4)

### Discord embed truncation
**File:** tests/unit/test_logging_discord.py::TestTruncation
1. Event with 300-char event name -- title truncated to 256
2. Event with 5000-char exc_info -- description truncated to 4096
3. Event with 2000-char user_id -- field value truncated to 1024

**Verifies:** Discord embed limits respected

## Structured Logging -- Guard Tests (Unit)

### No print() calls in source
**File:** tests/unit/test_print_usage_guard.py::test_no_print_calls_in_source
1. Walk all .py files in src/promptgrimoire/ (excluding cli/)
2. AST-parse each file
3. Find any `print(...)` call nodes
4. Assert no violations found

**Verifies:** All output uses structlog, not print()

### No silent exception swallowing
**File:** tests/unit/test_exception_logging_guard.py::test_no_silent_exception_swallowing
1. Walk all .py files in src/promptgrimoire/ (excluding cli/, logging_discord.py)
2. AST-parse each file
3. For each ExceptHandler, check it: logs (logger.exception/error/warning/debug), re-raises, assigns to variable, or continues
4. Assert no violations found

**Verifies:** Every except block logs or re-raises (logging_discord.py excluded because structlog inside a structlog processor would recurse)

## Structured Logging -- Export Instrumentation (Unit)

### Export produces stage events with timing
**File:** tests/unit/export/test_export_instrumentation.py::TestExportStageTiming
1. Set up JSON logging, mock compile_latex
2. Run export_annotation_pdf with "<p>Hello world</p>"
3. Parse all JSON log lines, filter by export_stage
4. Assert pandoc_convert, tex_generate, latex_compile stages present
5. Assert one export_complete event
6. Assert each stage has export_id and stage_duration_ms (non-negative int)

**Verifies:** Export pipeline emits structured stage timing events (AC3.1)

### All stages share same export_id
**File:** tests/unit/export/test_export_instrumentation.py::TestExportStageTiming::test_all_stages_share_same_export_id
1. Run export, collect export_ids from all stage events
2. Assert exactly one unique export_id

**Verifies:** Correlation ID ties all stages together (AC3.2)

### LaTeX error extraction
**File:** tests/unit/export/test_export_instrumentation.py::TestLatexErrorExtraction
1. Create fake .tex and .log with "! Undefined control sequence" and "! Missing $ inserted"
2. Mock subprocess to fail (returncode=1)
3. Assert latex_errors field contains both !-prefixed lines
4. Repeat with no !-lines, assert latex_errors is empty list

**Verifies:** LaTeX !-prefixed error lines extracted into structured field (AC3.3)

### Font fallback logging
**File:** tests/unit/export/test_export_instrumentation.py::TestFontFallbackLogging
1. Run export with Latin-only content, assert font_fallbacks is a list
2. Run export with CJK content, assert font_fallbacks is non-empty list

**Verifies:** Successful export logs detect_scripts() result (AC3.4)

### Subprocess output capture
**File:** tests/unit/export/test_export_instrumentation.py::TestSubprocessOutputCapture
1. Mock compile failure with known stdout/stderr
2. Assert latex_stdout and latex_stderr fields present in log
3. Assert return_code field present
4. Mock 10KB stdout, assert truncated to 4096 chars

**Verifies:** Failed LaTeX subprocess output captured in structured log

## Database Engine (Unit)

### Session logs on exception
**File:** tests/unit/test_db_engine.py::TestGetSession::test_session_logs_on_exception
1. Replace session factory with mock that raises ValueError on commit
2. Enter get_session() context
3. Assert "rolling back" and "database session error" in captured output
4. Assert rollback was called

**Verifies:** Database session errors are logged before re-raising

### Session lazy-initializes when factory is None
**File:** tests/unit/test_db_engine.py::TestGetSession::test_session_lazy_initializes_when_factory_is_none
1. Set _state.session_factory and _state.engine to None
2. Enter get_session() with mocked settings providing a DB URL
3. Assert engine and session_factory are now non-None
4. Assert session is usable

**Verifies:** Lazy engine initialization on first use

### get_engine returns None before init, engine after init
**File:** tests/unit/test_db_engine.py::TestGetEngine
1. Set _state.engine to None, assert get_engine() returns None
2. Set _state.engine to mock, assert get_engine() returns the mock

**Verifies:** Engine accessor reflects initialization state
