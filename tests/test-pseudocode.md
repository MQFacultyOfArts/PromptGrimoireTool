# Test Pseudocode

Human-readable description of what each test does, organised by domain.
Maintained by project-claude-librarian at branch completion.

Overlapping tests and coverage gaps are documented intentionally --
they reveal where the test suite is redundant or incomplete.

> **Scope:** This file covers tests added or modified on the
> 134-lua-highlight, 94-hierarchy-placement, and 103-copy-protection
> branches. Existing tests from before these branches are not yet
> documented here.

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

### Copy protection JS content (AC4.1-AC4.6)
**File:** tests/unit/test_copy_protection_js.py::TestCopyProtectionJsContent
1. JS targets #doc-container selector
2. JS targets organise-columns test ID
3. JS targets respond-reference-panel test ID
4. JS registers copy event listener
5. JS registers cut event listener
6. JS registers contextmenu event listener
7. JS registers dragstart event listener
8. JS targets milkdown-respond-editor for paste
9. JS uses Quasar.Notify.create for toast
10. JS uses "copy-protection" group key for toast debounce
11. JS calls stopImmediatePropagation on paste (blocks ProseMirror)
12. JS registers keydown listener checking e.key === 'p' (Ctrl+P intercept)

**Verifies:** JS block contains all required event interception, correct selectors, Quasar toast notification, and print shortcut intercept

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
