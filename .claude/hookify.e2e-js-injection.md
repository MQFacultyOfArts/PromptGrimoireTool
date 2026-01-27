---
name: e2e-js-injection
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: tests?/(e2e|playwright|integration)/.*\.(py|ts|js)$
  - field: new_text
    operator: regex_match
    pattern: page\.evaluate\(|ui\.run_javascript\(|page\.add_script_tag\(
action: warn
---

**E2E JavaScript Injection Detected**

Per CLAUDE.md: **NEVER inject JavaScript in E2E tests.**

Use Playwright's native APIs instead:
- **Text selection**: `page.mouse` to drag-select (move, down, move, up)
- **Keyboard input**: `page.keyboard.press()` or `locator.press()`
- **Clicks**: `locator.click()` with modifiers
- **Assertions**: `expect()` from `playwright.sync_api`
- **Scroll**: `locator.scroll_into_view_if_needed()`

Tests must simulate real user behavior through Playwright events, not bypass the UI with JavaScript injection.
