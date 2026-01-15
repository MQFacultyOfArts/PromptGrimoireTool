# Test Review: Spike 1 - pycrdt + NiceGUI WebSocket Sync

## Spike 1 Objectives (from PRD/Architecture)

1. Create a pycrdt `Doc` with a `Text` type
2. Connect two browser tabs to the same NiceGUI server
3. Type in one tab, see real-time updates in the other
4. Verify CRDT conflict resolution works correctly
5. Updates sync within <100ms (acceptance criteria)

---

## Test File Analysis

### 1. Integration Tests (`tests/integration/test_crdt_sync.py`)

**Coverage Assessment: STRONG**

| Objective | Covered | Tests |
|-----------|---------|-------|
| Doc/Text creation | Yes | `TestDocTextCreation` (5 tests) |
| Sync between docs | Yes | `TestDocSynchronization` (6 tests) |
| Observer callbacks | Yes | `TestObserverCallbacks` (6 tests) |
| Edge cases | Yes | `TestEdgeCases` (5 tests) |

**Strengths:**

- Thorough coverage of pycrdt fundamentals
- Tests bidirectional sync (`test_bidirectional_sync`)
- Tests concurrent edit merging (`test_concurrent_edits_merge`)
- Tests idempotency (`test_update_is_idempotent`)
- Validates update format is `bytes` (network-friendly)
- Observer-to-sync pattern tested (`test_observer_update_can_sync_another_doc`)
- Transaction batching tested (`test_transaction_batches_changes`)

**Missing Tests:**

1. **Differential sync with state vectors** - The docs show `get_update(state_vector)` for efficient sync, but tests only use `get_update()` (full state). Add:

   ```python
   def test_differential_sync_with_state_vector(self) -> None:
       """Differential sync sends only missing updates."""
       doc1 = Doc()
       doc1["text"] = text1 = Text("Initial")

       doc2 = Doc()
       doc2["text"] = text2 = Text()

       # Initial full sync
       doc2.apply_update(doc1.get_update())
       assert str(text2) == "Initial"

       # Record doc2's state before doc1's next change
       state_before = doc2.get_state()

       # doc1 makes more changes
       text1 += " more"

       # Differential sync - only get what doc2 is missing
       diff_update = doc1.get_update(state_before)
       full_update = doc1.get_update()

       # Diff should be smaller than full update
       assert len(diff_update) < len(full_update)

       # Applying diff should still result in correct state
       doc2.apply_update(diff_update)
       assert str(text2) == "Initial more"
   ```

2. **Origin tracking to prevent echo loops** - Real sync implementations need to track transaction origin. Add:

   ```python
   def test_transaction_origin_tracking(self) -> None:
       """Transaction origin can be used to prevent echo loops."""
       doc1 = Doc()
       doc1["text"] = text1 = Text()

       doc2 = Doc()
       doc2["text"] = text2 = Text()

       received_origins: list[Any] = []

       def on_change(event: TransactionEvent) -> None:
           received_origins.append(event.origin)

       doc2.observe(on_change)

       # Change with origin
       with doc1.transaction(origin="client-1"):
           text1 += "Hello"

       # The update carries the origin when applied
       update = doc1.get_update()
       with doc2.transaction(origin="client-1"):
           doc2.apply_update(update)

       # Verify we can filter by origin
       assert received_origins[-1] == "client-1"

   def test_can_skip_echo_updates_by_origin(self) -> None:
       """Demonstrates pattern to skip re-broadcasting own updates."""
       doc = Doc()
       doc["text"] = text = Text()

       broadcast_count = 0
       MY_ORIGIN = "my-client-id"

       def on_change(event: TransactionEvent) -> None:
           nonlocal broadcast_count
           # Skip if this was our own change
           if event.origin != MY_ORIGIN:
               broadcast_count += 1

       doc.observe(on_change)

       # Local change - should not trigger broadcast
       with doc.transaction(origin=MY_ORIGIN):
           text += "local edit"

       assert broadcast_count == 0

       # Remote change (different origin) - should trigger broadcast
       with doc.transaction(origin="other-client"):
           text += " remote edit"

       assert broadcast_count == 1
   ```

