---
source: https://playwright.dev/python/docs/intro
fetched: 2025-01-14
summary: Playwright Python E2E testing with pytest
---

# Playwright E2E Testing (Python)

Playwright enables reliable end-to-end testing for web applications.

## Installation

```bash
pip install pytest-playwright
playwright install
```

Or with uv:

```bash
uv add --dev pytest-playwright
uv run playwright install
```

## Writing Tests

Create test files with `test_` prefix (e.g., `tests/e2e/test_login.py`):

```python
import re
from playwright.sync_api import Page, expect

def test_has_title(page: Page):
    page.goto("https://example.com/")
    expect(page).to_have_title(re.compile("Example"))

def test_login_flow(page: Page):
    page.goto("https://example.com/login")
    page.get_by_label("Email").fill("test@example.com")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Welcome")).to_be_visible()
```

## Core Fixtures

pytest-playwright provides:

- **`page`**: Fresh browser page per test (function scope)
- **`context`**: New browser context per test
- **`browser`**: Browser instance (session scope)
- **`new_context`**: Factory for multi-user scenarios

## Locators

Find elements using accessible attributes:

```python
# By role (preferred)
page.get_by_role("button", name="Submit")
page.get_by_role("link", name="Get started")
page.get_by_role("heading", name="Welcome")

# By text
page.get_by_text("Welcome")

# By label (form fields)
page.get_by_label("Username")
page.get_by_label("Password")

# By placeholder
page.get_by_placeholder("Search...")

# By test ID
page.get_by_test_id("submit-btn")

# CSS selector (fallback)
page.locator("#submit-button")
page.locator(".card >> text=Title")
```

## Actions

```python
# Click
page.get_by_role("button").click()

# Fill input (clears first)
page.get_by_label("Email").fill("test@example.com")

# Type character by character
page.locator("input").type("text")

# Select dropdown
page.locator("select").select_option("value")

# Check/uncheck
page.get_by_label("Accept terms").check()
```

## Assertions

Web-first assertions auto-wait:

```python
from playwright.sync_api import expect

# Visibility
expect(page.get_by_text("Success")).to_be_visible()
expect(page.locator(".spinner")).to_be_hidden()

# Text content
expect(page.locator("h1")).to_have_text("Dashboard")
expect(page.locator("p")).to_contain_text("welcome")

# Input values
expect(page.get_by_label("Email")).to_have_value("test@example.com")

# Page state
expect(page).to_have_title("Dashboard")
expect(page).to_have_url("**/dashboard")
```

## Waiting

```python
# Wait for element state
page.locator(".loading").wait_for(state="hidden")

# Wait for URL
page.wait_for_url("**/dashboard")

# Wait for JavaScript condition
page.wait_for_function("() => window.appReady === true")

# Wait for network
with page.expect_request("**/api/data") as request_info:
    page.get_by_text("Load").click()
```

## JavaScript Evaluation

```python
# Get value from page
title = page.evaluate("document.title")

# Execute function
result = page.evaluate("() => localStorage.getItem('token')")

# Pass arguments
doubled = page.evaluate("x => x * 2", 21)
```

## Running Tests

```bash
# Run all E2E tests
pytest tests/e2e/

# Headed mode (see browser)
pytest --headed

# Specific browser
pytest --browser firefox
pytest --browser webkit

# Slow motion for debugging
pytest --slowmo 500

# Screenshots on failure
pytest --screenshot only-on-failure

# Record traces
pytest --tracing retain-on-failure

# Parallel execution
pip install pytest-xdist
pytest --numprocesses auto
```

## Configuration (pytest.ini)

```ini
[pytest]
addopts = --headed --browser chromium
```

## Fixture Customization

```python
# conftest.py
import pytest

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,
    }
```

## Multi-User Testing

```python
def test_collaboration(page: Page, new_context):
    # User 1
    page.goto("https://example.com/doc/123")

    # User 2 in separate context
    context2 = new_context()
    page2 = context2.new_page()
    page2.goto("https://example.com/doc/123")

    # Test real-time sync between users
    page.get_by_label("Title").fill("New Title")
    expect(page2.get_by_label("Title")).to_have_value("New Title")
```

## Debugging

```python
def test_debug(page: Page):
    page.goto("https://example.com")
    breakpoint()  # Pauses for pdb inspection
```

## Complete Example: NiceGUI App Test

```python
import pytest
from playwright.sync_api import Page, expect

@pytest.fixture(scope="module")
def app_url():
    # Start your NiceGUI app and return URL
    return "http://localhost:8080"

def test_annotation_flow(page: Page, app_url):
    # Navigate to app
    page.goto(app_url)

    # Login
    page.get_by_label("Email").fill("test@example.com")
    page.get_by_role("button", name="Sign in").click()

    # Wait for dashboard
    expect(page).to_have_url("**/dashboard")

    # Select conversation
    page.get_by_text("My Conversation").click()

    # Verify content loaded
    expect(page.get_by_role("article")).to_be_visible()

    # Make annotation (simulate text selection)
    page.evaluate("""
        const range = document.createRange();
        const text = document.querySelector('.conversation-text');
        range.selectNodeContents(text.firstChild);
        window.getSelection().addRange(range);
    """)

    # Click annotate button
    page.get_by_role("button", name="Annotate").click()

    # Verify annotation created
    expect(page.locator(".annotation-highlight")).to_be_visible()
```
