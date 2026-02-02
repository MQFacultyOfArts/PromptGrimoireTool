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

### Design Questions to Resolve

1. Where does shared logic live? (base class, utils module?)
2. How is dispatch handled? (registry pattern, factory?)
3. What's the interface each platform script must implement?
4. How to test in isolation?

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

Previous session fixed:
- ScienceOS platform detection
- Empty speaker blocks in OpenAI (pattern was too broad)

Current task: Refactor speaker_preprocessor.py into platform-specific sub-scripts.

The goal is to reduce cognitive load by having one file per platform that handles all that platform's quirks (detection, chrome removal, native label stripping, turn markers, special blocks).

Please read docs/wip/pdf-export-qa-handoff.md for full context, then use the brainstorming skill to design this refactor.
```

## Git Status

Changes made but not committed:
- `src/promptgrimoire/export/speaker_preprocessor.py` (ScienceOS + OpenAI fixes)
