# Spike 2: Text Selection → Annotation

## Objective
Validate browser text selection can be captured and turned into visual highlights.

## Acceptance Criteria (from GitHub issue #2)
- [ ] Display static text in NiceGUI
- [ ] Click-drag to select text
- [ ] Capture selection range via `ui.run_javascript()`
- [ ] Create visual highlight (CSS class applied to selection)
- [ ] Selection data available in Python for creating annotation

## User Decisions
- New standalone page at `/demo/text-selection`
- Hardcoded sample text (no fixtures)
- In-memory only (no persistence)

---

## Files to Create

### 1. `tests/e2e/test_text_selection.py` (TDD - Write First)
E2E tests covering:
- Page loads with sample text
- Text can be selected via click-drag
- Selection data captured (text, start, end offsets)
- Visual highlight applied via CSS class
- Edge cases: unicode, multiline, cross-element selection

### 2. `src/promptgrimoire/pages/text_selection.py`
Demo page with:
- Sample conversation text in selectable container
- JavaScript selection handler using `emitEvent()`
- Python event handler via `ui.on('text_selected', ...)`
- Selection info display panel
- "Create Highlight" button
- CSS for `.annotation-highlight` class

## Files to Modify

### 3. `tests/conftest.py`
Add fixture:
```python
@pytest.fixture
def text_selection_url(app_server: str) -> str:
    return f"{app_server}/demo/text-selection"
```

Update `_SERVER_SCRIPT` to import the new page.

### 4. `src/promptgrimoire/__init__.py`
Add import:
```python
import promptgrimoire.pages.text_selection  # noqa: F401
```

---

## Implementation Steps (TDD Order)

1. **Add test fixture** to `conftest.py`
2. **Write failing E2E tests** in `test_text_selection.py`
3. **Create minimal page** - just route and sample text (first test passes)
4. **Add CSS styling** - `.annotation-highlight` class
5. **Add JavaScript selection handler** - `mouseup` listener, `emitEvent()`
6. **Add Python event handler** - `ui.on('text_selected', ...)`, update display
7. **Add highlight button** - wraps selection in `<span class="annotation-highlight">`
8. **Register page** in `__init__.py`

---

## Key Code Patterns

**JavaScript Selection Capture:**
```javascript
container.addEventListener('mouseup', function(e) {
    const selection = window.getSelection();
    if (selection.isCollapsed) return;
    const text = selection.toString().trim();
    if (!text) return;
    // Calculate offsets relative to container
    emitEvent('text_selected', { text, start, end, containerId });
});
```

**Python Event Handler:**
```python
async def handle_selection(e) -> None:
    text = e.args.get('text', '')
    start = e.args.get('start', 0)
    end = e.args.get('end', 0)
    # Update UI with selection data
    ui.notify(f'Selected: "{text}"')

ui.on('text_selected', handle_selection)
```

**CSS Highlight:**
```css
.annotation-highlight {
    background-color: rgba(255, 235, 59, 0.4);
    border-bottom: 2px solid #ffc107;
}
```

---

## Verification

1. **Run E2E tests:**
   ```bash
   uv run pytest tests/e2e/test_text_selection.py -v
   ```

2. **Manual verification:**
   ```bash
   uv run python -m promptgrimoire
   # Navigate to http://localhost:8080/demo/text-selection
   # Select text, verify info panel updates
   # Click "Create Highlight", verify CSS applied
   ```

3. **Full test suite:**
   ```bash
   uv run pytest -v
   ```

4. **Code quality (automatic via hooks):**
   ```bash
   uv run ruff check . && uv run ruff format --check . && uvx ty check
   ```

---

## Reference Files
- [sync_demo.py](src/promptgrimoire/pages/sync_demo.py) - Page pattern
- [test_two_tab_sync.py](tests/e2e/test_two_tab_sync.py) - E2E test pattern
- [selection-api.md](docs/browser/selection-api.md) - JS Selection API docs
- [ui-patterns.md](docs/nicegui/ui-patterns.md) - NiceGUI patterns
