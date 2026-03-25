# NiceGUI Layout & Viewport: Lessons from the Roleplay Page

**Date:** 2026-03-25
**Context:** Issue #289 — roleplay page viewport fixes

## The Flex Chain Problem

NiceGUI + Quasar inserts wrapper divs between your Python layout code and the final DOM. A full-height flex layout requires every element in the chain from `.q-page` down to your content to participate in flex sizing. If any wrapper breaks the chain, content collapses to intrinsic height.

### The chain (roleplay page)

```
.q-page                    — Quasar sets min-height via inline style (JS, dynamic on resize)
  .nicegui-content         — NiceGUI wrapper, defaults to flex: 0 1 auto (BREAKS chain)
    your layout divs       — must propagate flex: 1 + min-height: 0
      .q-card              — must be flex column with flex: 1
        .q-scrollarea      — Quasar scroll area, needs bounded parent height
```

### Fix: force `.nicegui-content` to stretch

```css
.q-page > .nicegui-content {
    flex: 1 !important;
    display: flex !important;
    flex-direction: column !important;
    min-height: 0 !important;
}
```

This is required on every page that needs full-height flex layout. Without it, `.nicegui-content` has `flex: 0 1 auto` and the chain breaks.

### `.q-page` min-height is dynamic

Quasar sets `min-height` on `.q-page` as an **inline style** via JavaScript: `style="min-height: 732px"`. This updates dynamically on window resize. It equals `viewport height - header height`. The flex chain below it responds automatically — no JS needed for resize handling.

## `ui.row()` and `ui.column()` Add Wrapper Divs

`ui.row()` generates a `<div class="nicegui-row row ...">`. `ui.column()` generates `<div class="nicegui-column ...">`. These are the actual DOM elements.

**However:** in some contexts NiceGUI may add additional wrapper divs. When building layout-critical flex chains, prefer `ui.element('div')` with explicit styling to avoid unexpected wrappers:

```python
# Instead of ui.row() which may add wrappers:
with ui.element("div").style(
    "flex: 1; min-height: 0; display: flex;"
    " flex-wrap: nowrap; align-items: stretch;"
):
    ...
```

In practice, `ui.column()` and `ui.row()` worked fine for the roleplay layout — but if you hit mysterious flex chain breaks, check for extra wrapper divs.

## `ui.scroll_area()` (QScrollArea) Needs a Bounded Parent

Quasar's `QScrollArea` doesn't scroll unless its parent has a bounded height. The scroll area itself should have:

```css
.my-scroll-area {
    flex: 1 !important;
    min-height: 0 !important;
}
```

The `min-height: 0` is critical — without it, the flex item's minimum size is its content height, which prevents scrolling.

### Scroll-to-bottom timing

`scroll_area.scroll_to(percent=1.0)` fires server-side immediately, but the browser hasn't laid out new elements yet. Use a deferred timer:

```python
ui.timer(0.1, lambda: scroll_area.scroll_to(percent=1.0), once=True)
```

## Chat Message Styling

### Use `text_html=True`, not child elements

```python
# WRONG — bypasses Quasar's bubble structure:
msg = ui.chat_message(name=name, sent=sent, avatar=avatar)
with msg:
    ui.markdown(content)

# RIGHT — Quasar handles bubble structure and alignment:
ui.chat_message(text=html, name=name, sent=sent, avatar=avatar, text_html=True)
```

When using `text_html=True`, Quasar renders content directly inside `.q-message-text--sent` / `.q-message-text--received`. There is **no** `.q-message-text-content` wrapper. CSS targeting `.q-message-text-content` will have no effect.

When using child elements (the `with msg:` pattern), Quasar creates `.q-message-text-content` as a wrapper. Both approaches generate different DOM — don't mix CSS assumptions between them.

### Quasar specificity wars

Quasar applies chat message colours with high specificity. An external stylesheet often can't win. Use inline `<style>` blocks with `!important`:

