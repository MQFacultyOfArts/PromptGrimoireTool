# Word Count with Configurable Limits Design

**GitHub Issue:** #47

## Summary

This feature adds configurable word count limits to activity workspaces in PromptGrimoire. Instructors set a minimum, a maximum, or both on a per-activity basis through the existing activity settings dialog, with an enforcement mode (soft or hard) that can be configured at the course level and overridden per activity. Students see a live word count badge in the annotation header that updates as they type; the badge changes colour as they approach or exceed the limit. At export time, soft enforcement shows a warning dialog and stamps a red violation notice on the first page of the exported PDF, while hard enforcement blocks export entirely until the student brings their response within limits.

The implementation builds strictly on existing infrastructure. Word counting runs server-side in Python, triggered by the same Yjs synchronisation hook that already extracts markdown on every editor update. Multilingual support handles English (whitespace tokenisation), Chinese (jieba), Japanese (MeCab), and Korean (uniseg) through per-segment script detection, with normalisation rules that prevent gaming via zero-width characters, hyphen concatenation, or markdown URL padding. The enforcement mode uses the project's established tri-state inheritance pattern -- the same mechanism that governs copy protection and sharing permissions -- so course-level defaults compose naturally with per-activity overrides.

## Definition of Done

1. **Word count badge in the header bar** (always visible, all tabs) when a word limit or minimum is configured on the activity
2. **Word count algorithm handles multilingual text** -- English, Chinese (jieba), Japanese (MeCab), and Korean (uniseg, space-delimited) with per-segment script detection
3. **Anti-gaming normalisation** -- hyphens always split words, zero-width characters stripped, NFKC normalised, markdown link/image URLs excluded
4. **Activity model has `word_minimum` and `word_limit`** (int | None) fields; `word_limit_enforcement` follows tri-state pattern (Course default + Activity override)
5. **Soft enforcement** -- export proceeds with warning dialog and red snitch badge on PDF
6. **Hard enforcement** -- export blocked with explanatory dialog
7. **Only export is affected** -- no other interactions blocked by word count status

**Out of scope:** Language-specific configuration per activity, CJK dictionary customisation, word count on general notes or highlight comments.

## Acceptance Criteria

### word-count-limits-47.AC1: Word count computation
- **AC1.1 Success:** English text "well-known fact" returns 3 words (hyphens split)
- **AC1.2 Success:** Chinese text segmented by jieba -- "这是中文维基百科首页的示例内容" returns 7 words
- **AC1.3 Success:** Japanese text segmented by MeCab -- "日本国憲法は最高法規である" returns 8 words
- **AC1.4 Success:** Korean text segmented by uniseg (space-delimited) -- "대한민국 헌법은 최고의 법률입니다" returns 4 words
- **AC1.5 Success:** Mixed-script text segments correctly -- each language segment uses appropriate tokeniser
- **AC1.6 Success:** Markdown link URLs excluded -- `[text](https://example.com)` counts 1 word ("text")
- **AC1.7 Anti-gaming:** "write-like-this-to-game" returns 5 words (hyphens split)
- **AC1.8 Anti-gaming:** Zero-width characters stripped -- "hello\u200Bworld" returns 1 word
- **AC1.9 Anti-gaming:** NFKC normalisation applied before counting
- **AC1.10 Edge:** Empty string returns 0
- **AC1.11 Edge:** Numbers-only text ("42") returns 0

### word-count-limits-47.AC2: Data model and settings
- **AC2.1 Success:** Activity `word_minimum` and `word_limit` accept positive integers or None
- **AC2.2 Success:** Activity `word_limit_enforcement` is tri-state (None = inherit from course)
- **AC2.3 Success:** Course `default_word_limit_enforcement` defaults to False (soft)
- **AC2.4 Success:** PlacementContext resolves enforcement via existing `resolve_tristate()` pattern
- **AC2.5 Failure:** Setting `word_minimum >= word_limit` (when both set) is rejected with validation error
- **AC2.6 Edge:** Activity with no limits set -- no word count behaviour activated

### word-count-limits-47.AC3: Activity settings UI
- **AC3.1 Success:** Instructor can set word minimum via number input in activity settings dialog
- **AC3.2 Success:** Instructor can set word limit via number input in activity settings dialog
- **AC3.3 Success:** Word limit enforcement appears as tri-state select (Inherit / Hard / Soft)
- **AC3.4 Success:** Course defaults page has toggle for default word limit enforcement
- **AC3.5 Success:** Values persist across page reloads

