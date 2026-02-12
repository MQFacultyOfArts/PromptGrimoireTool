---
source: MDN Web Docs, W3C css-highlight-api-1 spec, Frontend Masters
fetched: 2026-02-12
library: CSS Custom Highlight API (browser built-in)
summary: Complete API reference for CSS.highlights, Highlight class, ::highlight() pseudo-element, StaticRange
---

# CSS Custom Highlight API Reference

## Overview

The CSS Custom Highlight API paints styled regions on arbitrary text ranges **without modifying the DOM**. Highlights are defined in JavaScript via `Range` objects collected into `Highlight` instances, registered in `CSS.highlights`, and styled via `::highlight()` pseudo-elements.

**Baseline status:** Newly available since **June 2025**. Works across latest browsers.

## Browser Support

| Browser | Version | Date | Notes |
|---------|---------|------|-------|
| Chrome | 105+ | Sep 2022 | First to ship |
| Edge | 105+ | Sep 2022 | Chromium-based |
| Safari | 17.2+ | Dec 2023 | |
| Firefox | 140+ | Jun 2025 | `text-decoration` and `text-shadow` NOT supported in `::highlight()` |

**Feature detection:**
```javascript
if (!CSS.highlights) {
  // API not supported
}
```

## Core API

### 1. Create Ranges

```javascript
const textNode = document.querySelector("p").firstChild;

const range = new Range();
range.setStart(textNode, 10);  // start at char 10
range.setEnd(textNode, 25);    // end at char 25
```

Ranges reference DOM text nodes with character offsets within those nodes.

### 2. Create Highlight Objects

```javascript
// Highlight is a Set-like object of Range instances
const highlight = new Highlight(range1, range2, range3);
```

One `Highlight` can hold multiple ranges — all styled identically.

### 3. Register in HighlightRegistry

```javascript
CSS.highlights.set("my-highlight", highlight);
```

### 4. Style with ::highlight()

```css
::highlight(my-highlight) {
  background-color: yellow;
  color: black;
}
```

## Highlight Class (Set-like)

### Constructor

```javascript
const hl = new Highlight(...ranges);  // zero or more Range objects
```

### Properties

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `size` | `number` | 0 | Number of ranges (read-only) |
| `priority` | `number` | 0 | Overlap resolution priority (read-write) |
| `type` | `string` | `"highlight"` | Semantic type for assistive tech (read-write) |

**`type` values:** `"highlight"`, `"spelling-error"`, `"grammar-error"`

### Methods (Set interface)

```javascript
highlight.add(range)         // Add a range
highlight.delete(range)      // Remove a specific range (returns boolean)
highlight.has(range)         // Check if range exists
highlight.clear()            // Remove all ranges
highlight.forEach(callback)  // Iterate ranges
highlight.values()           // Iterator of ranges
highlight.keys()             // Alias for values()
highlight.entries()          // Iterator of [range, range] pairs
```

## HighlightRegistry (CSS.highlights) — Map-like

```javascript
CSS.highlights.set("name", highlight)  // Register
CSS.highlights.get("name")            // Retrieve
CSS.highlights.delete("name")         // Unregister
CSS.highlights.has("name")            // Check existence
CSS.highlights.clear()                // Unregister all
CSS.highlights.size                   // Count (read-only)
CSS.highlights.forEach(callback)      // Iterate
CSS.highlights.entries()              // Iterator of [name, highlight]
CSS.highlights.keys()                 // Iterator of names
CSS.highlights.values()               // Iterator of highlights
```

## ::highlight() Pseudo-Element

### Supported CSS Properties (exhaustive)

- `background-color`
- `color`
- `text-decoration` (and sub-properties) — **NOT in Firefox <146**
- `text-shadow` — **NOT in Firefox <146**
- `-webkit-text-stroke-color`
- `-webkit-text-fill-color`
- `-webkit-text-stroke-width`

### NOT Supported

- `background-image` — explicitly ignored
- `border`, `padding`, `margin` — not applicable
- `opacity` — not directly (use rgba/hsla in background-color)
- **Transitions and animations** — not supported
- **Positioning** — not applicable (highlights are paint-only)

### Inheritance

`::highlight()` follows a special inheritance model (different from normal CSS inheritance). Highlight pseudo-elements inherit from the element they paint over, not from parent highlight rules.

## Priority and Overlapping Highlights

When multiple highlights overlap on the same text:

1. **Same CSS property conflict:** Higher `priority` number wins
2. **Different CSS properties:** All apply (no conflict)
3. **Equal priority:** Most recently registered highlight wins (last `set()` call)
4. **CSS cascade irrelevant:** Source order and `!important` do NOT affect conflict resolution between highlights

```javascript
const hl1 = new Highlight(range1);
const hl2 = new Highlight(range2);  // overlaps range1

hl1.priority = 1;  // wins on overlap for conflicting properties
hl2.priority = 0;

CSS.highlights.set("annotations", hl1);
CSS.highlights.set("search", hl2);
```

**Practical pattern for layering:** Use different CSS properties to avoid conflicts entirely:
```css
::highlight(annotation-bg) { background-color: rgba(255, 255, 0, 0.3); }
::highlight(search-result) { text-decoration: underline wavy red; }
/* Both visible simultaneously on overlapping text */
```

## StaticRange vs Range

| Feature | Range | StaticRange |
|---------|-------|-------------|
| DOM tracking | Live — updates with DOM changes | Fixed — snapshot in time |
| Performance | Higher overhead (tracking) | Lower overhead |
| Constructor | `new Range()` + `setStart/setEnd` | `new StaticRange({startContainer, startOffset, endContainer, endOffset})` |
| Browser support | Universal | Since July 2020 |
| Available in Workers | Yes | No |

**Which to use with Highlight API:**
- `Range` works and is more commonly used in examples
- `StaticRange` is theoretically better for performance (no live tracking overhead)
- If DOM is static (our case — annotation page), either works
- If DOM changes, `StaticRange` won't update (stale references)

```javascript
// StaticRange constructor
const sr = new StaticRange({
  startContainer: textNode,
  startOffset: 10,
  endContainer: textNode,
  endOffset: 25,
});

const hl = new Highlight(sr);
CSS.highlights.set("example", hl);
```

## Practical Patterns

### Dynamic Highlight Updates

```javascript
// To update ranges: modify the Highlight object, not the registry
highlight.clear();
highlight.add(newRange1);
highlight.add(newRange2);
// Changes reflect immediately — no need to re-register
```

### Search Highlighting

```javascript
function highlightMatches(container, searchTerm) {
  CSS.highlights.clear();
  if (!searchTerm) return;

  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const ranges = [];

  let node;
  while ((node = walker.nextNode())) {
    const text = node.textContent.toLowerCase();
    let pos = 0;
    while ((pos = text.indexOf(searchTerm, pos)) !== -1) {
      const range = new Range();
      range.setStart(node, pos);
      range.setEnd(node, pos + searchTerm.length);
      ranges.push(range);
      pos += searchTerm.length;
    }
  }

  const hl = new Highlight(...ranges);
  CSS.highlights.set("search-results", hl);
}
```

### Multiple Annotation Colours

```javascript
// One Highlight per annotation tag
const tagHighlights = new Map();

for (const [tag, ranges] of annotationsByTag) {
  const hl = new Highlight(...ranges);
  CSS.highlights.set(`hl-${tag}`, hl);
  tagHighlights.set(tag, hl);
}
```

```css
::highlight(hl-jurisdiction)  { background-color: rgba(33, 150, 243, 0.3); }
::highlight(hl-legal-issues)  { background-color: rgba(76, 175, 80, 0.3); }
::highlight(hl-key-facts)     { background-color: rgba(255, 152, 0, 0.3); }
```

## Known Gotchas

1. **No transitions/animations.** `::highlight()` does not support CSS transitions. For visual feedback (e.g. throb/pulse), you must use JS timing to toggle highlight on/off.

2. **Firefox text-decoration gap.** Firefox <146 does not support `text-decoration` or `text-shadow` in `::highlight()`. Design with `background-color` as primary indicator.

3. **Safari white-space rendering.** Safari has a known bug where white space between wrapped lines doesn't render background-color correctly.

4. **Stale ranges after DOM mutation.** If the DOM changes, `StaticRange` objects become stale. `Range` objects update but may become invalid. Rebuild ranges after any DOM change.

5. **Client-side only.** Highlights only exist in the browser. SSR cannot pre-render them — there's a flash before highlights appear.

6. **User selection coexists.** User text selection (`::selection`) renders independently of custom highlights. They can overlap without conflict.

7. **`background-image` silently ignored.** Setting it in `::highlight()` does nothing — no error, no effect.

8. **Integer priority only.** `priority` takes integers (positive, negative, zero). No fractional values.

9. **Registration order matters at equal priority.** The last `set()` wins when priority is tied. This means insertion order of `CSS.highlights.set()` calls can affect rendering.
