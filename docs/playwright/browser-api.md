---
source: https://playwright.dev/python/docs/api/class-browser
fetched: 2026-01-23
library: playwright
summary: Browser class API for multi-context testing
---

# Browser API

A `Browser` is created via `browserType.launch()`. Browser contexts isolate sessions and each context can have multiple pages.

## Usage

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://example.com")
    browser.close()
```

## Methods

### browser.close()

Closes the browser and all pages. Browser object is no longer usable after this call.

```python
browser.close()
```

### browser.contexts

Returns all open browser contexts (list):

```python
contexts = browser.contexts  # List[BrowserContext]
```

### browser.is_connected()

Check if browser is connected:

```python
if browser.is_connected():
    # Browser still active
```

### browser.new_context(**kwargs)

Creates a new browser context. **Key method for multi-user testing.**

Contexts don't share cookies/cache, providing complete isolation between users.

```python
context = browser.new_context()
```

**Common parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `viewport` | `dict` | `{"width": 1280, "height": 720}` |
| `ignore_https_errors` | `bool` | Ignore SSL errors |
| `java_script_enabled` | `bool` | Enable/disable JS |
| `locale` | `str` | e.g. `"en-US"` |
| `timezone_id` | `str` | e.g. `"America/New_York"` |
| `geolocation` | `dict` | `{"latitude": 0, "longitude": 0}` |
| `permissions` | `list` | e.g. `["geolocation"]` |
| `color_scheme` | `str` | `"dark"` or `"light"` |
| `storage_state` | `str/dict` | Load cookies/localStorage from file |
| `http_credentials` | `dict` | `{"username": "", "password": ""}` |
| `device_scale_factor` | `float` | Device pixel ratio |
| `is_mobile` | `bool` | Mobile emulation |
| `has_touch` | `bool` | Touch events support |
| `user_agent` | `str` | Custom UA string |
| `proxy` | `dict` | Proxy settings |
| `record_video_dir` | `str` | Path for video recording |
| `record_video_size` | `dict` | `{"width": 1280, "height": 720}` |

**Full example:**

```python
context = browser.new_context(
    viewport={"width": 1920, "height": 1080},
    ignore_https_errors=True,
    locale="en-US",
    timezone_id="America/New_York",
    color_scheme="dark",
)
```

### browser.new_page(**kwargs)

Shortcut that creates a new context with one page:

```python
page = browser.new_page()  # Creates context + page
```

Equivalent to:

```python
context = browser.new_context()
page = context.new_page()
```

**Important:** When using `browser.new_page()`, calls to `context.close()` will close the page.

### browser.start_tracing(**kwargs)

Start tracing for debugging (Chromium only):

```python
browser.start_tracing(page=page, path="trace.json", screenshots=True)
# ... do stuff ...
browser.stop_tracing()
```

### browser.stop_tracing()

Stop tracing and return trace data:

```python
trace = browser.stop_tracing()
```

### browser.version

Returns browser version string:

```python
print(browser.version)  # e.g. "120.0.6099.109"
```

## Events

### browser.on("disconnected")

Fired when browser disconnects (crash, close, `browser.close()`):

```python
browser.on("disconnected", lambda: print("Browser closed"))
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `browser_type` | `BrowserType` | The browser type (chromium, firefox, webkit) |
| `contexts` | `List[BrowserContext]` | All open contexts |
| `version` | `str` | Browser version string |

## Multi-User Testing Pattern

For E2E tests simulating multiple users, create separate browser contexts:

```python
from playwright.sync_api import Browser, Page, expect

def test_two_users_collaborate(browser: Browser):
    # User 1 - first browser context
    context1 = browser.new_context()
    page1 = context1.new_page()
    page1.goto("https://example.com/doc")

    # User 2 - separate browser context (isolated session)
    context2 = browser.new_context()
    page2 = context2.new_page()
    page2.goto("https://example.com/doc")

    # They have separate cookies, localStorage, etc.
    # Server sees them as different users

    # Test collaboration
    page1.get_by_label("Title").fill("Hello from User 1")
    expect(page2.get_by_text("Hello from User 1")).to_be_visible()

    # Cleanup
    context1.close()
    context2.close()
```

**Why separate contexts matter:**
- Two pages in the same context share cookies/session
- Server may count them as one user
- For true multi-user testing, use `browser.new_context()` for each user

## pytest-playwright Integration

With pytest-playwright, use the `browser` fixture:

```python
import pytest
from playwright.sync_api import Browser, BrowserContext, Page

def test_multi_user(browser: Browser):
    context1 = browser.new_context()
    context2 = browser.new_context()
    # ... test code ...
    context1.close()
    context2.close()
```

Or create a fixture factory:

```python
# conftest.py
@pytest.fixture
def new_context(browser: Browser):
    """Factory for creating isolated browser contexts."""
    contexts: list[BrowserContext] = []

    def _new_context(**kwargs) -> BrowserContext:
        ctx = browser.new_context(**kwargs)
        contexts.append(ctx)
        return ctx

    yield _new_context

    # Cleanup all contexts after test
    for ctx in contexts:
        ctx.close()

# test file
def test_collaboration(new_context):
    context1 = new_context()
    context2 = new_context()
    page1 = context1.new_page()
    page2 = context2.new_page()
    # ... test with automatic cleanup
```

## Element Visibility

When elements might be off-screen, use `scroll_into_view_if_needed()`:

```python
element = page.locator('[data-id="item-500"]')
element.scroll_into_view_if_needed()
expect(element).to_be_visible()
element.click()
```

## Color Format Note

Browsers convert CSS hex colors to RGB format. When asserting styles:

```python
# HTML/CSS: background-color: #1f77b4
# Browser reports: rgb(31, 119, 180)

style = element.get_attribute("style")
assert "rgb(31, 119, 180)" in style  # Use RGB, not hex
```
