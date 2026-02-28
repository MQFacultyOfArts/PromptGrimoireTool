# OpenRouter and ChatCraft Platform Handlers Design

**GitHub Issue:** [#209](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/209)

## Summary

PromptGrimoire's export pipeline processes chatbot conversation exports from multiple platforms (Claude, Gemini, OpenAI, etc.) into annotatable documents and PDFs. Each platform has a handler that detects its HTML fingerprint, strips UI chrome, and injects `data-speaker` attributes to identify conversation turns by role (user/assistant). This work adds two new handlers — OpenRouter and ChatCraft — and generalises the pipeline to support a third role: "system", which some platforms (ChatCraft in particular) expose.

The three-phase approach starts by refactoring the shared injection pipeline from hardcoded two-role logic to a generic loop, then adds downstream styling for the system role (CSS for the annotation page, a LaTeX environment for PDF export, and a Lua filter lookup table for LibreOffice). A guard test ensures that any handler returning an unstyled role fails loudly rather than silently producing broken output. With the pipeline generalised, the OpenRouter handler is added (detection via `data-testid="playground-container"`, two roles only), then the ChatCraft handler — the more complex of the two — which must infer speaker identity from avatar `<span title="...">` elements and classify them against a known model-prefix list, falling back to "user" for unrecognised names.

## Definition of Done

- OpenRouter platform handler exists and correctly detects, preprocesses, and injects speaker labels for OpenRouter playground exports
- ChatCraft platform handler exists and correctly detects, preprocesses, and injects speaker labels (including system prompt role) for ChatCraft.org conversation exports
- The shared pipeline (`preprocess_for_export`) supports a third "system" speaker role, available to all handlers
- Both fixtures are registered in `test_chatbot_fixtures.py` (PDF compilation) and `test_insert_markers_fixtures.py` (marker round-trip)
- Unit tests for each handler cover detection, preprocessing, and turn marker matching
- All existing tests continue to pass

## Acceptance Criteria

### platform-handlers-openrouter-chatcraft-209.AC1: Pipeline supports arbitrary speaker roles
- **AC1.1 Success:** Generic loop injects labels for all roles returned by a handler's `get_turn_markers()`, not just user/assistant
- **AC1.2 Success:** Existing handlers produce identical output after refactor (no behavioural change)
- **AC1.3 Success:** `data-speaker="system"` has CSS styling in annotation page (distinct from user/assistant colours)
- **AC1.4 Success:** Lua filter maps "system" role to `systemturn` environment with "System:" label
- **AC1.5 Success:** LaTeX preamble defines `systemcolor` and `systemturn` mdframed environment
- **AC1.6 Failure:** Guard test fails if a handler returns a role with no corresponding CSS or LaTeX styling

### platform-handlers-openrouter-chatcraft-209.AC2: OpenRouter handler detects and processes exports
- **AC2.1 Success:** Handler matches HTML containing `data-testid="playground-container"`
- **AC2.2 Success:** Handler does not match HTML from other platforms (Claude, Gemini, OpenAI, ChatCraft)
- **AC2.3 Success:** Preprocessing removes `[data-testid="playground-composer"]`
- **AC2.4 Success:** User and assistant speaker labels are injected at correct turn boundaries
- **AC2.5 Success:** Fixture compiles through PDF/LaTeX pipeline without errors
- **AC2.6 Success:** Marker round-trip property holds (extracted text at marker positions matches original)

### platform-handlers-openrouter-chatcraft-209.AC3: ChatCraft handler detects and processes exports
- **AC3.1 Success:** Handler matches HTML containing both `chakra-card` class and `chatcraft.org`
- **AC3.2 Success:** Handler does not match HTML from other platforms
- **AC3.3 Success:** Preprocessing removes sidebar chrome (accordion items, forms, menus)
- **AC3.4 Success:** Speaker classification maps "System Prompt" title to system role
- **AC3.5 Success:** Speaker classification maps hyphenated, spaceless titles (e.g. `claude-sonnet-4`) to assistant role
- **AC3.6 Success:** Speaker classification maps titles with spaces (e.g. human names) to user role
- **AC3.7 Success:** All three speaker labels (user, assistant, system) are injected at correct turn boundaries
- **AC3.8 Success:** Fixture compiles through PDF/LaTeX pipeline without errors
- **AC3.9 Success:** Marker round-trip property holds
- **AC3.10 Edge:** Title with no spaces and no hyphens (e.g. `ChatCraft`) falls through to user role

### platform-handlers-openrouter-chatcraft-209.AC4: Test infrastructure updated
- **AC4.1 Success:** Registry discovery test finds 8 handlers (up from 6)
- **AC4.2 Success:** Both fixtures appear in `CHATBOT_FIXTURES` and `_FIXTURES` lists
- **AC4.3 Success:** All existing tests pass without modification (except handler count assertions)

## Glossary

- **Platform handler**: A module in `src/promptgrimoire/export/platforms/` that encapsulates all platform-specific logic for a single chatbot UI — detection, chrome removal, and turn-marker patterns. Auto-discovered via `pkgutil.iter_modules` at import time.
- **`PlatformHandler` protocol**: A structural typing contract that all handlers implement: `matches(html)` for detection, `preprocess(tree)` for DOM mutation, and `get_turn_markers()` for returning `{role: regex_pattern}` mappings.
- **`preprocess_for_export()`**: The shared pipeline entry point in `platforms/__init__.py` that dispatches to the matching handler, strips chrome, and injects `data-speaker` attributes.
- **`data-speaker` attribute**: An HTML attribute marking the speaker role of a conversation turn (`user`, `assistant`, or `system`). CSS and LaTeX use this for distinct visual styling.
- **Speaker label injection**: The step where `data-speaker="{role}"` divs are inserted at turn boundaries so downstream rendering knows whose turn each block belongs to.
- **Turn markers**: Regex patterns (one per role) identifying the DOM elements corresponding to each conversation turn. Returned by `get_turn_markers()`.
- **Marker round-trip**: A test property asserting that text extracted at marker positions after preprocessing matches the original conversation text.
- **Chrome removal**: Stripping non-content UI elements (input areas, sidebars, buttons, forms) from exported HTML before processing.
- **OpenRouter**: An API aggregation platform with a web playground for comparing AI models. Its exports use `data-testid` attributes for structural identification.
- **ChatCraft**: An open-source chat interface at `chatcraft.org` built on Chakra UI. Supports multiple AI models and exposes system prompts.
- **Chakra UI**: A React component library used by ChatCraft. Its CSS class names (`chakra-card`, `chakra-accordion__item`) serve as detection and preprocessing signals.
- **`mdframed` environment**: A LaTeX package for drawing coloured bordered boxes. The export pipeline uses one per speaker role (`userturn`, `assistantturn`, `systemturn`).
- **Lua filter**: A script run by Pandoc during PDF export that maps `data-speaker` role values to the appropriate LaTeX environment and label.
- **Guard test**: A parametrised test collecting all role values from all handlers, asserting each has CSS and LaTeX styling — so adding a handler without styling fails loudly.

## Architecture

### Pipeline Extension: Generic Role Loop

The speaker label injection in `preprocess_for_export()` (`src/promptgrimoire/export/platforms/__init__.py`) currently hardcodes two blocks for "user" and "assistant". This design replaces them with a generic loop over all keys returned by `get_turn_markers()`. Each key becomes the `data-speaker` attribute value. Handlers define their own role vocabulary — the pipeline imposes no fixed set.

The `PlatformHandler` protocol signature is unchanged (`get_turn_markers() -> dict[str, str]`). The semantic shift is documented: keys are arbitrary role names, values are regex patterns.

Downstream touchpoints for the new "system" role:

| File | Change |
|------|--------|
| `src/promptgrimoire/pages/annotation/css.py` | Add `[data-speaker="system"]::before` CSS rule (amber/orange colour) |
| `src/promptgrimoire/export/filters/libreoffice.lua` | Replace binary ternary chains with lookup table mapping role → environment, label, colour |
| `src/promptgrimoire/export/promptgrimoire-export.sty` | Define `systemcolor` and `systemturn` mdframed environment |

The input pipeline (`src/promptgrimoire/input_pipeline/html_input.py`) already handles `data-speaker` generically — it preserves the attribute by name, not by value. No changes needed there.

### OpenRouter Handler

Detection: `data-testid="playground-container"` (unique to OpenRouter playground UI).

Preprocessing: Remove `[data-testid="playground-composer"]` (input area). Remaining playground chrome (buttons, SVGs, interactive controls) is handled by `remove_common_chrome()` in `base.py`.

Turn markers:
- `user`: `data-testid="user-message"`
- `assistant`: `data-testid="assistant-message"`

No system role — OpenRouter does not expose system prompts in its playground UI.

### ChatCraft Handler

Detection: `chakra-card` class AND `chatcraft.org` substring in HTML. Both conditions required to avoid false-positives (Chakra UI is a common framework).

Preprocessing: More complex than other handlers. ChatCraft has no `data-role` or `data-speaker` attributes. Speaker identity lives in the avatar `<span title="SPEAKER_NAME">` inside each card body. The handler's `preprocess()` method:

1. Removes sidebar/chrome: `.chakra-accordion__item`, `form` elements, `.chakra-menu__menuitem`
2. Walks remaining `.chakra-card` elements
3. Finds the avatar `<span>` with a `title` attribute inside each card
4. Classifies the speaker using `_classify_speaker(title)`:
   - `"System Prompt"` exact match → `"system"`
   - No spaces and at least one hyphen → `"assistant"` (model identifiers like `claude-sonnet-4`, `gpt-4`, `qwen3.5-35B-A3B` universally use hyphens; human display names universally have spaces)
   - Everything else → `"user"`
5. Injects `data-speaker="{role}"` onto the card element

Turn markers then match the injected attributes, same as every other handler downstream. Because ChatCraft's `preprocess()` already injects `data-speaker` attributes, the `already_has_labels` guard in `preprocess_for_export()` will skip the regex-based turn marker injection. This is correct — `get_turn_markers()` still returns patterns matching the injected attributes, but they serve only the Protocol contract and the guard test, not runtime injection.

```python
# Contract: _classify_speaker
def _classify_speaker(title: str) -> str:
    """Classify a ChatCraft avatar title into a speaker role.

    Heuristic: model identifiers contain hyphens but no spaces
    (e.g. claude-sonnet-4, gpt-4). Human names have spaces.
    """
    ...
```

### Guard Test: Role Coverage

A parametrised test collects all role values from all registered handlers' `get_turn_markers()` and asserts each role has corresponding CSS and LaTeX styling. This mitigates the open-loop risk: unstyled roles fail the test, not silently.

## Existing Patterns

Investigation found 6 existing platform handlers following the Protocol + Registry autodiscovery pattern (`src/promptgrimoire/export/platforms/__init__.py`). Each handler is a module with a module-level `handler` instance. The autodiscovery mechanism (`pkgutil.iter_modules`) requires no registration — new modules are found automatically on import.

Handler complexity ranges from trivial (Gemini: empty `preprocess()`) to complex (Claude: semantic attribute marking, Wikimedia: 23 CSS selectors for chrome removal). The ChatCraft handler falls into the Claude-level complexity — it injects semantic attributes during preprocessing.

All existing handler tests follow a three-class pattern: `TestXXXHandlerMatches`, `TestXXXHandlerPreprocess`, `TestXXXHandlerTurnMarkers`. Both new handlers follow this pattern.

The Lua filter (`src/promptgrimoire/export/filters/libreoffice.lua`) currently uses binary ternary chains for role → label/colour mapping. This design replaces them with a lookup table, which is a standard Lua pattern and more maintainable.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Pipeline Extension (System Role Support)

**Goal:** Generalise the speaker label injection pipeline to support arbitrary roles, and add downstream styling for the "system" role.

**Components:**
- `src/promptgrimoire/export/platforms/__init__.py` — replace hardcoded user/assistant injection blocks with generic loop over `get_turn_markers().items()`
- `src/promptgrimoire/pages/annotation/css.py` — add `[data-speaker="system"]::before` CSS rule
- `src/promptgrimoire/export/filters/libreoffice.lua` — replace binary ternary with lookup table for role → environment/label/colour
- `src/promptgrimoire/export/promptgrimoire-export.sty` — define `systemcolor` and `systemturn` mdframed environment
- Guard test in `tests/unit/export/platforms/` — parametrised test asserting all handler roles have CSS and LaTeX styling

**Dependencies:** None (first phase)

**Done when:** All existing tests pass unchanged. The generic loop produces identical output for existing handlers. The system role has CSS, LaTeX, and Lua filter support. Guard test passes for all current roles (user, assistant) and would catch an unstyled role.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: OpenRouter Handler

**Goal:** Detect, preprocess, and inject speaker labels for OpenRouter playground exports.

**Components:**
- `src/promptgrimoire/export/platforms/openrouter.py` — handler module with `OpenRouterHandler` class
- `tests/unit/export/platforms/test_openrouter.py` — unit tests (detection, preprocessing, turn markers)
- `tests/integration/test_chatbot_fixtures.py` — add `openrouter_fizzbuzz.html` to `CHATBOT_FIXTURES` and `_COMPLETE_CONVERSATION_FIXTURES`
- `tests/unit/input_pipeline/test_insert_markers_fixtures.py` — add `openrouter_fizzbuzz` to `_FIXTURES`
- `tests/unit/export/platforms/test_registry.py` — update handler count (6 → 7) and handler name assertions

**Dependencies:** Phase 1 (generic loop, though OpenRouter doesn't use system role)

**Done when:** Handler detects OpenRouter HTML, strips composer chrome, injects user/assistant labels. Fixture compiles through PDF pipeline. Marker round-trip tests pass. Registry discovers 7 handlers.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: ChatCraft Handler

**Goal:** Detect, preprocess, and inject speaker labels (including system role) for ChatCraft.org exports.

**Components:**
- `src/promptgrimoire/export/platforms/chatcraft.py` — handler module with `ChatCraftHandler` class and `_classify_speaker()` function
- `tests/unit/export/platforms/test_chatcraft.py` — unit tests (detection, preprocessing, turn markers, speaker classification edge cases)
- `tests/integration/test_chatbot_fixtures.py` — add `chatcraft_prd.html` to `CHATBOT_FIXTURES` and `_COMPLETE_CONVERSATION_FIXTURES`
- `tests/unit/input_pipeline/test_insert_markers_fixtures.py` — add `chatcraft_prd` to `_FIXTURES`
- `tests/unit/export/platforms/test_registry.py` — update handler count (7 → 8)

**Dependencies:** Phase 1 (system role support required for ChatCraft's three-role detection)

**Done when:** Handler detects ChatCraft HTML, removes sidebar/chrome, classifies speakers from avatar titles, injects user/assistant/system labels. Fixture compiles through PDF pipeline with all three speaker labels visible. Marker round-trip tests pass. Registry discovers 8 handlers. Guard test passes with system role included.
<!-- END_PHASE_3 -->

## Additional Considerations

**ChatCraft's `get_turn_markers()` is Protocol-only:** Because ChatCraft injects `data-speaker` attributes during `preprocess()`, the `already_has_labels` guard in `preprocess_for_export()` will skip the regex injection phase. The turn marker patterns exist to satisfy the `PlatformHandler` protocol and the guard test, not for runtime use. This is analogous to Wikimedia returning an empty dict — some handlers don't use the regex injection path.

**Guard test CSS verification:** The guard test checks CSS coverage via substring matching on the CSS string in `css.py` (e.g., asserting `[data-speaker="system"]` appears). This is a pragmatic check, not a syntax validator. It catches the common failure mode (forgot to add a rule) without over-engineering.
