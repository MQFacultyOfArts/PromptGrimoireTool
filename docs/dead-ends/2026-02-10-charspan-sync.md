# Dead End: Client-Side Char Span Synchronisation

**Date:** 2026-02-10
**Branch:** `annotation-guards` (tag: `dead-end/charspan-sync-attempt`)
**Status:** Abandoned

## Problem

NiceGUI's "Event listeners changed" mechanism triggers a **full destroy+recreate cycle** on DOM elements when event listeners are registered after initial render. This wipes client-side injected char spans (`<span class="char" data-char-index="N">`), breaking text selection.

The re-render happens because `_setup_selection_handlers()` registers `mouseup`/`selectionchange` listeners on the document AFTER the initial render, which NiceGUI detects and responds to by deleting the element from Vue's reactive data, awaiting `$nextTick()`, and re-adding it. The old DOM element is **replaced entirely** — `isConnected` is `false` on the old element.

## Approaches Tried (All Failed)

### 1. `_charSpansReady` Guard + Awaited Injection

Added a `window._charSpansReady` flag set `false` before injection and `true` after. Guard in `processSelection()` returns early if not ready.

**Why it failed:** The guard prevents selection during injection, but doesn't handle subsequent re-renders. After a highlight is created (cards refresh, CRDT update), NiceGUI re-renders again, wiping spans with no mechanism to re-inject. Also caused a **critical selection regression** — text selection became inaccurate (drag-to-select selected everything to the top of the document).

### 2. MutationObserver on `doc-container`

Watched `doc-container` with `MutationObserver({childList: true, subtree: true})` to detect span wipes and re-inject.

**Why it failed:** NiceGUI's destroy+recreate cycle **replaces the element itself**, not just its children. The observer was attached to the old (now-detached) element and never fired. Confirmed via diagnostic experiment: `isConnected: false`, `_diagMarker: undefined` on the "same" element after re-render.

### 3. Post-Handler Re-injection

After `_setup_selection_handlers()`, sent a `ui.run_javascript()` to re-inject spans. WebSocket FIFO ordering guarantees it runs after the re-render.

**Why it failed:** Only fixes the initial re-render at page load. After highlight creation triggers another re-render, spans are wiped again. First selection worked; second selection failed.

### 4. Self-Healing `processSelection()`

Modified `processSelection()` to detect missing spans and re-inject at point-of-use.

**Why it failed:** `selectionchange` fires continuously during drag. Re-injecting spans (which mutates the DOM by replacing all text nodes with wrapped spans) during an active drag selection breaks the browser's selection tracking, causing the selection to extend to the top of the document.

## Root Cause Analysis

The fundamental problem is that **NiceGUI's Vue-based rendering model and client-side DOM manipulation are architecturally incompatible**. NiceGUI owns the DOM and will destroy+recreate elements at will. Any client-side DOM modifications (char span injection) are ephemeral and will be wiped by the next re-render cycle, with no reliable hook to detect or recover from this.

Attempting to synchronise client-side state with NiceGUI's render cycle is fighting the framework. Each fix created new timing windows or interaction regressions.

## What NOT to Try Again

1. **MutationObserver on any NiceGUI-managed element** — the element itself gets replaced, observers watch dead nodes
2. **Synchronisation flags (`_charSpansReady`)** — timing windows between check and re-render; can cause selection regressions
3. **Fire-and-forget re-injection calls** — race with re-renders; the idempotent guard sees existing spans, then re-render wipes them
4. **DOM mutation during active selection** — breaks browser selection tracking

## Possible Alternative Approaches (Not Yet Explored)

- **Prevent the re-render entirely**: Register all event listeners during initial render, before NiceGUI's first pass, so "Event listeners changed" never fires
- **Move char span logic server-side**: Accept the websocket size cost, or use compression/chunking
- **Use a different selection mechanism**: CSS-based character targeting instead of DOM span wrapping
- **Shadow DOM / iframe isolation**: Put the document in an element NiceGUI doesn't manage
