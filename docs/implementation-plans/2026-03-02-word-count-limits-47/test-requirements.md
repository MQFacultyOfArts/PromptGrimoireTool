# Test Requirements: Word Count with Configurable Limits (#47)

Maps every acceptance criterion from the design plan to specific automated tests or documented human verification. Rationalised against implementation decisions in phases 1-6.

---

## Automated Test Mapping

### word-count-limits-47.AC1: Word count computation

| Criterion | Test type | Test file | Phase | Test description |
|---|---|---|---|---|
| **AC1.1** English text "well-known fact" returns 3 words (hyphens split) | unit | `tests/unit/test_word_count.py::TestWordCount` | 1 (task 6) | Parametrised case: `word_count("well-known fact") == 3`. Hyphens split into sub-tokens, each containing alpha chars. |
| **AC1.2** Chinese text segmented by jieba returns 7 words | unit | `tests/unit/test_word_count.py::TestWordCount` | 1 (task 6) | Parametrised case: `6 <= word_count("...") <= 8`. Uses +/-1 tolerance because jieba dictionary versions produce variable segmentation. Exact count in AC is illustrative magnitude, not a precise requirement. |
| **AC1.3** Japanese text segmented by MeCab returns 8 words | unit | `tests/unit/test_word_count.py::TestWordCount` | 1 (task 6) | Parametrised case: `7 <= word_count("...") <= 9`. Same +/-1 tolerance rationale as AC1.2 -- MeCab/unidic-lite dictionary variability. |
| **AC1.4** Korean text segmented by uniseg (space-delimited) returns 4 words | unit | `tests/unit/test_word_count.py::TestWordCount` | 1 (task 6) | Parametrised case: `word_count("...") == 4`. Exact match -- Korean is space-delimited via uniseg UAX #29, no dictionary variability. |
| **AC1.5** Mixed-script text segments correctly | unit | `tests/unit/test_word_count.py::TestSegmentByScript` and `TestWordCount` | 1 (tasks 4-5, 7) | `segment_by_script()` tests verify correct script classification per segment. Integration tests in task 7 verify `word_count()` produces reasonable totals for mixed English+CJK input. Kanji adjacent to hiragana classified as `"ja"` not `"zh"`. |
| **AC1.6** Markdown link URLs excluded | unit | `tests/unit/test_word_count.py::TestNormaliseText` and `TestWordCount` | 1 (tasks 2-3, 7) | `normalise_text()` tests verify `[text](url)` becomes `[text]`. `word_count("[click here](https://example.com/long/path)") == 2` verifies end-to-end. Image markers `![alt](url)` also stripped. |
| **AC1.7** "write-like-this-to-game" returns 5 words (hyphens split) | unit | `tests/unit/test_word_count.py::TestWordCount` | 1 (task 6) | Parametrised case: `word_count("write-like-this-to-game") == 5`. Verifies anti-gaming hyphen splitting. |
| **AC1.8** Zero-width characters stripped | unit | `tests/unit/test_word_count.py::TestNormaliseText` and `TestWordCount` | 1 (tasks 2-3, 7) | `normalise_text("hello\u200bworld") == "helloworld"` verifies stripping. `word_count("hello\u200bworld") == 1` verifies end-to-end -- zero-width space removed, single word remains. |
| **AC1.9** NFKC normalisation applied before counting | unit | `tests/unit/test_word_count.py::TestNormaliseText` and `TestWordCount` | 1 (tasks 2, 7) | `normalise_text()` tests verify full-width chars normalised. `word_count("\uff28\uff45\uff4c\uff4c\uff4f \uff37\uff4f\uff52\uff4c\uff44") == 2` verifies end-to-end. |
| **AC1.10** Empty string returns 0 | unit | `tests/unit/test_word_count.py::TestWordCount` | 1 (task 6) | Parametrised case: `word_count("") == 0`. |
| **AC1.11** Numbers-only text ("42") returns 0 | unit | `tests/unit/test_word_count.py::TestWordCount` | 1 (task 6) | Parametrised case: `word_count("42") == 0`. Filter step requires at least one alpha character per sub-token. |

---

### word-count-limits-47.AC2: Data model and settings