```python
ui.add_head_html("""<style>
    .roleplay-chat .q-message-text--received {
        background: rgba(80, 80, 80, 0.5) !important;
        color: rgb(220, 220, 210) !important;
    }
</style>""")
```

**Inheritance vs direct application:** `color: rgb(X) !important` on a parent element overrides inherited colour on children — even if the child has a CSS rule without `!important`. To override, the child's rule also needs `!important`:

```css
/* Parent sets colour with !important */
.q-message-text--received { color: rgb(220, 220, 210) !important; }

/* Child em/i needs !important too to override inherited colour */
.q-message em { color: rgb(225, 180, 100) !important; }
```

## Background Layering

Avoid stacking semi-transparent backgrounds on nested elements — creates a visible "box-in-box" effect:

```css
/* BAD — card at 0.75 + scroll area at 0.85 = nested dark rectangles */
.card { background: rgba(23, 23, 23, 0.75); }
.scroll-area { background: rgba(23, 23, 23, 0.85); }

/* GOOD — one background on the card, scroll area transparent */
.card { background: rgba(23, 23, 23, 0.75); }
.scroll-area { background: transparent; }
```

## Responsive Sidebar Pattern

Two-panel layout (sidebar + main content) where sidebar hides on narrow viewports:

**Python:** Build both sidebar and narrow header. CSS toggles visibility.

```python
# Sidebar — visible on wide viewports
_build_char_panel(widgets, management_drawer)

# Inside chat card — narrow header, hidden on wide viewports
_build_chat_header(widgets, management_drawer)
```

**CSS:**

```css
/* Narrow header hidden by default */
.narrow-header { display: none !important; }

/* At breakpoint: hide sidebar, show narrow header */
@media (max-width: 1024px) {
    .sidebar { display: none !important; }
    .narrow-header { display: flex !important; }
}
```

**Duplicated controls** (settings cog, finish button in both sidebar and header): store as a list and iterate on state changes:

```python
finish_btns = [widgets["sidebar_finish_btn"], widgets["header_finish_btn"]]
for btn in finish_btns:
    btn.disable()
```

## Debugging Tools

### Screenshot script with mock chat

`scripts/screenshot_page.py` takes Playwright screenshots against the running dev server:

```bash
uv run scripts/screenshot_page.py /roleplay --chat --output /tmp/test.png
uv run scripts/screenshot_page.py /roleplay --width 800 --height 600  # narrow viewport
uv run scripts/screenshot_page.py /roleplay --inspect  # flex chain diagnostics
```

`--chat` clicks the "Mock Chat" button (dev mode only) to inject conversation turns without hitting the LLM.

### Dev-mode buttons (sidebar, `DEV__AUTH_MOCK=true` only)

- **Mock Chat** — injects 3 mock turns via `Session.add_turn()`, re-renders through `_render_messages()`
- **Angry Becky** — injects 7 turns of a full interview + triggers the completion flow

### DOM chain inspection

When the flex chain breaks, dump the ancestor chain from your target element up to `.q-page`:

```javascript
// In browser console or Playwright evaluate:
let el = document.querySelector('.your-element');
while (el && el !== document.body) {
    const cs = getComputedStyle(el);
    console.log(el.className.substring(0, 50),
        'display:', cs.display, 'flex:', cs.flex,
        'h:', el.offsetHeight, 'minH:', cs.minHeight);
    el = el.parentElement;
}
```

Every element in the chain must have `flex: 1` (or explicit sizing) and `min-height: 0`. One missing link collapses everything below it.

### Playwright headless vs real browser

Playwright headless and real browsers can render differently due to:
- **CSS caching** — hard refresh (Ctrl+Shift+F5) may not bust NiceGUI's asset cache. Use incognito to verify.
- **Browser zoom** — 150% zoom on a 1536px screen = 1024px CSS viewport, which hits media query breakpoints.
- **Font rendering** — affects text wrapping and element heights.

When Playwright and the real browser disagree, test in incognito first. If incognito matches Playwright, it's a cache issue.
