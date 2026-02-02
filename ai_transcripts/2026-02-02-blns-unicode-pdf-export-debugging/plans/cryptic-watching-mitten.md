# Plan: Fix E2E Test Isolation - Reset CRDT State Between Tests

## Problem

E2E tests fail when run in sequence but pass when run individually. The 8th test times out on `page.goto()` because accumulated CRDT state from previous tests slows down rendering.

**Root cause:** The `reset_crdt_state` fixture is **session-scoped** (runs once at start), but tests create highlights that persist in CRDT state. The `_delete_all_cards()` cleanup only removes UI elements, not the underlying CRDT document data.

## Solution

Change `reset_crdt_state` from session-scoped to **function-scoped** so CRDT state is reset before each test.

## Files to Modify

### 1. [tests/conftest.py](tests/conftest.py)

Change the fixture scope from `session` to `function`:

```python
@pytest.fixture(scope="function")  # Changed from "session"
def reset_crdt_state(app_server: str) -> Generator[None]:
    """Reset CRDT state before each test."""
    import urllib.request

    reset_url = f"{app_server}/api/test/reset-crdt"
    try:
        with urllib.request.urlopen(reset_url, timeout=5) as resp:
            if resp.status != 200:
                pytest.fail(f"Failed to reset CRDT state: {resp.status}")
    except Exception as e:
        pytest.fail(f"Failed to reset CRDT state: {e}")

    yield
    # No cleanup needed - next test will reset
```

### 2. [tests/e2e/test_live_annotation.py](tests/e2e/test_live_annotation.py)

Simplify `clean_page` fixture since CRDT reset now happens per-test:

```python
@pytest.fixture
def clean_page(
    page: Page, live_annotation_url: str, reset_crdt_state: None
) -> Generator[Page]:
    """Navigate to live annotation page with clean CRDT state."""
    _ = reset_crdt_state  # Ensures CRDT is reset before this test
    page.goto(live_annotation_url)
    doc_container = page.locator(".doc-container")
    expect(doc_container).to_be_visible(timeout=10000)
    yield page
    # No cleanup needed - next test will reset CRDT state
```

Remove `_delete_all_cards()` from the teardown since it's redundant when CRDT resets.

## Verification

```bash
# Run all E2E tests - should pass without timeouts
uv run pytest tests/e2e/test_live_annotation.py -v

# Run multiple times to ensure consistency
uv run pytest tests/e2e/test_live_annotation.py -v --count=2
```

## Trade-offs

- **Pro:** Complete isolation - each test starts with truly clean state
- **Pro:** Simpler - no need for careful UI cleanup in teardown
- **Con:** Slightly slower - HTTP call to reset endpoint before each test
- **Mitigation:** Reset is fast (~10ms), much faster than cleaning up accumulated highlights

## Alternative Considered

Keep session-scoped reset but improve `_delete_all_cards()` to also clear CRDT state via JavaScript. Rejected because:
1. More complex - requires exposing CRDT internals to browser
2. Error-prone - if cleanup fails, subsequent tests fail
3. Function-scoped reset is the idiomatic pytest approach for test isolation