| Criterion | Test type | Test file | Phase | Test description |
|---|---|---|---|---|
| **AC2.1** Activity `word_minimum` and `word_limit` accept positive integers or None | unit | `tests/unit/test_word_count_models.py::TestActivityWordCountFields` | 2 (tasks 1, 6) | Model instantiation tests: `Activity(word_minimum=500, word_limit=1000)` succeeds. Integration tests in task 6: round-trip via `update_activity()` and read-back. |
| **AC2.2** Activity `word_limit_enforcement` is tri-state (None = inherit from course) | unit | `tests/unit/test_word_count_models.py::TestActivityWordCountFields` | 2 (task 1) | `Activity(word_limit_enforcement=True)`, `Activity(word_limit_enforcement=False)`, `Activity(word_limit_enforcement=None)` all succeed. |
| **AC2.3** Course `default_word_limit_enforcement` defaults to False (soft) | unit | `tests/unit/test_word_count_models.py` | 2 (task 1) | `Course()` instantiation verifies `default_word_limit_enforcement == False`. |
| **AC2.4** PlacementContext resolves enforcement via existing `resolve_tristate()` pattern | integration | `tests/integration/test_word_count_placement.py` | 2 (tasks 3-4) | Three resolution scenarios tested: activity override True -> hard; activity None + course False -> soft; activity False + course True -> activity wins (soft). Also tests course-placed and loose workspaces. |
| **AC2.5** Setting `word_minimum >= word_limit` (when both set) is rejected with validation error | unit | `tests/unit/test_word_count_models.py` | 2 (task 5) | `update_activity()` with `word_minimum=500, word_limit=200` raises `ValueError`. Equal values (`word_minimum=500, word_limit=500`) also rejected. One-sided (either None) succeeds. |
| **AC2.6** Activity with no limits set -- no word count behaviour activated | unit + integration | `tests/unit/test_word_count_models.py` + `tests/integration/test_word_count_placement.py` | 2 (tasks 1, 4) | Model defaults all None. PlacementContext resolves `word_minimum=None, word_limit=None` when Activity has no limits. |

---

### word-count-limits-47.AC3: Activity settings UI

| Criterion | Test type | Test file | Phase | Test description |
|---|---|---|---|---|
| **AC3.1** Instructor can set word minimum via number input in activity settings dialog | e2e | `tests/e2e/test_word_count.py::TestWordCountSettings` | 6 (task 2) | Fill `data-testid="activity-word-minimum-input"` with "200", save, verify persisted. |
| **AC3.2** Instructor can set word limit via number input in activity settings dialog | e2e | `tests/e2e/test_word_count.py::TestWordCountSettings` | 6 (task 2) | Fill `data-testid="activity-word-limit-input"` with "500", save, verify persisted. |
| **AC3.3** Word limit enforcement appears as tri-state select (Inherit / Hard / Soft) | e2e | `tests/e2e/test_word_count.py::TestWordCountSettings` | 6 (task 2) | Click `data-testid="activity-word_limit_enforcement-select"`, select Hard via `data-testid="activity-word_limit_enforcement-opt-on"`. Tri-state select options have testids via `_add_option_testids()` pattern (Phase 3 task 4). |
| **AC3.4** Course defaults page has toggle for default word limit enforcement | e2e | `tests/e2e/test_word_count.py::TestWordCountSettings` | 6 (task 2) | Open course settings, verify `data-testid="course-default_word_limit_enforcement-switch"` is visible. Toggle on, save, reload, verify persisted. |
| **AC3.5** Values persist across page reloads | e2e | `tests/e2e/test_word_count.py::TestWordCountSettings` | 6 (task 2) | Set values, save, reload page, reopen settings dialog, verify all values match what was saved. |

---

### word-count-limits-47.AC4: Header badge display

