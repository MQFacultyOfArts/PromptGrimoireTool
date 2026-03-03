# Roleplay Demo Polish — Test Requirements

**Design:** `docs/design-plans/2026-03-03-roleplay-demo-polish-36.md`
**Implementation plans:** `docs/implementation-plans/2026-03-03-roleplay-demo-polish-36/phase_01.md` through `phase_03.md`

---

## Traceability Matrix

Every acceptance criterion from the design is mapped below to either an automated test or a documented human verification, with justification for the choice.

### AC1: Visual assets display correctly

| Criterion | Test Type | Automated? | Location | Rationale |
|-----------|-----------|------------|----------|-----------|
| AC1.1 | Human | No | [HV-1](#hv-1-background-image-covers-viewport-ac11) | `background-size: cover` and `background-attachment: fixed` are CSS declarations applied to a page container class (`.roleplay-bg`). Verifying "no tiling or distortion" requires visual inspection of the rendered page at multiple viewport sizes. A unit test can confirm the CSS file contains the rule; an E2E test can confirm the class is applied to the DOM. But neither can verify the perceptual claim "no distortion" -- that requires a human eye. |
| AC1.2 | Unit | Yes | `tests/unit/test_roleplay_visual.py` | Phase 2, Tasks 1-2 (TDD red/green). Mocks `ui.chat_message` and asserts `avatar="/static/roleplay/user-default.png"` is passed when `sent=True`. Tests the parameter wiring, not the visual rendering -- the latter is covered by HV-2. |
| AC1.3 | Unit | Yes | `tests/unit/test_roleplay_visual.py` | Same test file. Asserts `avatar="/static/roleplay/becky-bennett.png"` is passed when `sent=False`. |

### AC2: ST-inspired dark theme renders correctly

| Criterion | Test Type | Automated? | Location | Rationale |
|-----------|-----------|------------|----------|-----------|
| AC2.1 | Human | No | [HV-2](#hv-2-dark-theme-visual-fidelity-ac21-ac22) | Semi-transparent tint with backdrop blur is a CSS visual effect. An E2E test could assert the `.roleplay-chat` class is present on the chat area element, but whether the tint is actually visible over the background image is a rendering question. No pixel-level assertions are planned. |
| AC2.2 | Human | No | [HV-2](#hv-2-dark-theme-visual-fidelity-ac21-ac22) | Ivory text, grey italics, and orange-bordered blockquotes are CSS rules in `roleplay.css`. Verifying the visual experience -- that these colours are readable, that they evoke SillyTavern's theme -- requires human inspection. A CSS linter could verify the file parses, but not that the aesthetics are correct. |
| AC2.3 | Human | No | [HV-3](#hv-3-upload-card-readability-ac23) | Edge case: the upload card (pre-session state) must remain readable against the dark background. This is a readability judgement that requires human verification with the actual background image. |

### AC3: Export creates annotatable workspace

| Criterion | Test Type | Automated? | Location | Rationale |
|-----------|-----------|------------|----------|-----------|
| AC3.1 | Integration | Yes | `tests/integration/test_roleplay_workspace_export.py` | Phase 3, Task 4. Creates a `Session` with known turns, converts to HTML via `session_to_html()`, calls `create_workspace()` + `add_document(type="ai_conversation")` + `grant_permission()`, then asserts: workspace exists, has exactly one document of type `ai_conversation`, document content contains all turn markers, ACL entry grants `"owner"` to the test user. Requires `TEST_DATABASE_URL`. |
| AC3.2 | Unit | Yes | `tests/unit/test_roleplay_export.py` | Phase 3, Tasks 2-3 (TDD red/green). Pure-function tests on `session_to_html()` (extracted to `roleplay_export.py` per justified design deviation for testability). Verifies: user turns produce `data-speaker="user"` + `data-speaker-name="{user_name}"`; AI turns produce `data-speaker="assistant"` + `data-speaker-name="{char_name}"`; markdown converts to HTML; marker divs are siblings (not parents) of content; empty session returns empty string; multiple turns alternate marker/content blocks correctly. |
| AC3.3 | Human | No | [HV-4](#hv-4-annotation-page-speaker-labels-ac33) | The annotation page renders speaker labels via CSS `::before` pseudo-elements keyed on `data-speaker` and `data-speaker-name` attributes (see `annotation/css.py` lines 157-222). The HTML structure is verified by AC3.2's unit tests and AC3.1's integration test. But whether the labels actually render visually in the annotation page UI depends on the annotation page's CSS being loaded, the document container having the `.doc-container` class, and NiceGUI's rendering pipeline. This is an end-to-end visual verification that crosses multiple subsystems. |
| AC3.4 | Unit | Yes | `tests/unit/test_roleplay_visual.py` | Phase 3, Task 5. Verifies the export button starts disabled when no session is active. Tests the initial state of the button's `disabled` property via mock or state-dict inspection. |

---

## Automated Tests

### Unit Tests

#### `tests/unit/test_roleplay_visual.py`

Created in Phase 2 Task 1 (TDD red), made green in Phase 2 Task 2. Extended in Phase 3 Task 5.

| Test | Criterion | What it verifies |
|------|-----------|-----------------|
| `test_user_message_passes_user_avatar` | AC1.2 | `_create_chat_message(sent=True)` passes `avatar="/static/roleplay/user-default.png"` to `ui.chat_message` |
| `test_ai_message_passes_ai_avatar` | AC1.3 | `_create_chat_message(sent=False)` passes `avatar="/static/roleplay/becky-bennett.png"` to `ui.chat_message` |
| `test_avatar_defaults_to_none` | AC1.2, AC1.3 | Backward compat: omitting avatar passes `avatar=None` |
| `test_export_button_disabled_without_session` | AC3.4 | Export button's initial state is disabled when no session is loaded |

**Approach:** Mock `ui.chat_message` and `ui.markdown` (NiceGUI components require a running client context). Follow the mock pattern from `tests/unit/test_auth_client.py`. For the export button test, inspect the state dict or mock the button creation to verify `disabled=True` at initialisation.

#### `tests/unit/test_roleplay_export.py`

Created in Phase 3 Task 2 (TDD red), made green in Phase 3 Task 3.

| Test | Criterion | What it verifies |
|------|-----------|-----------------|
| `test_user_turn_has_correct_speaker_attrs` | AC3.2 | Output contains `data-speaker="user"` and `data-speaker-name="{user_name}"` |
| `test_ai_turn_has_correct_speaker_attrs` | AC3.2 | Output contains `data-speaker="assistant"` and `data-speaker-name="{char_name}"` |
| `test_markdown_converts_to_html` | AC3.2 | `*italics*` becomes `<em>italics</em>`, etc. |
| `test_marker_divs_are_siblings_not_parents` | AC3.2 | Marker `<div data-speaker="..."></div>` is followed by content as a sibling, not wrapping it |
| `test_multiple_turns_alternate_correctly` | AC3.2 | Multi-turn session produces alternating marker+content blocks |
| `test_empty_session_returns_empty_string` | AC3.2 | `session_to_html(empty_session)` returns `""` |

**Approach:** Pure-function tests. Create `Session` and `Turn` objects from `promptgrimoire.models`, call `session_to_html()`, parse/inspect the returned HTML string. No mocks needed -- this is the payoff of extracting `session_to_html()` into `roleplay_export.py` (design deviation justified for testability in Phase 3 header).

### Integration Tests

#### `tests/integration/test_roleplay_workspace_export.py`

Created in Phase 3 Task 4.

| Test | Criterion | What it verifies |
|------|-----------|-----------------|
| `test_export_creates_workspace_with_ai_conversation_doc` | AC3.1 | Workspace is created as loose (no parent week/activity), has exactly one document of type `ai_conversation` |
| `test_exported_document_contains_speaker_markers` | AC3.1, AC3.2 | Document HTML content includes `data-speaker` and `data-speaker-name` attributes for all turns |
| `test_export_grants_owner_permission` | AC3.1 | ACL entry exists with `"owner"` permission for the exporting user |

**Approach:** Requires `TEST_DATABASE_URL` (skip guard at module level). Uses `db_session` fixture from `tests/integration/conftest.py`. Creates a `Session` with known turns, runs the full export pipeline (`session_to_html()` -> `create_workspace()` -> `add_document()` -> `grant_permission()`), then queries the database to verify results. Follows the workspace test pattern from `docs/testing.md`: no user creation needed for workspace operations, UUID isolation.

---

## Human Verification

### HV-1: Background image covers viewport (AC1.1)

**Why not automated:** The criterion specifies "no tiling or distortion", which is a visual-perceptual judgement. CSS `background-size: cover` and `background-attachment: fixed` should achieve this, but edge cases (aspect ratio mismatch, small viewports, high-DPI screens) require human inspection. Pixel-comparison snapshot testing was considered but rejected: the background image is a photograph where minor rendering differences across browsers are acceptable, and the maintenance cost of snapshot baselines outweighs the risk.

**Verification approach:**
1. Start the app: `uv run python -m promptgrimoire`
2. Navigate to `/roleplay`
3. Verify: office conference room background fills the viewport edge-to-edge
4. Resize the browser window to a narrow width (mobile-like) and verify: no tiling, image crops gracefully
5. Scroll the page (if scrollable) and verify: background stays fixed (does not scroll with content)

**Phase:** Phase 2 UAT step 3

---

### HV-2: Dark theme visual fidelity (AC2.1, AC2.2)

**Why not automated:** These criteria describe aesthetic outcomes: "semi-transparent dark tint", "ivory/warm white text", "grey italics", "orange left border on blockquotes". While an E2E test could assert CSS class presence, verifying the visual result -- that the tint is perceptible over the background, that text colours are readable, that the overall feel resembles SillyTavern -- is a design judgement.

**Verification approach:**
1. Start the app and navigate to `/roleplay`
2. Load a character card (or verify auto-load if Phase 2 Task 4 is complete)
3. Send a test message containing:
   - Plain text (should render ivory/warm white)
   - `*italic text*` (should render grey)
   - `> A blockquote` (should show orange left border)
4. Verify: chat area has visible dark tint; background image shows through with reduced brightness
5. Verify: message bubbles are distinguishable (user vs AI have different tint intensity)

**Phase:** Phase 2 UAT steps 5, 8

---

### HV-3: Upload card readability (AC2.3)

**Why not automated:** This is an edge-case readability judgement. The upload card appears before any session is loaded, against the dark background. Whether its text, borders, and input fields are readable depends on contrast ratios that vary with the specific background image region. Automated contrast checking (e.g., axe-core) could partially address this, but the card overlays a photographic background with spatially varying luminance, making automated WCAG checks unreliable.

**Verification approach:**
1. Start the app and navigate to `/roleplay`
2. Before loading any character card, inspect the upload card
3. Verify: "Load Character Card" heading is readable
4. Verify: "Your name" input field text and border are visible
5. Verify: file upload drop zone text and border are visible
6. If the upload card is inside an expansion panel (Phase 2 Task 4 deviation), expand it and re-verify

**Phase:** Phase 2 UAT step 6 (adjusted for auto-load deviation: the upload card is inside a "Load Different Character" expansion panel)

---

### HV-4: Annotation page speaker labels (AC3.3)

**Why not automated:** This criterion spans two subsystems: the roleplay export (which produces `data-speaker`/`data-speaker-name` HTML attributes, tested by AC3.2 unit tests) and the annotation page (which renders those attributes as visual speaker labels via CSS `::before` pseudo-elements in `annotation/css.py` lines 157-222). The HTML structure correctness is tested automatically. But verifying that the annotation page actually renders "Jane:" and "Becky Bennett:" labels in the correct colours, positions, and styles requires loading the full annotation page with the exported document -- a cross-subsystem visual verification.

An E2E test could partially automate this by navigating to the annotation page after export and asserting that `[data-speaker-name]` elements are present in the DOM. However, CSS `::before` pseudo-element content is not accessible via standard Playwright selectors (`textContent` does not include pseudo-element text). Verifying the rendered label text would require `window.getComputedStyle(..., '::before').content` via `page.evaluate()`, which is fragile. The cost-benefit ratio favours human verification for this demo scope.

**Verification approach:**
1. Complete a roleplay conversation (at least 2 exchanges)
2. Click "Export to Workspace"
3. Verify: browser navigates to annotation page (`/annotation/{workspace_id}`)
4. Verify: each user turn shows a blue label (e.g., "Jane:") above the turn text
5. Verify: each assistant turn shows a green label (e.g., "Becky Bennett:") above the turn text
6. Verify: all turns from the roleplay session appear in the exported document (no missing turns)
7. Verify: turn content preserves markdown formatting (italics, bold, blockquotes render correctly)

**Phase:** Phase 3 UAT steps 6, 7, 8

---

## Coverage Summary

| Criterion | Automated | Human | Phase |
|-----------|-----------|-------|-------|
| AC1.1 -- Background covers viewport | -- | HV-1 | 2 |
| AC1.2 -- User avatar 50px round | Unit test | -- | 2 |
| AC1.3 -- AI avatar 50px round | Unit test | -- | 2 |
| AC2.1 -- Semi-transparent dark tint | -- | HV-2 | 2 |
| AC2.2 -- Ivory text, grey italics, orange quotes | -- | HV-2 | 2 |
| AC2.3 -- Upload card readable on dark bg | -- | HV-3 | 2 |
| AC3.1 -- Export creates loose workspace + ai_conversation doc | Integration test | -- | 3 |
| AC3.2 -- Correct data-speaker/data-speaker-name attributes | Unit test | -- | 3 |
| AC3.3 -- Annotation page renders speaker labels | -- | HV-4 | 3 |
| AC3.4 -- Export button disabled without session | Unit test | -- | 3 |

**Totals:** 5 criteria with automated tests, 5 criteria with human verification.

---

## Rationalisation Against Implementation Decisions

### Design deviation: `roleplay_export.py` extraction (Phase 3)

The design places the export function inline in `roleplay.py`. The implementation plan extracts `session_to_html()` into a separate `roleplay_export.py` module. This deviation directly enables the AC3.2 unit tests: `session_to_html()` is a pure function (markdown in, HTML string out) that can be tested without mocking NiceGUI's UI context. Without this extraction, testing AC3.2 would require either integration-level tests with a running NiceGUI server or extensive mocking -- both slower and more fragile. The deviation is justified and acknowledged in the Phase 3 plan header.

### Design deviation: Auto-load Becky Bennett (Phase 2 Task 4)

The design scopes Phase 2 as visual integration only. The implementation plan adds auto-loading of the bundled character card on page open. This deviation affects testing: HV-3 (upload card readability) must account for the upload card being inside a collapsed expansion panel rather than being the primary page element. The verification approach is adjusted accordingly. No new automated tests are needed for the auto-load itself -- it reuses the existing `parse_character_card()` + `_setup_session()` code paths that are already tested elsewhere.

### Phase 1 has no acceptance criteria coverage

Phase 1 is infrastructure: copying image files and creating a CSS file. No acceptance criteria are directly testable until Phase 2 applies these assets to the page. Phase 1 verification is operational (files exist, CSS parses, app starts without errors) and is covered by the Phase 1 UAT steps, not by acceptance criteria. This is appropriate -- Phase 1 is a dependency, not a deliverable.

### AC1.2 and AC1.3 test avatar parameter wiring, not visual size

The acceptance criteria specify "50px round image". The automated tests verify that the correct avatar URL is passed to `ui.chat_message()`. The 50px size and round shape are CSS rules in `roleplay.css` (`.q-avatar img` targeting). Verifying that the rendered avatar is actually 50px and circular requires visual inspection or pixel-level E2E assertions. This is covered implicitly by HV-2 (dark theme visual fidelity) where the human inspector sees the avatars alongside the messages. No separate human verification step is needed because the avatar appearance is visible during any HV-2 or HV-4 inspection.

### AC3.3 could be partially automated with E2E

An E2E test could navigate to the exported workspace's annotation page and assert `[data-speaker]` elements exist in the DOM. This would partially cover AC3.3 but not verify the CSS `::before` rendering. The implementation plan does not include an E2E test for this path because: (a) the roleplay page requires authentication and an active Claude API key for conversation, making E2E setup complex; (b) the annotation page's speaker label rendering is already exercised by existing E2E tests for AI conversation imports; (c) the HTML structure is fully covered by AC3.1 and AC3.2 automated tests. If a future iteration adds roleplay E2E tests (with mocked LLM responses), AC3.3 automation should be revisited.
