# Rodney CLI Reference

Source: `simonw/rodney` (`main.go` at commit `9e7ae93`). Go binary wrapping `go-rod/rod` for shell-friendly Chrome DevTools Protocol automation.

Cached: 2026-02-27

## Session Management

```bash
rodney start --local          # Start a local browser session
rodney stop --local           # Stop the local browser session
rodney start --global         # Start a global (shared) browser session
rodney stop --global          # Stop the global browser session
```

Sessions are either `--local` (per-terminal) or `--global` (shared). All subsequent commands require `--local` or `--global` to identify which session.

## Navigation

```bash
rodney open --local <url>     # Navigate to URL
```

## Waiting

### Element-level waits

```bash
rodney wait --local <selector>
```

**Two-stage wait**: First `page.Element(selector)` polls for DOM existence (up to timeout), then `MustWaitVisible()` waits for CSS visibility. Prints "Element visible" on success. Exit 2 on timeout.

### Page-level waits

```bash
rodney waitload --local       # Wait for browser 'load' event (DOM + subresources)
rodney waitstable --local     # Wait for DOM to stop changing (no reflows/repaints)
rodney waitidle --local       # Wait for network idle (zero outstanding requests)
```

No selector argument. These are page-level conditions.

### Sleep

```bash
rodney sleep <seconds>        # Explicit sleep. Accepts float (e.g., 0.5 for 500ms)
```

Process-level sleep, no browser interaction.

## Interaction

### Click

```bash
rodney click --local <selector>
```

`page.Element(selector)` waits for DOM existence (up to timeout), then `el.Click()` clicks at element centre. Does **NOT** wait for CSS visibility. 100ms post-click sleep hardcoded.

### Input

```bash
rodney input --local <selector> <text...>
```

`page.Element(selector)` waits for DOM existence, then `MustSelectAllText().MustInput(text)` — **clears existing content first**, then types with real keyboard events (keydown/keypress/input/keyup per character via CDP). Multiple text arguments joined with spaces.

### Clear

```bash
rodney clear --local <selector>
```

Select all text and replace with empty string.

### Key

```bash
rodney key --local <key>
```

Dispatch keyboard event. Examples: `"Enter"`, `"Control+v"`, `"Tab"`.

## JavaScript

```bash
rodney js --local <expression...>
```

Expression wrapped in `() => { return (%s); }` and evaluated via `Runtime.evaluate`. Returns typed output:
- `null`/`undefined`: printed literally
- Booleans: `true`/`false`
- Strings: printed unquoted
- Objects/arrays: pretty-printed JSON (2-space indent)
- Numbers: printed as-is

Multiple arguments joined with spaces. Not natively async but rod handles Promise returns.

## Screenshots

```bash
rodney screenshot --local [-w <width>] [-h <height>] [filename]
```

- `-w <N>`: viewport width (default 1280)
- `-h <N>`: viewport height (default 720). When `-h` is NOT provided, captures **full page** (scrollable). When provided, captures viewport only.
- `[filename]`: output path (default: auto-numbered `screenshot.png`, `screenshot-2.png`, etc.)

```bash
rodney screenshot-el --local <selector> [filename]
```

Captures only the element's bounding box. Default filename: `element.png`.

## Element Checks

### exists (instant, no wait)

```bash
rodney exists --local <selector>
```

Uses `page.Has()` — **instant** DOM query, no polling. Prints `true`/`false`. Exit 0 if exists, exit 1 if not.

### visible (waits for existence, instant visibility check)

```bash
rodney visible --local <selector>
```

`page.Element(selector)` **waits** up to timeout for DOM existence, then instant `el.Visible()` check. Prints `true`/`false`. Exit 0 if visible, exit 1 if not found or not visible.

### count (instant, no wait)

```bash
rodney count --local <selector>
```

Uses `page.Elements()` — instant query. Prints integer count. **Always exits 0** (even for count 0).

### assert

```bash
rodney assert --local <js-expression> [expected-value]
```

Evaluates JS expression. Without expected value: exit 0 if truthy, exit 1 if falsy. With expected value: exit 0 if equal, exit 1 if not.

## Timeout Configuration

**Default timeout**: 30 seconds for all wait operations.

**Override**: Set `ROD_TIMEOUT` environment variable (float, in seconds):

```bash
ROD_TIMEOUT=15 rodney wait --local '[data-testid="my-element"]'
```

Applied globally — no per-command timeout flag.

**Timeout applies to**: `wait`, `click` (element finding), `input` (element finding), `visible` (element finding), `waitload`, `waitstable`, `waitidle`.

**Not affected**: `exists` (instant), `count` (instant), `sleep` (explicit duration).

## Exit Codes

| Code | Meaning | Commands |
|------|---------|----------|
| 0 | Success | All commands on success |
| 1 | Check failed | `exists`, `visible`, `assert`, `ax-find` |
| 2 | Error (timeout, bad args, no browser) | All commands on error. `fatal()` always exits 2. |

## NiceGUI Integration Notes

NiceGUI updates DOM via WebSocket pushes after server-side Python executes. Key implications:

1. **`rodney wait` handles NiceGUI timing** — its `page.Element()` polling naturally waits for elements pushed via WebSocket. Empirically verified against live NiceGUI app.

2. **`rodney click` waits for DOM existence** — after a NiceGUI action that creates new elements, the next `rodney click` on those elements will wait up to 30s for them to appear.

3. **`waitstable` catches batch updates** — after NiceGUI pushes multiple DOM changes, `waitstable` waits for reflows to settle.

4. **Genuine delays need `sleep`** — operations like LaTeX PDF export or clipboard processing have real-time delays that no DOM polling can short-circuit. Use `rodney sleep` for these.

5. **`waitload` is for full page navigations only** — within a NiceGUI SPA, route changes don't fire browser `load` events. Use `rodney wait` for a target element instead.