| Criterion | Test type | Test file | Phase | Test description |
|---|---|---|---|---|
| **AC4.1** Badge visible in header bar on all tabs when limits configured | e2e | `tests/e2e/test_word_count.py::TestWordCountBadge` | 6 (tasks 3-4) | Navigate to workspace with limits, verify `data-testid="word-count-badge"` visible. Switch to Annotate tab, verify still visible. Test with min-only and limit-only configurations. |
| **AC4.2** Badge hidden when no limits configured on the activity | e2e | `tests/e2e/test_word_count.py::TestWordCountBadge` | 6 (task 3) | Navigate to workspace without limits, verify `data-testid="word-count-badge"` not visible. |
| **AC4.3** Badge shows neutral style: "Words: 1,234 / 1,500" | unit | `tests/unit/test_word_count_badge.py` | 4 (tasks 3, 5) | `format_word_count_badge(1234, None, 1500)` returns text="Words: 1,234 / 1,500" with neutral CSS classes. Also tested with both min+max where count is within range. |
| **AC4.4** Badge shows amber at 90%+ of max | unit | `tests/unit/test_word_count_badge.py` | 4 (tasks 3-4) | `format_word_count_badge(1380, None, 1500)` returns text including "(approaching limit)" with amber CSS classes. Boundary cases: exactly 90% (1350/1500) is amber, just below (1349/1500) is neutral. |
| **AC4.5** Badge shows red at 100%+ of max | unit | `tests/unit/test_word_count_badge.py` | 4 (tasks 3-4) | `format_word_count_badge(1567, None, 1500)` returns text including "(over limit)" with red CSS classes. Boundary: exactly at limit (1500/1500) counts as over. |
| **AC4.6** Badge shows red below minimum | unit | `tests/unit/test_word_count_badge.py` | 4 (tasks 3, 5) | `format_word_count_badge(234, 500, None)` returns text including "(below minimum)" with red CSS classes. Also tested with both min+max where count is below minimum. |
| **AC4.7** Badge updates live as student types (after Yjs sync) | e2e | `tests/e2e/test_word_count.py::TestWordCountBadge` | 6 (task 3) | Type text in Milkdown editor, wait for Yjs sync, verify badge text updated to reflect new word count. |
| **AC4.8** Min-only activity shows "Words: 612 / 500 minimum" in neutral when met | unit | `tests/unit/test_word_count_badge.py` | 4 (task 3) | `format_word_count_badge(612, 500, None)` returns text="Words: 612 / 500 minimum" with neutral CSS classes. |

---

### word-count-limits-47.AC5: Export enforcement (soft mode)

| Criterion | Test type | Test file | Phase | Test description |
|---|---|---|---|---|
| **AC5.1** Export shows warning dialog: "Your response is X words over/under the limit" | unit + e2e | `tests/unit/test_word_count_enforcement.py` + `tests/e2e/test_word_count.py::TestWordCountExport` | 5 (tasks 1-2), 6 (task 5) | Unit: `format_violation_message()` tested with over-limit and under-minimum violations, verifying exact message format. E2E: click export, verify warning dialog appears with `data-testid="wc-export-anyway-btn"`. |
| **AC5.2** User can confirm and proceed with export | e2e | `tests/e2e/test_word_count.py::TestWordCountExport` | 6 (task 5) | Click `data-testid="wc-export-anyway-btn"` in soft enforcement dialog, verify download completes. |
| **AC5.3** PDF page 1 shows red badge: "Word Count: 1,567 / 1,500 (Exceeded)" | unit + e2e | `tests/unit/test_word_count_enforcement.py` (LaTeX output) + `tests/e2e/test_word_count.py::TestWordCountExport` | 5 (task 5), 6 (task 5) | Unit: `_build_word_count_badge()` with over-limit returns red `\fcolorbox` LaTeX with "(Exceeded)". E2E: extract text from downloaded PDF, verify snitch badge text present. |
| **AC5.4** PDF shows neutral word count line when within limits | unit | `tests/unit/test_word_count_enforcement.py` | 5 (task 5) | `_build_word_count_badge()` with count within limits returns neutral `\textit{}` LaTeX line (no colour box). No limits returns empty string. |
| **AC5.5** Both min and max violated -- dialog shows both violations | unit | `tests/unit/test_word_count_enforcement.py` | 5 (task 2) | **Implementation decision:** "Both violated" is architecturally unreachable through validated data. The `word_minimum < word_limit` constraint (AC2.5) makes it impossible for `count >= word_limit` AND `count < word_minimum` simultaneously. The message formatting code path is tested by constructing a `WordCountViolation` directly with `over_limit=True, under_minimum=True` (bypassing `check_word_count_violation()`), verifying the message mentions both violations. E2E tests (Phase 6 task 5) cover each violation independently (over-limit and under-minimum in separate test methods). |

