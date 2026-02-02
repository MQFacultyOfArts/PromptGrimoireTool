# Plan: Move Linting from PostToolUse to Stop Hook

## Problem

The current `PostToolUse` hook runs `ruff check --fix` after every Write/Edit operation. This causes ruff to remove "unused" imports before all files are written, breaking code that will use those imports in subsequent edits.

## Solution

Move linting from `PostToolUse` to the `Stop` hook, which fires when Claude finishes responding and is about to present work to the user. This allows all edits to complete before linting runs.

## Changes

### 1. Update `.claude/settings.json`

Remove the PostToolUse hook for linting. Add a Stop hook that runs comprehensive linting:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/final_lint.py",
            "timeout": 120
          },
          {
            "type": "prompt",
            "prompt": "If Write or Edit tools were used this session to modify Python files, remind the user to run /code-review before committing. Keep the reminder brief (one line)."
          }
        ]
      }
    ]
  }
}
```

### 2. Create `.claude/hooks/final_lint.py`

A new script that:
- Checks `stop_hook_active` to prevent infinite loops
- Finds all `.py` files modified during the session (via git status)
- Runs `ruff check --fix`, `ruff format`, and `ty check` on modified files
- Reports results without blocking (exit 0)

### 3. Modify `python_lint.py` (PostToolUse)

Keep the per-file hook for early error detection, but **remove `--fix`** so ruff reports issues without auto-removing imports. Changes:
- Remove `ruff check --fix` (line 42-48)
- Keep `ruff check` (read-only) for early warnings
- Keep `ruff format` and `ty check`

## Files to Modify

- [.claude/settings.json](.claude/settings.json) - Update hook configuration
- [.claude/hooks/final_lint.py](.claude/hooks/final_lint.py) - Create new Stop hook script
- [.claude/hooks/python_lint.py](.claude/hooks/python_lint.py) - Remove or modify

## Verification

1. Make a multi-file edit that adds imports in one file and uses them in another
2. Confirm imports are not removed mid-session
3. Confirm linting runs when Claude stops and presents work