### word-count-limits-47.AC4: Header badge display
- **AC4.1 Success:** Badge visible in header bar on all tabs when limits configured
- **AC4.2 Success:** Badge hidden when no limits configured on the activity
- **AC4.3 Success:** Badge shows neutral style: "Words: 1,234 / 1,500"
- **AC4.4 Success:** Badge shows amber at 90%+ of max: "Words: 1,380 / 1,500 (approaching limit)"
- **AC4.5 Success:** Badge shows red at 100%+ of max: "Words: 1,567 / 1,500 (over limit)"
- **AC4.6 Success:** Badge shows red below minimum: "Words: 234 / 500 minimum (below minimum)"
- **AC4.7 Success:** Badge updates live as student types (after Yjs sync)
- **AC4.8 Edge:** Min-only activity shows "Words: 612 / 500 minimum" in neutral when met

### word-count-limits-47.AC5: Export enforcement (soft mode)
- **AC5.1 Success:** Export shows warning dialog: "Your response is X words over/under the limit"
- **AC5.2 Success:** User can confirm and proceed with export
- **AC5.3 Success:** PDF page 1 shows red badge: "Word Count: 1,567 / 1,500 (Exceeded)"
- **AC5.4 Success:** PDF shows neutral word count line when within limits
- **AC5.5 Edge:** Both min and max violated -- dialog shows both violations

### word-count-limits-47.AC6: Export enforcement (hard mode)
- **AC6.1 Success:** Export blocked with dialog explaining violation
- **AC6.2 Success:** Dialog has no export button -- only dismiss
- **AC6.3 Edge:** Within limits -- export proceeds normally with no dialog

### word-count-limits-47.AC7: Non-blocking behaviour
- **AC7.1 Success:** Word count status does not prevent saving
- **AC7.2 Success:** Word count status does not prevent editing
- **AC7.3 Success:** Word count status does not prevent sharing
- **AC7.4 Success:** Only export is affected by enforcement mode

## Glossary