---

### word-count-limits-47.AC6: Export enforcement (hard mode)

| Criterion | Test type | Test file | Phase | Test description |
|---|---|---|---|---|
| **AC6.1** Export blocked with dialog explaining violation | e2e | `tests/e2e/test_word_count.py::TestWordCountExport` | 6 (task 6) | Create workspace with hard enforcement, type over limit, click export. Verify blocking dialog appears with violation text. |
| **AC6.2** Dialog has no export button -- only dismiss | e2e | `tests/e2e/test_word_count.py::TestWordCountExport` | 6 (task 6) | Verify `data-testid="wc-export-anyway-btn"` is NOT visible. Verify `data-testid="wc-dismiss-btn"` IS visible. Click dismiss, verify dialog closes and no download triggered. |
| **AC6.3** Within limits -- export proceeds normally with no dialog | unit + e2e | `tests/unit/test_word_count_enforcement.py` | 5 (task 3) | `check_word_count_violation()` with count within range returns `has_violation=False`. The export code path skips the dialog when `has_violation` is False. E2E coverage implicit in export tests for within-limit cases. |

---

### word-count-limits-47.AC7: Non-blocking behaviour

| Criterion | Test type | Test file | Phase | Test description |
|---|---|---|---|---|
| **AC7.1** Word count status does not prevent saving | unit | `tests/unit/test_word_count_enforcement.py` | 5 (task 3) | **Implementation decision:** Tested via module namespace assertions. `import promptgrimoire.crdt; assert not hasattr(promptgrimoire.crdt, 'WordCountViolation')` and `assert not hasattr(promptgrimoire.crdt, 'check_word_count_violation')`. If enforcement is ever imported into save paths, this test fails. |
| **AC7.2** Word count status does not prevent editing | unit | `tests/unit/test_word_count_enforcement.py` | 5 (task 3) | Module namespace assertion: `import promptgrimoire.pages.annotation.respond; assert not hasattr(promptgrimoire.pages.annotation.respond, 'WordCountViolation')`. The respond module imports `word_count` (for badge updates) but NOT `WordCountViolation` or `check_word_count_violation` (enforcement). |
| **AC7.3** Word count status does not prevent sharing | unit | `tests/unit/test_word_count_enforcement.py` | 5 (task 3) | Module namespace assertion: `import promptgrimoire.db.acl; assert not hasattr(promptgrimoire.db.acl, 'WordCountViolation')`. ACL/share code has no enforcement dependency. |
| **AC7.4** Only export is affected by enforcement mode | unit | `tests/unit/test_word_count_enforcement.py` | 5 (task 3) | Positive + negative control assertions. Positive: `import promptgrimoire.pages.annotation.pdf_export; assert hasattr(promptgrimoire.pages.annotation.pdf_export, 'check_word_count_violation')` (or equivalent import verification). Negative: the three assertions from AC7.1-AC7.3 above confirm no other module imports enforcement. Every test contains at least one `assert`. |

---

## Human Verification

### word-count-limits-47.AC4.3, AC4.4, AC4.5, AC4.6, AC4.8: Badge visual appearance

- **Criterion:** Badge CSS classes produce visually distinct neutral (grey), amber, and red styles.
- **Justification:** Unit tests verify correct CSS class strings are returned by `format_word_count_badge()`, but cannot verify that Tailwind/Quasar renders those classes into visually distinguishable colours. E2E tests verify badge text content and visibility but do not screenshot-compare colour rendering.
- **Verification approach:** During UAT, an instructor should navigate to a workspace with word limits configured and visually confirm:
  1. Neutral badge (within limits) appears with a grey/subtle background
  2. Amber badge (90-99% of limit) appears with a distinct amber/yellow warning colour
  3. Red badge (at or over limit, or below minimum) appears with a distinct red danger colour
  4. Text is legible against each background colour

