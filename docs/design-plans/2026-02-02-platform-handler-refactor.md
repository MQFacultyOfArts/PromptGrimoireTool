# Platform Handler Refactor Design

## Summary

This refactor consolidates platform-specific HTML preprocessing logic that currently exists in two separate modules (`speaker_preprocessor.py` and `chrome_remover.py`) into a single, extensible architecture. Each AI platform (OpenAI, Claude, Gemini, AI Studio, ScienceOS) exports conversation HTML with different structural quirks: different CSS classes for UI chrome, different native speaker labels (e.g., "You said:" in OpenAI, `<div class="author-label">` in AI Studio), and platform-specific features like Claude's thinking sections. The current code handles these differences through nested conditionals and separate processing steps, making it difficult to understand what happens to each platform's HTML and creating edge cases like duplicate labels ("You said: User:").

The new architecture uses a Protocol + Registry pattern where each platform gets its own handler module that implements three methods: `matches()` to detect the platform, `preprocess()` to remove chrome and native labels in a single pass, and `get_turn_markers()` to define speaker label injection patterns. Handlers are autodiscovered at import time via `pkgutil`, eliminating manual registration. The refactor also replaces BeautifulSoup with selectolax (5-30x faster) for HTML parsing and introduces a unified entry point `preprocess_for_export()` that handles detection, preprocessing, and label injection in one call. This improves both cognitive load (each platform is self-contained) and maintainability (adding new platforms requires only creating a new handler module).

## Definition of Done

- [ ] Each platform (OpenAI, Claude, Gemini, AI Studio, ScienceOS) has its own module in `src/promptgrimoire/export/platforms/`
- [ ] Each platform handler implements the `PlatformHandler` protocol
- [ ] Platform handlers are autodiscovered via `pkgutil.iter_modules()`
- [ ] Single entry point `preprocess_for_export(html, platform_hint=None)` replaces both `inject_speaker_labels()` and `remove_ui_chrome()`
- [ ] Optional `platform_hint` parameter allows user override of autodiscovery
- [ ] Chrome removal logic moved from `chrome_remover.py` into platform handlers
- [ ] Native label stripping eliminates duplicate labels (e.g., "You said: User:")
- [ ] HTML parsing uses `selectolax` (lexbor backend) instead of BeautifulSoup
- [ ] All 40 existing integration tests pass
- [ ] Each platform has isolated unit tests
- [ ] Old files (`speaker_preprocessor.py`, `chrome_remover.py`) deleted

## Glossary

- **Protocol (typing.Protocol)**: Python's structural typing mechanism for defining interfaces without inheritance; classes match the protocol if they have the required attributes/methods, regardless of explicit subclassing
- **autodiscovery**: Runtime module scanning technique using `pkgutil.iter_modules()` to automatically find and register handlers without manual imports
- **chrome**: UI elements that are part of the platform's interface but not part of the conversation content (navigation bars, buttons, metadata sections); needs removal before PDF export
- **native labels**: Platform-generated speaker indicators already present in the HTML (e.g., "You said:", "Model:"); must be stripped to prevent duplication when our own labels are injected
- **selectolax**: Fast HTML parser with CSS selector support; uses Lexbor (C library) backend; 5-30x faster than BeautifulSoup
- **BeautifulSoup**: Python HTML/XML parser library being replaced in this refactor
- **thinking sections**: Claude-specific feature showing internal reasoning; requires special marking with `data-thinking` attribute for styling in PDF export
- **data attributes**: HTML custom attributes (prefix `data-`) used to pass metadata from Python preprocessing to Lua filter; Pandoc strips the prefix but preserves the attribute name
- **Pandoc**: Universal document converter used in the export pipeline to transform HTML to LaTeX
- **Lua filter**: Custom Pandoc extension that processes the document during HTML-to-LaTeX conversion; reads `data-speaker` attributes to inject styled speaker labels
- **turn markers**: Regex patterns that identify conversation turn boundaries (where one speaker stops and another begins); used by the label injection logic
- **graceful degradation**: Design principle where unknown platforms return unchanged HTML instead of failing; allows the system to handle new platforms without explicit support
- **cognitive isolation**: Architectural principle where platform-specific logic is contained in separate modules, reducing mental load when working on one platform's behavior

## Architecture

Platform-specific preprocessing using Protocol + Registry pattern with autodiscovery.

**Directory structure:**
```
src/promptgrimoire/export/platforms/
├── __init__.py      # Protocol, registry, preprocess_for_export()
├── base.py          # Shared utilities (if needed)
├── openai.py
├── claude.py
├── gemini.py
├── aistudio.py
└── scienceos.py
```

**Protocol interface** (`platforms/__init__.py`):
```python
from typing import Protocol, runtime_checkable
from selectolax.lexbor import LexborHTMLParser

@runtime_checkable
class PlatformHandler(Protocol):
    name: str

    def matches(self, html: str) -> bool:
        """Return True if this handler should process the HTML."""
        ...

    def preprocess(self, tree: LexborHTMLParser) -> None:
        """Remove chrome, strip native labels, mark special blocks."""
        ...

    def get_turn_markers(self) -> dict[str, str]:
        """Return {'user': pattern, 'assistant': pattern} for turn injection."""
        ...
```

**Autodiscovery** via `pkgutil.iter_modules()`:
```python
def _discover_handlers() -> None:
    """Auto-discover all platform handlers in this package."""
    for finder, name, ispkg in pkgutil.iter_modules(__path__, f"{__name__}."):
        if name.endswith(('.base', '.__init__')):
            continue
        module = importlib.import_module(name)
        if hasattr(module, 'handler'):
            _handlers[module.handler.name] = module.handler
```