3. **Position-based insertion (cursor positioning)** - The pycrdt API supports `Text.insert(index, value)` for inserting at specific positions. This is critical for real collaborative editing. Add:

   ```python
   class TestPositionBasedEditing:
       """Test position-based text operations for cursor-aware editing."""

       def test_insert_at_position(self) -> None:
           """Can insert text at specific index."""
           doc = Doc()
           doc["text"] = text = Text("Hello World!")
           text.insert(5, ",")
           assert str(text) == "Hello, World!"

       def test_insert_at_position_syncs(self) -> None:
           """Position-based insert syncs correctly."""
           doc1 = Doc()
           doc1["text"] = text1 = Text("Hello World")

           doc2 = Doc()
           doc2["text"] = text2 = Text()
           doc2.apply_update(doc1.get_update())

           # Insert at position 5 in doc1
           text1.insert(5, " Beautiful")

           doc2.apply_update(doc1.get_update())
           assert str(text2) == "Hello Beautiful World"

       def test_delete_at_position(self) -> None:
           """Can delete text at specific index."""
           doc = Doc()
           doc["text"] = text = Text("Hello, World!")
           del text[5]  # Delete the comma
           assert str(text) == "Hello World!"

       def test_delete_range(self) -> None:
           """Can delete a range of text."""
           doc = Doc()
           doc["text"] = text = Text("Hello, World!")
           del text[5:7]  # Delete ", "
           assert str(text) == "HelloWorld!"

       def test_replace_range(self) -> None:
           """Can replace text at specific range."""
           doc = Doc()
           doc["text"] = text = Text("Hello, World!")
           text[7:12] = "Brian"
           assert str(text) == "Hello, Brian!"

       def test_concurrent_position_inserts(self) -> None:
           """Concurrent inserts at different positions merge correctly."""
           doc1 = Doc()
           doc1["text"] = text1 = Text("Hello World")

           doc2 = Doc()
           doc2["text"] = text2 = Text()
           doc2.apply_update(doc1.get_update())

           # doc1 inserts at position 0
           text1.insert(0, "Say: ")

           # doc2 inserts at end (position 11)
           text2.insert(11, "!")

           # Exchange updates
           update1 = doc1.get_update()
           update2 = doc2.get_update()
           doc1.apply_update(update2)
           doc2.apply_update(update1)

           # Both should have same merged result
           assert str(text1) == str(text2)
           assert "Say:" in str(text1)
           assert "!" in str(text1)

       def test_concurrent_inserts_at_same_position(self) -> None:
           """Concurrent inserts at same position are both preserved."""
           doc1 = Doc()
           doc1["text"] = text1 = Text("AC")

           doc2 = Doc()
           doc2["text"] = text2 = Text()
           doc2.apply_update(doc1.get_update())

           # Both insert at position 1 (between A and C)
           text1.insert(1, "B1")
           text2.insert(1, "B2")

           # Exchange updates
           update1 = doc1.get_update()
           update2 = doc2.get_update()
           doc1.apply_update(update2)
           doc2.apply_update(update1)

           # Both edits should be present, order determined by CRDT
           assert str(text1) == str(text2)
           assert "B1" in str(text1)
           assert "B2" in str(text1)
           assert str(text1).startswith("A")
           assert str(text1).endswith("C")
   ```

4. **StickyIndex for cursor persistence** - pycrdt provides `StickyIndex` for cursor positions that survive concurrent edits. Add:

   ```python
   class TestStickyIndex:
       """Test StickyIndex for cursor position tracking."""

       def test_sticky_index_survives_insert_before(self) -> None:
           """StickyIndex adjusts when text inserted before it."""
           doc = Doc()
           doc["text"] = text = Text("Hello World")

           # Create sticky index at position 6 (start of "World")
           sticky = text.sticky_index(6)
           assert sticky.get_index() == 6

           # Insert text before the sticky position
           text.insert(0, "Say ")

           # Sticky index should have moved
           assert sticky.get_index() == 10  # "Say Hello ".length

       def test_sticky_index_stable_on_insert_after(self) -> None:
           """StickyIndex stays put when text inserted after it."""
           doc = Doc()
           doc["text"] = text = Text("Hello World")

           # Create sticky index at position 5 (end of "Hello")
           sticky = text.sticky_index(5)

           # Insert text after the sticky position
           text.insert(6, "Beautiful ")

           # Sticky index should not have moved
           assert sticky.get_index() == 5
   ```