- **Activity**: A unit of student work within a course week -- the primary container for a student's response draft and annotations. Activities are configured by instructors and may carry constraints such as word limits.
- **Alembic**: The database schema migration tool used in this project. All schema changes (new columns, tables) must go through Alembic migrations rather than being applied directly.
- **CRDT (Conflict-free Replicated Data Type)**: A data structure designed for real-time collaborative editing. In this project, pycrdt stores the canonical document content and enables multiple users to edit simultaneously without conflicts.
- **jieba**: A Chinese-language tokeniser library for Python. Because Chinese text has no spaces between words, segmentation requires a dictionary-based approach.
- **MeCab**: A Japanese morphological analyser. Like jieba for Chinese, MeCab segments Japanese text into meaningful units (words/morphemes) that whitespace splitting cannot handle.
- **Milkdown**: The rich-text markdown editor embedded in the Respond tab. Students type their responses here; the editor emits Yjs updates on every change.
- **NFKC normalisation**: A Unicode normalisation form that maps compatibility variants of characters (e.g. full-width digits, ligatures) to their canonical equivalents. Applied before word counting to prevent students from inflating counts using visually similar but technically distinct characters.
- **NiceGUI**: The Python web UI framework this project uses. Its server-push mechanism allows the server to update UI elements (such as the word count badge) on connected clients without a page reload.
- **PlacementContext**: A dataclass in `db/workspaces.py` that carries all resolved per-workspace settings (copy protection, sharing, word limits, etc.) to the annotation page. Settings that involve tri-state inheritance are resolved here before being passed to page components.
- **Respond tab**: Tab 3 of the annotation page where students compose their responses. Word count computation hooks into this tab's Yjs event handler.
- **snitch badge**: A project-internal term for a red violation marker injected into an exported PDF (using LaTeX's `\fcolorbox`) when a student's submission falls outside word limits. Visible to both student and instructor.
- **tri-state pattern**: A configuration inheritance model used throughout the project where a setting can be explicitly `True`, explicitly `False`, or `None` (meaning "inherit from the course-level default"). `word_limit_enforcement` follows this same pattern.
- **uniseg**: A Unicode segmentation library used here for Korean text, which is space-delimited at the word boundary level and does not require a dictionary tokeniser.
- **Yjs**: A CRDT framework implemented in JavaScript. The annotation page's editor emits Yjs update events on every keystroke; the server-side Python handler (`_setup_yjs_event_handler`) processes these updates to keep the server's copy of the document in sync.
- **zero-width characters**: Unicode code points that render with no visible width (e.g. U+200B, zero-width space). Stripping them before word counting prevents students from splitting or joining words artificially to manipulate the count.

## Architecture

Word count computation runs server-side in Python, triggered after the existing `_sync_markdown_to_crdt()` call in the Respond tab's Yjs event handler. A single `word_count()` function normalises the response draft markdown, segments it by script (Latin, Chinese, Japanese), dispatches each segment to the appropriate tokeniser (uniseg, jieba, or MeCab), and returns a total. The count is pushed to a header badge via NiceGUI's server-push mechanism.

Three new fields on the Activity model (`word_minimum`, `word_limit`, `word_limit_enforcement`) and one on Course (`default_word_limit_enforcement`) control behaviour. The enforcement mode follows the existing tri-state pattern: Activity value wins if set, otherwise Course default applies, resolved through the existing `resolve_tristate()` in `db/workspaces.py:199-206`. The full resolution chain: Activity `word_limit_enforcement` (True/False) → Course `default_word_limit_enforcement` (False = soft). When neither has been explicitly configured, enforcement defaults to soft. Word count features only activate when `word_minimum` or `word_limit` is set on the Activity; enforcement mode is irrelevant when no limits exist.

At export time, the word count is recomputed from the response draft markdown. Soft enforcement shows a warning dialog and injects a red LaTeX badge on page 1 of the PDF. Hard enforcement blocks export entirely with an explanatory dialog. No other user interactions are affected.

### Data Flow

```
User types in Milkdown (Tab 3)
  |
  v
Yjs update fires -> _setup_yjs_event_handler (respond.py:350-396)
  |
  v
_sync_markdown_to_crdt (respond.py:304-347) -> CRDT response_draft_markdown updated
  |
  v
word_count(markdown) -> normalise, segment by script, tokenise, count
  |
  v
NiceGUI server-push -> header badge updates ("Words: 1,234 / 1,500")
```

```
Export button clicked (header.py:182-196)
  |
  v
Recompute word_count() from response draft
  |
  v
Check limits from PlacementContext
  |                          |
  v                          v
Soft mode:                 Hard mode:
Warning dialog             Blocking dialog
  |                          |
  v                          x (stop)
Export PDF with
snitch badge on page 1
```

## Existing Patterns

**Tri-state settings:** Activity fields `copy_protection`, `allow_sharing`, `anonymous_sharing`, `allow_tag_creation` (models.py:284-299) inherit from Course defaults (models.py:143-163) via `resolve_tristate()` (workspaces.py:199-206). `word_limit_enforcement` follows this pattern exactly.

**PlacementContext:** The `PlacementContext` dataclass (workspaces.py:107-158) carries resolved settings to the annotation page. New fields `word_minimum`, `word_limit`, `word_limit_enforcement` are added here.

**Header badges:** `save_status` and `user_count_badge` (header.py:166-177) are `ui.label` elements on `PageState` updated via server-push. The word count badge follows this pattern.

**Activity settings UI:** `_ACTIVITY_TRI_STATE_FIELDS` (courses.py:125-139) is a declarative list of tri-state settings rendered as selects in `open_activity_settings()`. The enforcement mode is added here. The numeric word limit/minimum fields require a new input pattern (number fields rather than tri-state selects).

**Markdown sync:** `_sync_markdown_to_crdt()` (respond.py:304-347) fires on every Yjs update and extracts markdown via `window._getMilkdownMarkdown()`. Word count hooks in after this call at respond.py:387.

**No divergence from existing patterns.** This design extends established infrastructure without introducing new architectural concepts.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Word Count Function and Dependencies

**Goal:** Pure word count function with multilingual support, fully tested in isolation.

**Components:**
- `src/promptgrimoire/word_count.py` -- normalise_text(), dominant_script(), segment_by_script(), word_count() functions
- Dependencies: `uniseg`, `jieba`, `mecab-python3`, `unidic-lite` added to pyproject.toml

**Dependencies:** None (first phase)

**Done when:** `word_count()` returns correct counts for English, Chinese, Japanese, Korean, mixed-script, anti-gaming inputs, and markdown with links/images. All tests pass.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Data Model and Migration

**Goal:** Activity and Course models support word limit configuration, resolved through PlacementContext.

**Components:**
- Activity model in `src/promptgrimoire/db/models.py` -- add `word_minimum: int | None`, `word_limit: int | None`, `word_limit_enforcement: bool | None`
- Course model in `src/promptgrimoire/db/models.py` -- add `default_word_limit_enforcement: bool` (default False = soft)
- `PlacementContext` in `src/promptgrimoire/db/workspaces.py` -- add `word_minimum`, `word_limit`, `word_limit_enforcement` fields with resolution via `resolve_tristate()`
- Alembic migration adding four columns

**Dependencies:** Phase 1 (word_count function exists)

**Done when:** Migration applies cleanly, PlacementContext resolves tri-state enforcement correctly, model fields persist and round-trip through the database. Tests pass.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Activity Settings UI

**Goal:** Instructors can configure word limits per activity and course-level enforcement default.

**Components:**
- Activity settings dialog in `src/promptgrimoire/pages/courses.py` -- add word_minimum and word_limit number inputs, add word_limit_enforcement to `_ACTIVITY_TRI_STATE_FIELDS`
- Course defaults in `src/promptgrimoire/pages/courses.py` -- add `default_word_limit_enforcement` toggle to `_COURSE_DEFAULT_FIELDS`

**Dependencies:** Phase 2 (model fields exist)

**Done when:** Instructors can set word minimum, word limit, and enforcement mode through the UI. Values persist across page reloads. Tri-state inheritance from course default works correctly.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Header Badge Integration

**Goal:** Word count badge appears in the annotation header and updates live as students type.

**Components:**
- `PageState` in `src/promptgrimoire/pages/annotation/__init__.py` -- add `word_count_badge: ui.label | None` field
- Header rendering in `src/promptgrimoire/pages/annotation/header.py` -- mount badge near existing status badges, conditionally (only when limits configured)
- Respond tab in `src/promptgrimoire/pages/annotation/respond.py` -- call `word_count()` after `_sync_markdown_to_crdt()` at line 387, push result to header badge
- PlacementContext wiring -- pass word limit values from workspace context to the badge renderer

**Dependencies:** Phase 1 (word_count function), Phase 2 (PlacementContext carries limits)

**Done when:** Badge displays word count with correct formatting (neutral, amber at 90%, red at 100%+, under-minimum in red). Badge updates on every editor sync. Badge hidden when no limits configured.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Export Enforcement

**Goal:** Export respects word limit enforcement mode -- soft shows warning + snitch badge, hard blocks export.

**Components:**
- Export handler in `src/promptgrimoire/pages/annotation/pdf_export.py` -- pre-export word count check, warning/blocking dialog
- PDF template in `src/promptgrimoire/export/pdf_export.py` -- LaTeX snitch badge (`\fcolorbox`) injected before response content when count violates limits
- PlacementContext wiring -- enforcement mode available at export time

**Dependencies:** Phase 1 (word_count function), Phase 2 (PlacementContext), Phase 4 (badge wiring pattern)

**Done when:** Soft mode: export proceeds after warning, PDF shows red badge with count vs limit. Hard mode: export blocked, dialog explains violation. No badge when within limits. Tests verify both paths.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: E2E Tests

**Goal:** End-to-end verification of the full word count workflow.

**Components:**
- E2E tests in `tests/e2e/` -- activity settings configuration, word count badge display and live update, export with soft/hard enforcement

**Dependencies:** Phases 1-5 (all functionality implemented)

**Done when:** E2E tests verify: setting word limits via activity settings, badge appears and updates as user types, soft export shows warning and badge on PDF, hard export blocks with dialog. All tests use `data-testid` attributes per project convention.
<!-- END_PHASE_6 -->

## Additional Considerations

**MeCab system dependency:** `mecab-python3` requires the MeCab binary and `libmecab-dev` headers installed at the system level. `unidic-lite` bundles a ~900MB dictionary. Deployment (grimoire.drbbs.org) must install `mecab` and `libmecab-dev` via apt. If MeCab is not installed, `word_count()` must raise `ImportError` at startup (not silently degrade) so the failure is obvious. Phase 1 includes a startup check that logs a clear error if MeCab is unavailable.

**jieba Python 3.14 compatibility:** jieba emits `SyntaxWarning` for invalid escape sequences on Python 3.14. Suppress with a `warnings.filterwarnings` call scoped to the jieba import.

**Synchronous word count in sync callback:** `word_count()` runs synchronously after `_sync_markdown_to_crdt()` completes, inside the Yjs event handler. For typical student responses (a few hundred to a few thousand words), latency is negligible. If performance becomes an issue with very long mixed-script documents (5,000+ words), debounce the badge update independently from the markdown sync or offload to a background task -- but do not implement this preemptively.

**Markdown URL stripping:** Two regexes strip URLs from raw markdown before counting: `re.sub(r'\]\([^)]*\)', ']', text)` removes link/image URLs, `re.sub(r'!\[', '[', text)` removes image markers. Link text is preserved and counts toward the total. Reference-style links (`[text][ref]` with `[ref]: url` elsewhere) are not explicitly handled; the ref label would count as a word. This is acceptable -- reference-style links are uncommon in Milkdown output, and the ref label is typically one word.

**CJK ambiguous kanji:** Leading CJK ideographs without nearby hiragana/katakana default to Chinese segmentation (jieba) rather than Japanese (MeCab). The word count difference is ~1 word per ambiguous segment. Acceptable for word limit enforcement.
