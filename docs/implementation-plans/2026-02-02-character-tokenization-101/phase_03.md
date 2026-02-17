# Character-Based Tokenization Implementation Plan

**Goal:** Update JavaScript selection handling to work with character-based spans

**Architecture:** Update all `data-w` and `data-word-index` selectors in JavaScript to use `data-char-index`, update `dataset.w` to `dataset.charIndex`

**Tech Stack:** JavaScript, Python (inline JS)

**Scope:** Phase 3 of 6 from design plan

**Codebase verified:** 2026-02-02

---

<!-- START_TASK_1 -->
### Task 1: Update `live-annotation.js` selectors

**Files:**
- Modify: `src/promptgrimoire/assets/js/live-annotation.js`

**Step 1: Update `data-w` attribute references**

Change all instances of `data-w` to `data-char-index`:

Line ~45 (word span detection):
```javascript
// OLD:
const wordSpan = target.closest('[data-w]');

// NEW:
const wordSpan = target.closest('[data-char-index]');
```

Line ~52 (dataset access):
```javascript
// OLD:
const wordIndex = parseInt(wordSpan.dataset.w, 10);

// NEW:
const charIndex = parseInt(wordSpan.dataset.charIndex, 10);
```

**Step 2: Update variable names throughout**

Replace `wordIndex` with `charIndex` in all contexts:
- Selection start/end tracking
- Event handler parameters
- CRDT update calls

**Step 3: Update selection boundary finding**

Lines ~65-85 (findSelectionBounds function):
```javascript
// OLD:
function findSelectionBounds() {
    const spans = Array.from(container.querySelectorAll('[data-w]'));
    // ...
    return { startWord: start, endWord: end };
}

// NEW:
function findSelectionBounds() {
    const spans = Array.from(container.querySelectorAll('[data-char-index]'));
    // ...
    return { startChar: start, endChar: end };
}
```

**Step 4: Update all remaining `data-w` selectors**

Search and replace in the file:
- `[data-w]` → `[data-char-index]`
- `dataset.w` → `dataset.charIndex`
- `wordIndex` → `charIndex`
- `startWord` → `startChar`
- `endWord` → `endChar`

**Expected occurrences to update:** ~11 in live-annotation.js

**Step 5: Verify no old-style `data-w` or `dataset.w` references remain**

```bash
# Check for data-w='N' or data-w="N" patterns (the shorthand attribute)
grep -nE "data-w['\"]" src/promptgrimoire/assets/js/live-annotation.js
# Check for dataset.w accessor
grep -nE "dataset\.w[^o]" src/promptgrimoire/assets/js/live-annotation.js
```

**Expected:** No matches (the patterns specifically avoid matching `data-word-index` or `dataset.wordIndex`)

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update inline JS in annotation.py selection handlers

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py:893-920`

**Step 1: Update mouseup selection handler**

Around line 893, in the mouseup event handler JS:

```python
# OLD:
            ui.run_javascript('''
                const selection = window.getSelection();
                if (!selection.rangeCount) return;
                const range = selection.getRangeAt(0);
                const container = document.querySelector('.document-content');
                if (!container) return;

                const spans = Array.from(container.querySelectorAll('[data-w]'));
                // ... uses data-w ...
            ''')

# NEW:
            ui.run_javascript('''
                const selection = window.getSelection();
                if (!selection.rangeCount) return;
                const range = selection.getRangeAt(0);
                const container = document.querySelector('.document-content');
                if (!container) return;

                const spans = Array.from(container.querySelectorAll('[data-char-index]'));
                // ... uses data-char-index ...
            ''')
```

**Step 2: Update span attribute access**

```python
# OLD:
                const startSpan = spans.find(s => range.intersectsNode(s));
                const startIndex = startSpan ? parseInt(startSpan.dataset.w, 10) : -1;

# NEW:
                const startSpan = spans.find(s => range.intersectsNode(s));
                const startIndex = startSpan ? parseInt(startSpan.dataset.charIndex, 10) : -1;
```

**Step 3: Run lint check**

```bash
uv run ruff check src/promptgrimoire/pages/annotation.py
```

**Expected:** No errors

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update go-to-highlight and scroll-sync JS

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py:1077-1120`

**Step 1: Update go-to-highlight selector**

Around line 1077, in the card click handler that scrolls to highlight:

```python
# OLD:
            ui.run_javascript(f'''
                const targetSpan = document.querySelector('[data-w="{start_idx}"]');
                if (targetSpan) {{
                    targetSpan.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                }}
            ''')

# NEW:
            ui.run_javascript(f'''
                const targetSpan = document.querySelector('[data-char-index="{start_idx}"]');
                if (targetSpan) {{
                    targetSpan.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                }}
            ''')
```

**Step 2: Update any scroll-sync or position tracking**

Search for other inline JS that references word indices:

```bash
grep -n "data-w" src/promptgrimoire/pages/annotation.py
grep -n "dataset.w" src/promptgrimoire/pages/annotation.py
```

Update all found occurrences to use `data-char-index` and `dataset.charIndex`.

**Step 3: Verify no old selectors remain**

```bash
grep -n "data-w[^o]" src/promptgrimoire/pages/annotation.py
```

**Expected:** No matches (note: `data-w` followed by `o` would be `data-word-index` which should also be gone by now from Phase 2)

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update Python event handlers

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py`

**Step 1: Update event handler parameter names**

Search for Python functions that receive word indices from JavaScript:

```python
# OLD:
async def handle_selection(start_word: int, end_word: int) -> None:
    ...

# NEW:
async def handle_selection(start_char: int, end_char: int) -> None:
    ...
```

**Step 2: Update any variable references**

In the event handlers, update:
- `start_word` → `start_char`
- `end_word` → `end_char`
- `word_index` → `char_index`

**Step 3: Run type check and lint**

```bash
uvx ty check src/promptgrimoire/pages/annotation.py && uv run ruff check src/promptgrimoire/pages/annotation.py
```

**Expected:** No errors

**Step 4: Commit Phase 3 changes**

```bash
git add src/promptgrimoire/assets/js/live-annotation.js src/promptgrimoire/pages/annotation.py
git commit -m "$(cat <<'EOF'
refactor(annotation): update JS to character-based selection

- Update live-annotation.js: data-w -> data-char-index
- Update live-annotation.js: dataset.w -> dataset.charIndex
- Update inline JS selection handlers in annotation.py
- Update go-to-highlight scroll targeting
- Rename word index variables to char index

Part of Issue #101: CJK unicode support

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_4 -->

---

## Phase 3 UAT Steps

1. [ ] Run grep to verify no `data-w` or `dataset.w` remain in JS files
2. [ ] Run type check: `uvx ty check src/promptgrimoire/pages/annotation.py`
3. [ ] Run lint: `uv run ruff check src/promptgrimoire/pages/annotation.py`
4. [ ] Start app: `uv run python -m promptgrimoire`
5. [ ] Navigate to `/annotation`, create workspace, add text
6. [ ] Verify character selection works (click and drag)
7. [ ] Verify clicking a card scrolls to the correct highlight

## Evidence Required

- [ ] No `data-w` or `dataset.w` in grep output
- [ ] Type check passes
- [ ] Lint passes
- [ ] Character selection creates highlights at correct positions