---

### 2. E2E Tests (`tests/e2e/test_two_tab_sync.py`)

**Coverage Assessment: EXCELLENT structure, needs fixes**

| Objective | Covered | Tests |
|-----------|---------|-------|
| Two tabs connected | Yes | All tests use two contexts |
| Typing syncs across | Yes | `test_typing_in_tab1_appears_in_tab2`, `test_typing_in_tab2_appears_in_tab1` |
| <100ms sync | Yes | `test_sync_happens_within_100ms` |
| CRDT conflict resolution | Partial | `test_concurrent_edits_both_visible` (weak assertion) |

**Strengths:**

- Direct mapping to spike acceptance criteria
- Separate browser contexts (simulates real multi-user)
- Bidirectional sync tested
- Late joiner scenario tested (`TestLateJoiner`)
- Three-tab sync tested (beyond requirements)
- Disconnect/reconnect scenarios (`TestDisconnectReconnect`)
- Unicode/long content edge cases

**Issues to Fix:**

1. **Missing `new_context` fixture** - Tests will fail. Add to `tests/conftest.py` or `tests/e2e/conftest.py`:

   ```python
   import pytest
   from playwright.sync_api import Browser

   @pytest.fixture
   def new_context(browser: Browser):
       """Factory fixture for creating new browser contexts."""
       contexts = []

       def _new_context():
           ctx = browser.new_context()
           contexts.append(ctx)
           return ctx

       yield _new_context

       # Cleanup all created contexts
       for ctx in contexts:
           ctx.close()
   ```

2. **Weak concurrent edit assertion** (line 177) - Change from `or` to `and`:

   ```python
   # Current (too weak):
   assert "A" in text1 or "B" in text1

   # Should be:
   assert "A" in text1 and "B" in text1, f"Expected both A and B, got: {text1}"
   ```

3. **100ms timeout too aggressive** - Increase to 250ms with comment:

   ```python
   # Accept slightly higher latency to reduce CI flakiness
   # while still validating "real-time" feel (<250ms)
   expect(page2.get_by_test_id("synced-text")).to_have_text(
       "Speed test", timeout=250
   )
   ```

4. **No context cleanup** - The fixture above handles this, but existing tests should use the fixture properly.

5. **`fill()` vs `type()` - Discussion:**

   The tests mostly use `fill()` which atomically replaces content. This is fine for testing the sync mechanism at the WebSocket/CRDT level, but doesn't exercise character-by-character CRDT behavior.

   For Spike 1's objectives (validate sync works), `fill()` is sufficient. For Spike 2 (text selection + annotation), character-level tests will be needed.

   **Recommendation:** Keep `fill()` for basic sync tests, add one explicit character-by-character test:

   ```python
   def test_character_by_character_typing_syncs(
       self, page: Page, new_context, spike1_url: str
   ) -> None:
       """Character-by-character typing syncs in real-time."""
       page.goto(spike1_url)

       context2 = new_context()
       page2 = context2.new_page()
       page2.goto(spike1_url)

       # Type character by character (not fill)
       input_field = page.get_by_label("Edit text")
       input_field.type("Hello", delay=50)  # 50ms between chars

       # Each character should have synced
       expect(page2.get_by_test_id("synced-text")).to_have_text("Hello")
   ```

