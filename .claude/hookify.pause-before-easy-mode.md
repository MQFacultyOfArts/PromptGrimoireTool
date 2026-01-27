---
name: pause-before-easy-mode
enabled: true
event: file
conditions:
  - field: new_text
    operator: regex_match
    pattern: #\s*(TODO|FIXME|HACK|XXX):?\s*(for now|later|simplif|temporary|workaround)|#\s*simplified|#\s*easy|pass\s*#|\.\.\.(\s*#|$)|NotImplementedError|raise\s+NotImplementedError|# (skip|ignore|remove)\s*(this|for now|later)
action: warn
---

**"Easy Mode" Pattern Detected**

You may be simplifying or deferring instead of implementing properly.

**Detected patterns that suggest shortcuts:**
- TODO/FIXME comments deferring work
- "for now", "temporary", "workaround" language
- `pass` or `...` placeholders
- `NotImplementedError` stubs
- Comments suggesting skipping functionality

**Before proceeding, pause and ask:**
1. Is this simplification what the user actually wants?
2. Should you implement the full solution instead?
3. Did you hit complexity and choose "easy" over "right"?

**Principle:** When facing a hard problem, don't silently simplify. Ask the user: "This is complex - would you prefer I implement it fully or use a simpler approach?"