### word-count-limits-47.AC4.7: Badge updates feel "live"

- **Criterion:** Badge updates live as student types (after Yjs sync).
- **Justification:** E2E tests verify the badge text changes after typing, but cannot assess whether the update latency feels responsive to a human user. The design notes that word_count() runs synchronously after Yjs sync and should be negligible for typical student responses, but latency perception is subjective.
- **Verification approach:** During UAT, a student should type continuously in the Respond tab and observe the badge updating. Confirm updates appear within ~1 second of pausing. Try with a document containing ~2,000 words of mixed-script text to stress-test.

### word-count-limits-47.AC5.3: PDF snitch badge visual rendering

- **Criterion:** PDF page 1 shows red badge: "Word Count: 1,567 / 1,500 (Exceeded)".
- **Justification:** Unit tests verify the LaTeX `\fcolorbox` output. E2E tests extract text from the PDF to verify content. Neither confirms the visual rendering (red box, legible text, correct positioning on page 1).
- **Verification approach:** During UAT, export a PDF from a workspace with a word count violation (soft enforcement). Open the PDF and visually confirm:
  1. Red-bordered box appears on page 1 before the response content
  2. Text reads "Word Count: X / Y (Exceeded)" with correct numbers
  3. Box does not overlap or obscure other content

### word-count-limits-47.AC3.1, AC3.2: Number input UX

- **Criterion:** Instructor can set word minimum/limit via number inputs.
- **Justification:** E2E tests verify fill-and-save round-trips. They do not verify that the inputs enforce `min=1` (no zero or negative values), handle non-numeric input gracefully, or clear correctly when the user deletes the value.
- **Verification approach:** During UAT, an instructor should:
  1. Attempt to enter 0, -1, and non-numeric text in the word minimum/limit fields -- verify the input rejects or ignores them
  2. Clear a previously-set value by deleting all text -- verify it saves as "no limit" (None)
  3. Verify the validation error notification appears when setting minimum >= limit

---

## Coverage Summary

| AC Group | Total criteria | Automated | Human-only | Notes |
|---|---|---|---|---|
| AC1: Word count computation | 11 | 11 | 0 | CJK counts use +/-1 tolerance (AC1.2, AC1.3) |
| AC2: Data model and settings | 6 | 6 | 0 | |
| AC3: Activity settings UI | 5 | 5 | 2 supplementary | E2E covers function; human verifies UX edge cases |
| AC4: Header badge display | 8 | 8 | 2 supplementary | Unit covers logic; human verifies visual rendering and perceived latency |
| AC5: Export enforcement (soft) | 5 | 5 | 1 supplementary | AC5.5 "both violated" tested via direct construction (architecturally unreachable through validated data) |
| AC6: Export enforcement (hard) | 3 | 3 | 0 | |
| AC7: Non-blocking behaviour | 4 | 4 | 0 | Tested via `hasattr` namespace assertions |
| **Total** | **42** | **42** | **5 supplementary** | All criteria have automated coverage; human verification supplements visual/UX aspects |

---

## Implementation Decision Cross-Reference

| Decision | Affected criteria | Test impact |
|---|---|---|
| CJK +/-1 tolerance (jieba/MeCab dictionary variability) | AC1.2, AC1.3 | Range assertions (`6 <= count <= 8`) instead of exact equality. AC exact counts are illustrative. |
| "Both violated" architecturally unreachable (AC2.5 enforces `word_minimum < word_limit`) | AC5.5 | Message formatting tested by constructing `WordCountViolation` directly. `check_word_count_violation()` cannot produce `over_limit=True AND under_minimum=True` with valid inputs. |
| AC7.1-7.4 via module namespace assertions | AC7.1, AC7.2, AC7.3, AC7.4 | `hasattr` checks on imported modules provide regression guard: if enforcement is ever imported into non-export paths, tests fail. |
| Tri-state select option testids via `_add_option_testids()` | AC3.3 | E2E tests locate select options by `data-testid` (e.g. `activity-word_limit_enforcement-opt-on`) instead of visible text. |
| `generate_tex_only()` backward compatibility | AC5.3, AC5.4 | Word count params are keyword-only with `None` defaults. Existing call sites unaffected. |
