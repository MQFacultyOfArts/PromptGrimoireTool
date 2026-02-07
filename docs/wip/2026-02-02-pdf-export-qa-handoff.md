# PDF Export Visual QA - Session Handoff

## Context

Branch: `css-fidelity-pdf-export`
Working on: Visual QA of PDF exports, fixing preprocessing issues

## What Was Fixed This Session

1. **ScienceOS platform detection** - Changed detection pattern from `tabler-icon-robot-face` to `_prompt_` class
   - File: `src/promptgrimoire/export/speaker_preprocessor.py` lines 28, 62-67

2. **Empty speaker blocks in OpenAI** - Changed user turn pattern from `items-end` to `data-message-author-role="user"`
   - File: `src/promptgrimoire/export/speaker_preprocessor.py` lines 44-50
   - Root cause: `items-end` matched 10 nested layout divs, only 3 were real user turns

All 40 integration tests pass.

## Current Issue: Duplicate Labels

PDFs show duplicate speaker labels:
- OpenAI: "You said: User:" (platform native + injected)
- AI Studio: "User User:" (native `<div class="author-label">User</div>` + injected)

### Approved Direction

User approved refactoring to **platform-specific sub-scripts** to reduce cognitive load:

```
platforms/
  openai.py      → all OpenAI quirks
  aistudio.py    → all AI Studio quirks
  gemini.py      → all Gemini quirks
  claude.py      → all Claude quirks
  scienceos.py   → all ScienceOS quirks
```

Each script handles:
1. Platform detection pattern
2. Chrome to remove (platform-specific)
3. Native labels to strip
4. Turn markers for speaker injection
5. Special blocks (thinking summaries, etc.)

### Design Questions - RESOLVED

Design complete: `docs/design-plans/2026-02-02-platform-handler-refactor.md`

Key decisions:
1. **Shared logic**: `platforms/base.py` for utilities, Protocol in `__init__.py`
2. **Dispatch**: Registry + autodiscovery via `pkgutil.iter_modules()`
3. **Interface**: `PlatformHandler` Protocol with `matches()`, `preprocess()`, `get_turn_markers()`
4. **Testing**: Each platform has isolated unit tests; registry tests cover autodiscovery
5. **HTML parsing**: selectolax (lexbor) replaces BeautifulSoup (5-30x faster)
6. **User override**: `platform_hint` parameter for manual platform selection

## Other Issues Found (Not Yet Fixed)

| Issue | Severity | Notes |
|-------|----------|-------|
| Code block overflow | HIGH | fancyvrb doesn't wrap - need `listings` package |
| Table truncation | MEDIUM | Wide tables overflow page margins |
| CJK font fallback | HIGH | BLOCKED on 101-cjk-blns merge |

## Files to Review

- `src/promptgrimoire/export/speaker_preprocessor.py` - current platform detection + injection
- `src/promptgrimoire/export/chrome_remover.py` - generic chrome removal (if exists)
- Scratchpad rubric: `/tmp/claude-1000/.../scratchpad/visual-qa-rubric.md`

## Prompt for New Session

```
I'm continuing work on the css-fidelity-pdf-export branch for PDF visual QA.

Design complete: docs/design-plans/2026-02-02-platform-handler-refactor.md

Next step: Execute the implementation plan (5 phases).

Please read the design plan, then use the starting-an-implementation-plan skill to begin implementation.
```

## Git Status

Changes made but not committed:
- `src/promptgrimoire/export/speaker_preprocessor.py` (ScienceOS + OpenAI fixes)
