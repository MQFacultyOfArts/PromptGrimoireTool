# Plan: Create Shareable claude-code-transcript-hook Package

## Goal

Create a standalone, installable tool at `/home/brian/people/brian/claude-code-transcript-hook` that anyone can deploy to archive Claude Code transcripts with nice HTML output.

## Behavior Summary

- **Manual `/transcript`:** Archives to central `~/.claude/transcripts/` by default
- **Project auto-archive (opt-in):** Projects with Stop hook archive to local `ai_transcripts/`
- **Override:** `--local` flag archives to project's `ai_transcripts/`

## Project Structure

```
/home/brian/people/brian/claude-code-transcript-hook/
├── README.md                    # Installation & usage docs
├── pyproject.toml               # Package config (uv/pip installable)
├── src/
│   └── claude_transcript_archive/
│       ├── __init__.py
│       └── cli.py               # Main script
├── claude-commands/
│   └── transcript.md            # Ready-to-copy slash command
└── example-hooks/
    └── settings.local.json      # Example auto-archive hook config
```

## Installation Options (for users)

### Option A: uv tool install (recommended)
```bash
uv tool install git+https://github.com/Denubis/claude-code-transcript-hook
```

### Option B: pipx
```bash
pipx install git+https://github.com/Denubis/claude-code-transcript-hook
```

### Option C: Manual
```bash
git clone https://github.com/Denubis/claude-code-transcript-hook
cd claude-code-transcript-hook
uv tool install .
```

All options install `claude-transcript-archive` to `~/.local/bin/`.

## CLI Interface

```
claude-transcript-archive [OPTIONS]

Options:
  --title TITLE      Title for the transcript (from /transcript skill)
  --retitle          Force regenerate title/rename directory
  --local            Archive to ./ai_transcripts/ instead of central
  --output DIR       Custom output directory

Input: JSON on stdin with {transcript_path, session_id}
       (automatically provided by Claude Code hooks)
```

## Dependencies

- Python 3.10+ (stdlib only for core)
- `claude-code-transcripts` - Simon Willison's tool for HTML generation
  - Installed automatically as dependency, or user can install separately

## Files to Create

| File | Purpose |
|------|---------|
| `README.md` | Installation, setup, usage documentation |
| `pyproject.toml` | Package metadata, dependencies, entry point |
| `src/claude_transcript_archive/__init__.py` | Package init |
| `src/claude_transcript_archive/cli.py` | Main script (adapted from current) |
| `claude-commands/transcript.md` | Slash command for users to copy |
| `example-hooks/settings.local.json` | Example Stop hook config |

## Key Changes from Current Implementation

1. **Remove hardcoded paths** - use `~/.claude/transcripts/` or CWD
2. **Make it a proper package** - installable via uv/pipx
3. **Add `claude-code-transcripts` as dependency** - auto-install
4. **Documentation** - README with setup instructions
5. **Example configs** - ready-to-copy hook and command files

## User Setup (documented in README)

1. Install the tool
2. Copy `claude-commands/transcript.md` to `~/.claude/commands/`
3. (Optional) Add Stop hook for auto-archive per-project

## Verification

1. Install from the new repo
2. Run `/transcript` from any project
3. Confirm transcript appears in `~/.claude/transcripts/`
4. Test `--local` flag
5. Test auto-archive hook in a project
