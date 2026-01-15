# NiceGUI E2E Testing with Playwright

> **Project Notes**: Lessons learned from PromptGrimoire Spike 1 implementation.

## The Problem

NiceGUI detects pytest and enters a special "test mode" that expects specific environment variables (`NICEGUI_SCREEN_TEST_PORT`, etc.). This breaks normal E2E testing with Playwright because:

1. NiceGUI won't start normally when pytest env vars are present
2. You get errors like `KeyError: 'NICEGUI_SCREEN_TEST_PORT'`

## The Solution

Run the NiceGUI server as a **subprocess** with cleaned environment variables.

### Server Script Pattern

```python
_SERVER_SCRIPT = """
import os
import sys

# Clear pytest-related environment variables that NiceGUI checks
for key in list(os.environ.keys()):
    if 'PYTEST' in key or 'NICEGUI' in key:
        del os.environ[key]

port = int(sys.argv[1])

from nicegui import ui
import your_app.pages  # Import your page modules

ui.run(port=port, reload=False, show=False)
"""
```

### Pytest Fixture

```python
import os
import socket
import subprocess
import sys
import time
from typing import Generator

import pytest


def _find_free_port() -> int:
    """Find an available port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def app_server() -> Generator[str]:
    """Start the NiceGUI app server for E2E tests.

    Returns the base URL of the running server.
    """
    port = _find_free_port()
    url = f"http://localhost:{port}"

    # Create clean environment without pytest variables
    clean_env = {
        k: v for k, v in os.environ.items()
        if "PYTEST" not in k and "NICEGUI" not in k
    }

    # Start server as subprocess with clean environment
    process = subprocess.Popen(
        [sys.executable, "-c", _SERVER_SCRIPT, str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=clean_env,
    )

    # Wait for server to be ready
    max_wait = 15  # seconds
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            pytest.fail(
                f"Server died. Exit: {process.returncode}\n"
                f"stdout: {stdout.decode()}\n"
                f"stderr: {stderr.decode()}"
            )
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                break
        except OSError:
            time.sleep(0.1)
    else:
        process.terminate()
        pytest.fail(f"Server failed to start within {max_wait} seconds")

    yield url

    # Cleanup
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
```

### Multi-User Testing with Browser Contexts

Playwright's `browser.new_context()` creates isolated browser sessions - perfect for simulating multiple users:

```python
@pytest.fixture
def new_context(browser: Browser) -> Generator[Callable[[], BrowserContext]]:
    """Factory fixture for creating new browser contexts."""
    contexts: list[BrowserContext] = []

    def _new_context() -> BrowserContext:
        ctx = browser.new_context()
        contexts.append(ctx)
        return ctx

    yield _new_context

    for ctx in contexts:
        ctx.close()
```

Usage in tests:

```python
def test_two_users_sync(page: Page, new_context, app_url: str):
    """Two users see each other's changes."""
    # User 1 (default page from pytest-playwright)
    page.goto(f"{app_url}/my-page")

    # User 2 (separate browser context = separate session)
    context2 = new_context()
    page2 = context2.new_page()
    page2.goto(f"{app_url}/my-page")

    # Now page and page2 are independent browser sessions
    page.get_by_label("Input").fill("Hello from user 1")
    expect(page2.get_by_test_id("display")).to_have_text("Hello from user 1")
```

## Key Points

1. **Use `scope="session"`** for the server fixture - one server for all tests
2. **Random port** via `_find_free_port()` - avoids conflicts
3. **Clean environment** - strip `PYTEST` and `NICEGUI` vars
4. **Wait for ready** - poll the port before returning
5. **Proper cleanup** - terminate then kill if needed

## Dependencies

```bash
uv add --dev pytest-playwright
uv run playwright install chromium
```

## See Also

- [tests/conftest.py](../../tests/conftest.py) - Working implementation
- [tests/e2e/test_two_tab_sync.py](../../tests/e2e/test_two_tab_sync.py) - Example tests
