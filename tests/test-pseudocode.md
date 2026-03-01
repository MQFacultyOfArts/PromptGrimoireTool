# Test Pseudocode

Human-readable description of what each test does, organised by domain.
Maintained by project-claude-librarian at branch completion.

Overlapping tests and coverage gaps are documented intentionally --
they reveal where the test suite is redundant or incomplete.

> **Scope:** This file covers tests added or modified on the
> 134-lua-highlight, 94-hierarchy-placement, 103-copy-protection,
> css-highlight-api, 165-auto-create-branch-db, 96-workspace-acl,
> 95-annotation-tags, workspace-navigator-196,
> user-docs-rodney-showboat-207, and
> platform-handlers-openrouter-chatcraft-209 branches.
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
1. get_expected_tables() now returns 12 tables including permission, course_role, acl_entry, tag_group, tag

**Verifies:** Schema verification function knows about all tables including tag tables

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

**Verifies:** websearch_to_tsquery gracefully handles malformed input

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

### Server and Rodney stop on script failure
**File:** tests/unit/test_make_docs.py::TestMakeDocsCleanup::test_make_docs_stops_server_on_script_failure
1. Patch all external dependencies; make bash subprocess.run calls return exit code 1
2. Call make_docs(), expect SystemExit
3. Assert _stop_e2e_server was still called with the server process
4. Assert "rodney stop --local" was called in the finally block

**Verifies:** AC1.2 -- cleanup runs even when a capture script fails

### Rodney start/stop lifecycle order
**File:** tests/unit/test_make_docs.py::TestMakeDocsRodneyLifecycle::test_make_docs_rodney_start_stop_lifecycle
1. Patch all external dependencies for happy path
2. Call make_docs()
3. Extract command summaries from all subprocess.run calls
4. Assert "rodney start" precedes all "bash" (script) calls
5. Assert "rodney stop" follows all "bash" (script) calls

**Verifies:** Rodney browser is started before scripts run and stopped after they complete

### Missing rodney causes early exit
**File:** tests/unit/test_make_docs.py::TestMakeDocsDependencyChecks::test_make_docs_exits_if_rodney_missing
1. Patch shutil.which to return None for "rodney"
2. Call make_docs(), expect SystemExit with code 1
3. Assert output mentions "rodney"
4. Assert _start_e2e_server was never called

**Verifies:** AC1.4 -- missing rodney binary is detected before starting the server

### Missing showboat causes early exit
**File:** tests/unit/test_make_docs.py::TestMakeDocsDependencyChecks::test_make_docs_exits_if_showboat_missing
1. Patch shutil.which to return None for "showboat"
2. Call make_docs(), expect SystemExit with code 1
3. Assert output mentions "showboat"
4. Assert _start_e2e_server was never called

**Verifies:** AC1.5 -- missing showboat binary is detected before starting the server

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
