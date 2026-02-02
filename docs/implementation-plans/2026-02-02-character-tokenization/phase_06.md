# Character-Based Tokenization Implementation Plan

**Goal:** Manual verification with real CJK and BLNS content

**Architecture:** UAT steps for human verification of character-based selection and export

**Tech Stack:** Manual testing, browser DevTools

**Scope:** Phase 6 of 6 from design plan

**Codebase verified:** 2026-02-02

---

<!-- START_TASK_1 -->
### Task 1: Verify CJK character selection

**Prerequisites:**
- All previous phases completed
- App running: `uv run python -m promptgrimoire`

**Step 1: Load Chinese text into workspace**

1. Navigate to `http://localhost:8080/annotation`
2. Create new workspace
3. Add document with Chinese content:
   ```
   你好世界
   这是一个测试
   ```
4. Save document

**Step 2: Verify DOM structure**

1. Open browser DevTools (F12)
2. Inspect the document content
3. Verify each Chinese character has its own `<span>` with `data-char-index`:
   ```html
   <span class="char" data-char-index="0">你</span>
   <span class="char" data-char-index="1">好</span>
   <span class="char" data-char-index="2">世</span>
   <span class="char" data-char-index="3">界</span>
   ```

**Step 3: Test character selection**

1. Click on character "好" (index 1)
2. Shift+click on character "世" (index 2)
3. Verify selection highlights exactly those 2 characters
4. Create annotation card
5. Verify highlight persists and card shows selected text "好世"

**Step 4: Test Japanese and Korean**

Repeat steps 1-3 with:
- Japanese: `こんにちは世界`
- Korean: `안녕하세요`

**Expected:** Each character individually selectable, highlights work correctly

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Verify BLNS paste-in

**Step 1: Load BLNS content**

1. Open `tests/fixtures/blns.txt` in a text editor
2. Copy the "Two-Byte Characters" section (includes CJK, emoji, special chars)
3. Paste into a new workspace document
4. Save document

**Step 2: Verify rendering**

1. Check that all characters render (no missing glyphs)
2. Check that each character has its own span
3. Use DevTools to verify `data-char-index` attributes are sequential

**Step 3: Test selection on edge cases**

1. Select emoji characters (if present)
2. Select zero-width characters (should be selectable but invisible)
3. Select mixed scripts (Latin + CJK + emoji)

**Expected:** All BLNS content renders and is selectable character-by-character

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify RTL text handling

**Step 1: Add Arabic text**

1. Create new document with Arabic:
   ```
   مرحبا بالعالم
   ```
   (Hello world in Arabic)

**Step 2: Verify DOM order**

1. Inspect with DevTools
2. Characters should be indexed left-to-right in DOM (0, 1, 2...)
3. Visual rendering should be right-to-left (browser handles this via Unicode bidi)

**Step 3: Test selection**

1. Click on first visible character (rightmost in display)
2. Shift+click on third character
3. Verify correct characters are selected
4. Create highlight and verify it persists

**Step 4: Add Hebrew text**

Repeat with Hebrew:
```
שלום עולם
```

**Expected:** RTL text displays correctly, selection works by DOM index

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Verify hard whitespace (AustLII case)

**Step 1: Load AustLII-style content**

1. Create document with non-breaking spaces (copy from 183-austlii fixture or type manually):
   ```
   Smith v Jones [2024] NSWSC 123
   ```
   Where spaces between case components are non-breaking spaces (U+00A0)

**Step 2: Verify whitespace spans**

1. Open DevTools
2. Check that non-breaking spaces have their own `data-char-index`
3. Example: "Smith" = indices 0-4, nbsp = index 5, "v" = index 6

**Step 3: Test whitespace selection**

1. Click on the non-breaking space (may need to click between words)
2. Verify it can be selected
3. Create highlight that includes the nbsp
4. Verify highlight spans correctly across the whitespace

**Step 4: Test ideographic space (U+3000)**

Add content with ideographic space:
```
你　好
```
(Chinese with full-width space in middle)

Verify the ideographic space is selectable.

**Expected:** All whitespace types (regular, nbsp, ideographic) are individually selectable

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Verify PDF export with CJK highlights

**Step 1: Create CJK document with highlights**

1. Create workspace with CJK content:
   ```
   这是一个重要的测试文档。
   我们需要验证PDF导出功能。
   ```
2. Create highlight on "重要" (indices for "重要")
3. Create highlight on "验证" with different color

**Step 2: Export to PDF**

1. Click export button
2. Select PDF format
3. Wait for export to complete

**Step 3: Verify PDF output**

1. Open the exported PDF
2. Verify CJK characters render correctly (proper fonts)
3. Verify highlights appear at correct positions
4. Verify highlight colors are correct

**Step 4: Export mixed content**

Create document with mixed Latin/CJK/RTL and highlights spanning different scripts:
```
Hello 世界 مرحبا World
```

Export and verify all scripts render with correct highlights.

**Expected:** PDF exports correctly with CJK fonts and accurate highlight positions

<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Final sign-off

**UAT Checklist:**

- [ ] **CJK Selection:** Chinese, Japanese, Korean characters individually selectable
- [ ] **BLNS Content:** All BLNS strings render and are selectable
- [ ] **RTL Text:** Arabic and Hebrew display correctly, selection works
- [ ] **Hard Whitespace:** Non-breaking spaces and ideographic spaces selectable
- [ ] **PDF Export:** CJK highlights export to PDF correctly
- [ ] **Mixed Scripts:** Documents with multiple scripts work correctly

**User Sign-off:**

After completing all verification steps, user confirms:

> "Character-based tokenization is working correctly for CJK text, BLNS content, RTL scripts, and hard whitespace. PDF export produces correct highlights."

**Step: Mark Issue #101 as resolved**

```bash
# Add comment to issue with UAT results
gh issue comment 101 --body "UAT completed for character-based tokenization. All verification steps passed."
```

<!-- END_TASK_6 -->

---

## Phase 6 UAT Summary

| Test Area | Content | Verification |
|-----------|---------|--------------|
| CJK Selection | Chinese, Japanese, Korean | Each character has own span, selection works |
| BLNS | blns.txt Two-Byte section | All content renders, selectable |
| RTL | Arabic, Hebrew | Correct display and selection |
| Hard Whitespace | nbsp (U+00A0), ideographic space (U+3000) | Individually selectable |
| PDF Export | CJK with highlights | Correct fonts, accurate positions |

## Evidence Required

- [ ] Screenshot: CJK document with character spans visible in DevTools
- [ ] Screenshot: BLNS content loaded in workspace
- [ ] Screenshot: RTL text with highlight
- [ ] Screenshot: PDF export with CJK highlights
- [ ] User confirmation of all UAT steps passing
