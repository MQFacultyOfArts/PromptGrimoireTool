---
source: https://nicegui.io/documentation/section_configuration_deployment
fetched: 2026-03-05
library: nicegui
version: "3.8.0"
summary: ui.run() parameters, environment variables, native mode configuration
---

# NiceGUI Configuration

## ui.run() Parameters

The `ui.run()` function accepts optional arguments for server and UI configuration. Most arguments apply after a full restart, not with auto-reloading.

### Core Settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `root` | function | None | Root page function (v3.0.0+) |
| `host` | str | `'0.0.0.0'` | Server hostname (`'127.0.0.1'` in native mode) |
| `port` | int | 8080 | Port number (auto-assigned in native mode) |
| `title` | str | `'NiceGUI'` | Page title (overridable per page) |
| `viewport` | str | `'width=device-width, initial-scale=1'` | Meta viewport content |
| `favicon` | str | None | Relative filepath, absolute URL, or emoji |

### Styling & Display

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dark` | bool\|None | False | Quasar dark mode (None = auto) |
| `language` | str | `'en-US'` | Quasar language |
| `tailwind` | bool | True | Enable Tailwind CSS (experimental) |
| `unocss` | str\|None | None | UnoCSS preset: `"mini"`, `"wind3"`, `"wind4"` |
| `prod_js` | bool | True | Production Vue/Quasar versions |

### Performance & Caching

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `binding_refresh_interval` | float\|None | 0.1 | Active link update interval (None disables) |
| `reconnect_timeout` | float | 3.0 | Browser reconnection window (seconds) |
| `message_history_length` | int | 1000 | Messages stored for reconnection (0 disables) |
| `cache_control_directives` | str | `'public, max-age=31536000, immutable, stale-while-revalidate=31536000'` | Static file cache headers |
| `gzip_middleware_factory` | callable\|None | GZipMiddleware | Custom GZip config (None disables) |

### Storage & Security

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `storage_secret` | str | None | Browser storage encryption key. **Required** for `app.storage.user` and `app.storage.browser` |
| `session_middleware_kwargs` | dict | None | Additional `SessionMiddleware` parameters |

### Documentation & API

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fastapi_docs` | bool\|dict | False | Enable Swagger/ReDoc/OpenAPI |
| `endpoint_documentation` | str | `'none'` | OpenAPI doc scope: `'none'`, `'internal'`, `'page'`, `'all'` |

### Development & Reloading

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `reload` | bool | True | Auto-reload on file changes |
| `uvicorn_logging_level` | str | `'warning'` | Server logging verbosity |
| `uvicorn_reload_dirs` | str | cwd | Comma-separated monitored directories |
| `uvicorn_reload_includes` | str | `'*.py'` | Glob patterns triggering reload |
| `uvicorn_reload_excludes` | str | `'.*, .py[cod], .sw.*, ~*'` | Ignored glob patterns |

### Native & Window Mode

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `native` | bool | False | Open in native window (800x600) |
| `window_size` | tuple | None | Native window dimensions, e.g. `(1024, 786)` |
| `fullscreen` | bool | False | Fullscreen window (activates native) |
| `frameless` | bool | False | Frameless window (activates native) |
| `show` | bool\|str | True | Auto-open browser tab (accepts specific paths) |
| `on_air` | bool | False | Tech preview: temporary remote access |
| `show_welcome_message` | bool | True | Display welcome notification |
| `kwargs` | dict | None | Extra arguments passed to `uvicorn.run()` |

### Example

```python
from nicegui import ui

ui.label('page with custom title')
ui.run(title='My App', port=8080, dark=True)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MATPLOTLIB` | `true` | Set `false` to skip Matplotlib import (disables `ui.pyplot`, `ui.line_plot`) |
| `NICEGUI_STORAGE_PATH` | `.nicegui` | Custom location for storage files |
| `MARKDOWN_CONTENT_CACHE_SIZE` | 1000 | Markdown snippet cache limit |
| `RST_CONTENT_CACHE_SIZE` | 1000 | ReStructuredText snippet cache limit |
| `NICEGUI_REDIS_URL` | None | Redis server URL for distributed/shared storage |
| `NICEGUI_REDIS_KEY_PREFIX` | `nicegui:` | Redis key namespace prefix |

## Native Mode Configuration

Native mode launches applications in standalone windows using pywebview.

### Configuration Objects

- **`app.native.window_args`** — customise `webview.create_window` parameters:
  ```python
  app.native.window_args['resizable'] = False
  ```

- **`app.native.start_args`** — control startup behaviour:
  ```python
  app.native.start_args['debug'] = True
  ```

- **`app.native.settings`** — modify webview behaviour:
  ```python
  app.native.settings['ALLOW_DOWNLOADS'] = True
  ```

- **`app.native.main_window`** — async wrapper for runtime window control:
  ```python
  app.native.main_window.resize(1000, 700)
  ```

**Important:** Configuration changes within `if __name__ == '__main__'` blocks are ignored since native apps run in separate processes. Place configuration outside this guard.

## Storage Types

NiceGUI provides five built-in storage types:

| Storage | Scope | Persistence | Notes |
|---------|-------|-------------|-------|
| `app.storage.tab` | Per tab | In-memory (lost on restart) | Requires `await client.connected()` |
| `app.storage.client` | Per connection | In-memory (lost on reload) | For short-lived/sensitive data |
| `app.storage.user` | Per user (all tabs) | Server-side file/Redis | Requires `storage_secret` |
| `app.storage.general` | All users | Server-side file/Redis | Shared global state |
| `app.storage.browser` | Per browser (all tabs) | Session cookie | Requires `storage_secret`; less preferred than `.user` |

### Storage Integration with Bindings

```python
element.bind_value(app.storage.user, 'key')  # persists UI state across visits
```

### Configuration

- `app.storage.max_tab_storage_age` — max age for tab storage (default: 30 days)
- Redis storage enabled via `NICEGUI_REDIS_URL` environment variable
