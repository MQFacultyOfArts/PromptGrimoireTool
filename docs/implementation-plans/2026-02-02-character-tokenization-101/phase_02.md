# Character-Based Tokenization Implementation Plan

**Goal:** Update all CSS generation to use `data-char-index` and switch call sites to character-based tokenization

**Architecture:** Replace all `data-word-index` selectors with `data-char-index`, update CSS class from `.word` to `.char`, switch state and call sites to use new tokenization function

**Tech Stack:** Python, CSS

**Scope:** Phase 2 of 6 from design plan

**Codebase verified:** 2026-02-02

---

<!-- START_TASK_1 -->
### Task 1: Update `_PAGE_CSS` class `.word` → `.char`

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py:139-146`

**Step 1: Update the CSS class definitions**

Change lines 139-146 from:
```python
    /* Word spans for selection */
    .word {
        cursor: text;
    }

    /* Hover highlight effect when card is hovered */
    .word.card-hover-highlight {
        outline: 2px solid #FFD700 !important;
        outline-offset: 1px;
    }
```

To:
```python
    /* Character spans for selection */
    .char {
        cursor: text;
    }

    /* Hover highlight effect when card is hovered */
    .char.card-hover-highlight {
        outline: 2px solid #FFD700 !important;
        outline-offset: 1px;
    }
```

**Step 2: Verify lint passes**

```bash
uv run ruff check src/promptgrimoire/pages/annotation.py
```

**Expected:** No errors

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update `_build_highlight_css()` to use `data-char-index`

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py:248-307`

**Step 1: Update the function selectors**

In `_build_highlight_css()`, change all `data-word-index` to `data-char-index`:

Line 293 - Change selector:
```python
        css_rules.append(
            f'[data-char-index="{word_idx}"] {{ '
            f"background-color: {bg_rgba}; "
            f"text-decoration: underline; "
            f"text-decoration-color: {underline_color}; "
            f"text-decoration-thickness: {thickness}; }}"
        )
```

Line 303-305 - Change selector:
```python
        if (word_idx + 1) in word_highlights:
            css_rules.append(
                f"[data-char-index=\"{word_idx}\"]::after {{ content: ' '; }}"
            )
```

**Step 2: Run type check**

```bash
uvx ty check src/promptgrimoire/pages/annotation.py
```

**Expected:** No errors

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update cursor and selection CSS functions

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py:310-378`

**Step 1: Update `_build_remote_cursor_css()` (lines 310-337)**

Change all `data-word-index` to `data-char-index`:

Lines 325-332:
```python
        rules.append(
            f'[data-char-index="{word}"] {{ '
            f"position: relative; "
            f"box-shadow: inset 2px 0 0 0 {color}; }}"
        )
        # Floating name label
        rules.append(
            f'[data-char-index="{word}"]::before {{ '
            f'content: "{name}"; position: absolute; top: -1.2em; left: 0; '
            f"font-size: 0.6rem; background: {color}; color: white; "
            f"padding: 1px 3px; border-radius: 2px; white-space: nowrap; "
            f"z-index: 10; }}"
        )
```

**Step 2: Update `_build_remote_selection_css()` (lines 340-378)**

Change all `data-word-index` to `data-char-index`:

Line 358:
```python
        selectors = [f'[data-char-index="{i}"]' for i in range(start, end + 1)]
```

Line 366:
```python
            rules.append(
                f'[data-char-index="{end}"] {{ box-shadow: none !important; }}'
            )
```

Lines 368-371:
```python
            rules.append(f'[data-char-index="{start}"] {{ position: relative; }}')
            rules.append(
                f'[data-char-index="{start}"]::before {{ '
                f'content: "{name}"; position: absolute; top: -1.2em; left: 0; '
                f"font-size: 0.65rem; background: {color}; color: white; "
                f"padding: 1px 4px; border-radius: 2px; white-space: nowrap; "
                f"z-index: 10; }}"
            )
```

**Step 3: Verify changes**

```bash
uvx ty check src/promptgrimoire/pages/annotation.py
```

**Expected:** No errors

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update `PageState` and call sites

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py:177, 784-786, 996, 1457`

**Step 1: Update PageState dataclass (line 177)**

Change:
```python
    document_words: list[str] | None = None  # Words by index
```

To:
```python
    document_chars: list[str] | None = None  # Characters by index
```

**Step 2: Update highlight text extraction (lines 784-786)**

Change:
```python
    highlighted_text = ""
    if state.document_words:
        words_slice = state.document_words[start:end]
        highlighted_text = " ".join(words_slice)
```

To:
```python
    highlighted_text = ""
    if state.document_chars:
        chars_slice = state.document_chars[start:end]
        highlighted_text = "".join(chars_slice)
```

**Step 3: Update document loading (line 996)**

Change:
```python
    if hasattr(doc, "raw_content") and doc.raw_content:
        state.document_words = doc.raw_content.split()
```

To:
```python
    if hasattr(doc, "raw_content") and doc.raw_content:
        _, state.document_chars = _process_text_to_char_spans(doc.raw_content)
```

**Step 4: Update call site for new documents (line 1457)**

Change:
```python
                html_content = _process_text_to_word_spans(content_input.value.strip())
```

To:
```python
                html_content, _ = _process_text_to_char_spans(content_input.value.strip())
```

**Step 5: Run type check and lint**

```bash
uvx ty check src/promptgrimoire/pages/annotation.py && uv run ruff check src/promptgrimoire/pages/annotation.py
```

**Expected:** No errors

**Step 6: Commit Phase 2 changes**

```bash
git add src/promptgrimoire/pages/annotation.py
git commit -m "$(cat <<'EOF'
refactor(annotation): switch to character-based tokenization

- Update _PAGE_CSS: .word -> .char
- Update _build_highlight_css(): data-word-index -> data-char-index
- Update _build_remote_cursor_css(): data-word-index -> data-char-index
- Update _build_remote_selection_css(): data-word-index -> data-char-index
- Update PageState: document_words -> document_chars
- Update call site to use _process_text_to_char_spans()
- Update highlight text extraction to join chars without spaces

Part of Issue #101: CJK unicode support

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_4 -->

---

## Phase 2 UAT Steps

1. [ ] Run type check: `uvx ty check src/promptgrimoire/pages/annotation.py`
2. [ ] Run lint: `uv run ruff check src/promptgrimoire/pages/annotation.py`
3. [ ] Start app: `uv run python -m promptgrimoire`
4. [ ] Navigate to `/annotation`, create workspace, add simple text
5. [ ] Verify character spans appear (inspect DOM for `data-char-index`)
6. [ ] Note: Selection won't work yet (JS still uses old selectors - Phase 3)

## Evidence Required

- [ ] Type check passes
- [ ] Lint passes
- [ ] DOM inspection shows `data-char-index` attributes on each character