6. **Missing cursor position test** - Add test for mid-text insertion:

   ```python
   def test_insert_at_cursor_position_syncs(
       self, page: Page, new_context, spike1_url: str
   ) -> None:
       """Inserting at cursor position (not just appending) syncs correctly."""
       page.goto(spike1_url)

       context2 = new_context()
       page2 = context2.new_page()
       page2.goto(spike1_url)

       # Initial text
       page.get_by_label("Edit text").fill("HelloWorld")
       expect(page2.get_by_test_id("synced-text")).to_have_text("HelloWorld")

       # Move cursor to middle and insert (simulates real editing)
       input_field = page.get_by_label("Edit text")
       input_field.click()

       # Option A: Use keyboard navigation
       input_field.press("Home")
       for _ in range(5):
           input_field.press("ArrowRight")
       input_field.type(" ")  # Insert space

       # Option B: Use setSelectionRange via evaluate (more precise)
       # await input_field.evaluate("(el) => el.setSelectionRange(5, 5)")
       # input_field.type(" ")

       expect(page2.get_by_test_id("synced-text")).to_have_text("Hello World")
   ```

   **Playwright cursor positioning options:**
   - **Keyboard navigation**: `press("Home")` + `press("ArrowRight")` - works but verbose
   - **`setSelectionRange` via evaluate**: More precise for input fields:
     ```python
     await locator.evaluate("(el, pos) => el.setSelectionRange(pos, pos)", 5)
     ```
   - **For contenteditable**: Use `Range` API via evaluate:
     ```python
     await locator.evaluate("""(el, pos) => {
         const range = document.createRange();
         const sel = window.getSelection();
         range.setStart(el.firstChild, pos);
         range.collapse(true);
         sel.removeAllRanges();
         sel.addRange(range);
     }""", 5)
     ```

   See: [Playwright GitHub Issue #22873](https://github.com/microsoft/playwright/issues/22873) - Feature request for built-in cursor positioning methods.

   **Note:** This test depends on the implementation capturing cursor position and using `Text.insert()` rather than replacing entire content. If the current implementation uses full replacement on each keystroke, this test will help identify that gap.

---

## Summary: Aptness to Spike Objectives

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Validates pycrdt works | Excellent | Comprehensive integration tests |
| Two-tab WebSocket sync | Good | E2E tests cover it, pending fixture fix |
| Real-time (<100ms) | Risky | Test exists but may be flaky |
| Conflict resolution | Weak | Concurrent test assertion too permissive |
| Foundation for future | Good | Observer patterns, transactions covered |

---

## Recommended Changes

### Critical (tests will fail without these)

1. **Add `new_context` fixture** to `tests/conftest.py` with cleanup

### Important (tests pass but don't validate correctly)

2. **Fix concurrent edit assertion** - change `or` to `and` at line 177
3. **Increase 100ms timeout** to 250ms with explanatory comment

### Should Add (expand test coverage)

4. **Add differential sync test** with `get_state()` / `get_update(state)`
5. **Add origin tracking tests** for echo loop prevention
6. **Add position-based editing tests** (`Text.insert()`, `del text[i]`, `text[i:j] = x`)
7. **Add StickyIndex tests** for cursor persistence
8. **Add character-by-character typing E2E test**
9. **Add cursor position insertion E2E test**

### Documentation Reference

The pycrdt API provides these relevant methods (cache to `docs/pycrdt/api-reference.md`):

- `Text.insert(index, value, attrs=None)` - insert at position
- `del text[index]` / `del text[start:stop]` - delete at position/range
- `text[start:stop] = value` - replace range
- `text.sticky_index(index, assoc)` - cursor that survives edits
- `doc.transaction(origin=...)` - origin for echo prevention
- `doc.get_state()` / `doc.get_update(state)` - differential sync
- `event.origin` on `TransactionEvent` - check update origin

Sources:

- [pycrdt API Reference](https://y-crdt.github.io/pycrdt/api_reference/)
- [pycrdt PyPI](https://pypi.org/project/pycrdt/)
- [Playwright cursor positioning issue #22873](https://github.com/microsoft/playwright/issues/22873)

---

## Pre-Implementation Tasks

1. **Cache pycrdt API reference** to `docs/pycrdt/api-reference.md` (use cache-docs skill)
2. **Cache Playwright selection docs** if needed for E2E cursor tests
