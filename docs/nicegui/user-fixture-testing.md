---
source: https://nicegui.io/documentation/user
fetched: 2026-02-17
library: nicegui
version: 3.6.1 (pinned)
summary: NiceGUI User fixture for fast headless page testing without a browser
---

# NiceGUI User Fixture Testing

NiceGUI provides a built-in `User` fixture for **fast, headless** page-level testing without a real browser. This runs in-process using HTTPX+ASGI transport — no subprocess, no Playwright, no Selenium.

## Setup

Register the pytest plugin in `conftest.py`:

```python
pytest_plugins = ['nicegui.testing.user_plugin']
```

Or via pyproject.toml:

```toml
[tool.pytest.ini_options]
main_file = "main.py"  # your NiceGUI entry point
```

The `user_plugin` provides two fixtures:
- `user` — a single simulated user
- `create_user` — factory for additional users (multi-user tests)

## Core API

### User class

```python
async def test_example(user: User) -> None:
    # Navigate to a page
    await user.open('/')

    # Assert element visibility (retries 3x with 0.1s delay)
    await user.should_see('Submit')
    await user.should_not_see('Error')

    # Find and interact with elements
    user.find(ui.Button).click()
    user.find('Submit').click()       # find by content text
    user.find(marker='my-id').click() # find by marker

    # Type into inputs
    user.find(ui.Input).type('hello')

    # Trigger arbitrary events
    user.find(ui.Button).trigger('mouseover')
```

### Finding elements

`user.find()` returns a `UserInteraction` wrapping an `ElementFilter`:

```python
# By NiceGUI type
user.find(ui.Button)
user.find(ui.Input)
user.find(ui.Select)

# By content text
user.find('Submit')
user.find('Welcome')

# By marker (set via .mark())
user.find(marker='save-btn')

# By kind + content
user.find(kind=ui.Label, content='Hello')

# Combined
user.find(kind=ui.Button, marker='submit', content='Save')
```

### UserInteraction methods

```python
.click()     # Click the element
.type(text)  # Type text into an input
.clear()     # Clear an input
.trigger(event, args=None)  # Fire arbitrary JS event
```

### Assertions

```python
# should_see / should_not_see accept same args as find()
await user.should_see('Welcome')
await user.should_see(ui.Button)
await user.should_see(marker='my-marker')
await user.should_see(kind=ui.Label, content='Hello')
await user.should_not_see('Error')

# Custom retries
await user.should_see('Loaded', retries=10)
```

### Multiple users

```python
async def test_multi_user(user: User, create_user) -> None:
    user2 = create_user()
    await user.open('/')
    await user2.open('/')

    # Each user has independent state
    user.find(ui.Input).type('hello')
    await user2.should_not_see('hello')  # if not synced
```

### JavaScript simulation

The User fixture does NOT execute real browser JavaScript. Instead, it provides a regex-based rule system:

```python
import re

async def test_with_js(user: User) -> None:
    # Register a JS simulation rule
    user.javascript_rules[re.compile(r'getComputedStyle.*')] = lambda m: '16px'
    await user.open('/')
```

Built-in rule: `__IS_DRAWER_OPEN__` always returns `True`.

### Downloads

```python
async def test_download(user: User) -> None:
    await user.open('/')
    user.find(ui.Button).click()
    # Access download via user.download
```

### Navigation

```python
async def test_nav(user: User) -> None:
    await user.open('/page1')
    # Navigate programmatically
    user.navigate.to('/page2')
    await user.should_see('Page 2')
```

## How It Works Internally

1. `user_simulation()` context manager:
   - Resets NiceGUI global state
   - Sets `NICEGUI_USER_SIMULATION=true` env var
   - Loads the main file via `runpy.run_path()` OR calls `ui.run(root)`
   - Creates `httpx.AsyncClient` with `ASGITransport(core.app)`
   - Yields a `User` wrapping that client

2. `user.open(path)`:
   - HTTP GET via HTTPX (in-process, no network)
   - Extracts `client_id` from response HTML
   - Calls `_on_handshake()` to simulate WebSocket connection
   - Patches outbox emit for JS simulation

3. Element queries go through NiceGUI's `ElementFilter` against the server-side element tree — no DOM, no browser.

## Limitations

- **No real JavaScript execution** — CSS Highlight API, custom JS, `page.evaluate()` equivalents won't work
- **No real DOM** — tests query the server-side element tree, not rendered HTML
- **No real WebSocket** — handshake is simulated
- **No visual rendering** — can't test CSS, layout, or screenshot
- **No clipboard, drag-and-drop, or mouse coordinates** — these need Playwright

## When to Use User vs Playwright

| Scenario | Use User | Use Playwright |
|----------|----------|----------------|
| Button click → state change | Yes | Overkill |
| Form fill → validation | Yes | Overkill |
| Dialog open/close | Yes | Overkill |
| Navigation between pages | Yes | Overkill |
| Download triggered | Yes | Overkill |
| Multi-user state sync (server-side) | Yes | Overkill |
| CSS Highlight API | No | Required |
| Text selection (mouse drag) | No | Required |
| JavaScript execution | No | Required |
| Visual regression / screenshots | No | Required |
| Copy protection (clipboard) | No | Required |

## See Also

- [NiceGUI Playwright E2E patterns](testing.md) - Subprocess server approach
- [Source: nicegui.testing.user](https://nicegui.io/documentation/user)
- [Source: nicegui.testing.user_plugin](source code in installed package)