**Entry point:**
```python
def preprocess_for_export(html: str, platform_hint: str | None = None) -> str:
    """Main entry point: detect platform, preprocess, inject labels.

    Args:
        html: Raw HTML from chatbot export
        platform_hint: Optional platform name to skip autodiscovery (e.g., "openai")
    """
    if platform_hint:
        handler = _handlers.get(platform_hint)
    else:
        handler = get_handler(html)

    if handler is None:
        return html  # Unknown platform, return unchanged

    tree = LexborHTMLParser(html)
    handler.preprocess(tree)
    _inject_speaker_labels(tree, handler)
    return tree.html()
```

**Data flow:**
```
Raw HTML
  ↓
get_handler(html) → PlatformHandler | None
  ↓
handler.matches(html) validates
  ↓
tree = LexborHTMLParser(html)
  ↓
handler.preprocess(tree)  # Removes chrome, strips native labels, marks special blocks
  ↓
_inject_speaker_labels(tree, handler.get_turn_markers())
  ↓
tree.html() → processed HTML string
  ↓
(existing pipeline: latex.py → Lua filter → PDF)
```

## Existing Patterns

Investigation found:

1. **Pattern-based detection** in current `speaker_preprocessor.py`:
   - `_PLATFORM_PATTERNS` dict maps platform → detection regex
   - `_TURN_PATTERNS` nested dict maps platform → role → boundary regex
   - Claude-specific `_mark_thinking_sections()` special case

2. **Pattern list approach** in `chrome_remover.py`:
   - `_CHROME_CLASS_PATTERNS` list for class substring matching
   - `_CHROME_ID_PATTERNS` list for ID prefix matching
   - Helper functions, not per-platform conditionals

3. **Data attributes for inter-layer communication**:
   - `data-speaker` passed from Python to Lua filter
   - `data-thinking` for Claude thinking sections
   - Pandoc strips `data-` prefix automatically

**This design follows** the pattern-based approach but moves patterns into platform-specific modules for better cognitive isolation. Each platform becomes a self-contained unit.

**Divergence:** Replaces BeautifulSoup with selectolax (5-30x faster, similar API). Justified by performance improvement and good CSS selector support.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Add selectolax dependency and create package structure

**Goal:** Set up the platforms package with Protocol definition

**Components:**
- Add `selectolax` to `pyproject.toml` dependencies
- Create `src/promptgrimoire/export/platforms/__init__.py` with Protocol and registry
- Create empty `src/promptgrimoire/export/platforms/base.py` for shared utilities

**Dependencies:** None

**Done when:** `uv sync` succeeds, `from promptgrimoire.export.platforms import PlatformHandler` works
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Implement OpenAI handler

**Goal:** First platform handler as reference implementation

**Components:**
- `src/promptgrimoire/export/platforms/openai.py` — handler with matches(), preprocess(), get_turn_markers()
- `tests/unit/export/platforms/test_openai.py` — unit tests for detection, chrome removal, native label stripping

**Dependencies:** Phase 1

**Done when:** OpenAI handler detects platform, removes chrome, strips "You said:" native labels, unit tests pass
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Implement remaining platform handlers

**Goal:** Complete all five platform handlers

**Components:**
- `src/promptgrimoire/export/platforms/claude.py` — includes thinking section marking
- `src/promptgrimoire/export/platforms/gemini.py`
- `src/promptgrimoire/export/platforms/aistudio.py` — strips native `<div class="author-label">` elements
- `src/promptgrimoire/export/platforms/scienceos.py`
- Unit tests for each platform

**Dependencies:** Phase 2 (use as template)

**Done when:** All five handlers implemented with passing unit tests
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Implement autodiscovery and entry point

**Goal:** Registry discovers handlers, single entry point works, user override available

**Components:**
- Complete `platforms/__init__.py` with `_discover_handlers()`, `get_handler()`, `preprocess_for_export(platform_hint=None)`
- `tests/unit/export/platforms/test_registry.py` — tests for autodiscovery, dispatch, import failure handling, and platform_hint override

**Dependencies:** Phase 3

**Done when:** `preprocess_for_export()` correctly dispatches to platform handlers, `platform_hint` override works, import failures are logged and skipped (not crash), registry tests pass
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Update call sites and delete old files

**Goal:** Migrate to new API, remove deprecated code

**Components:**
- Update `tests/integration/test_chatbot_fixtures.py` to use `preprocess_for_export()`
- Update any other call sites found via grep
- Delete `src/promptgrimoire/export/speaker_preprocessor.py`
- Delete `src/promptgrimoire/export/chrome_remover.py`
- Delete or migrate tests from `test_css_fidelity.py` and `test_chrome_remover.py`

**Dependencies:** Phase 4

**Done when:** All 40 integration tests pass, old files deleted, no references to old API remain
<!-- END_PHASE_5 -->

## Additional Considerations

**Backward compatibility:** None needed. This is internal refactor with no public API.

**Error handling:** Unknown platforms return HTML unchanged (graceful degradation). Malformed HTML handled by selectolax's lenient parser. Handler import failures should be logged and skip the handler (don't crash the registry).

**User-selectable platform:** Add optional `platform_hint` parameter to `preprocess_for_export()`:
- `None` (default): Autodiscover via `matches()`
- Platform name string: Skip autodiscovery, use specified handler directly
- Useful when autodiscovery fails (platform changed markup) or user knows better

**Selectolax fallback:** If integration tests fail due to selectolax parsing differences, fall back to BeautifulSoup. The Protocol interface is parser-agnostic - handlers receive a tree object, implementation can swap parsers without changing handler logic.

**Testing isolation:** Each platform handler is independently testable with synthetic HTML. Integration tests use real fixture files. Registry tests must verify import failure handling.
