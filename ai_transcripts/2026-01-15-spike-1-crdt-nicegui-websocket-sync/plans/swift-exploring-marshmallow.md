# Audit and Improvements Plan for claude-code-research-transcript-hook

## Summary

Transform this forked repository into a research-grade transcript archiving tool with:

- Rich metadata using the **IDW2025 reproducibility framework** (three_ps: Prompt/Process/Provenance)
- Full research package output (CATALOG.json, HTML, JSON, plan files, relationships)
- Interactive `/transcript` command that asks targeted clarifying questions
- Silent auto-archive mode that extracts what it can and flags for human review
- Proper error handling with `--quiet` flag
- Metadata sidecars (no modification of original transcripts)
- Support for both global install (`uv tool install`) and per-repo (`uvx`)

## Key Design Decisions

1. **Never modify original transcripts** - use sidecar `.meta.json` files instead
2. **Two modes**: Silent (hooks) extracts stats/artifacts, flags "needs review"; Interactive (`/transcript`) asks clarifying questions
3. **IDW2025 Three Ps framework**: Prompt (what was asked), Process (how tool was used), Provenance (role in research workflow)
4. **Proleptic questioning**: Ask targeted questions about context that won't be obvious in 6 months
5. **CATALOG.json**: Central index of all sessions with metadata completion status
6. **Plan file archiving**: Copy any plan files from the session into the archive
7. **Project organization**: Global archive uses CC's path encoding (e.g., `-home-user-project`)
8. **Dual install support**: Works as global tool (`uv tool install`) or per-repo (`uvx`)

## Files to Modify

### 1. `src/claude_transcript_archive/cli.py`

**Remove:**

- `update_transcript_title()` function (lines 94-131)
- Call to it from `archive()` (lines 157-160)

**Add new functions:**

```python
def get_cc_project_path(project_dir: Path) -> str:
    """Get CC's path-encoded project ID (e.g., /home/user/project -> -home-user-project)."""

def extract_session_stats(content: str) -> dict:
    """Extract rich metadata: turns, messages, tokens, tool calls, thinking blocks, model, timestamps, duration."""

def estimate_cost(stats: dict) -> float:
    """Estimate API cost based on token usage (input/output/cache pricing)."""

def extract_artifacts(content: str) -> dict:
    """Extract created/modified/referenced files from tool calls with deduplication."""

def detect_relationship_hints(content: str) -> dict:
    """Detect mentions of other sessions, continuation patterns."""

def find_plan_files(transcript_path: Path) -> list[Path]:
    """Find any plan files associated with this session."""

def generate_title_from_content(content: str) -> str:
    """Generate a meaningful title from transcript content (smarter than first 50 chars)."""

def write_metadata_sidecar(
    archive_dir: Path,
    transcript_path: Path,
    session_id: str,
    title: str,
    stats: dict,
    three_ps: dict | None,
    needs_review: bool
) -> None:
    """Write session.meta.json to archive AND next to original transcript."""

def load_catalog(archive_dir: Path) -> dict:
    """Load CATALOG.json or create empty structure."""

def update_catalog(archive_dir: Path, session_metadata: dict) -> None:
    """Update CATALOG.json with new/updated session entry."""
```

**Modify `archive()` function:**

- Extract rich stats (tokens, tool calls, thinking blocks, artifacts)
- Copy plan files into archive directory
- Write metadata sidecar with `needs_review: true` for auto mode
- Update CATALOG.json
- Print errors to stderr by default

**Add CLI flags:**

- `--quiet` - suppress error output
- `--force` - regenerate even if transcript unchanged (for schema/HTML updates)
- Keep existing: `--title`, `--retitle`, `--local`, `--output`

### 2. `claude-commands/transcript.md`

Rewrite the slash command to be interactive:

```markdown
---
description: Archive this conversation with research metadata
---

# Archive Transcript

Based on this conversation, I'll help you create a research-grade archive.

## Step 1: Draft metadata

[Claude analyzes conversation and drafts:]
- Title (3-7 words)
- Inferred three_ps (Prompt/Process/Provenance)
- Detected artifacts and relationships

## Step 2: Clarifying questions

[Claude asks targeted questions about gaps, e.g.:]
- "What was the broader research context for this work?"
- "Were there alternatives you considered but didn't pursue?"
- "How does this connect to other work you're doing?"

## Step 3: Archive

[Execute the archive command with gathered metadata]
```

The prompt should instruct Claude to:

1. Infer what it can from the conversation
2. Identify what won't be obvious in 6 months
3. Ask 1-3 targeted clarifying questions (not a checklist)
4. Execute the archive with complete metadata

### 3. `pyproject.toml`

- Update `name` to `claude-research-transcript`
- Update CLI entry point to `claude-research-transcript`
- Update all GitHub URLs to `claude-code-research-transcript-hook`

### 4. `README.md`

- Update GitHub URLs
- Update CLI command name
- Document `--quiet` flag
- Document metadata sidecar feature
- Document CATALOG.json structure
- Document archive contents (HTML, JSON, plan files, raw transcript)
- Document two modes (silent vs interactive)

### 5. `CLAUDE.md`

- Update CLI command references
- Update repo URL
- Document the three_ps framework briefly

### 6. `example-hooks/settings.local.json`

Fix structure and update command:

```json
{
  "hooks": {
    "Stop": [
      {
        "type": "command",
        "command": "claude-research-transcript --local"
      }
    ]
  }
}
```

## Metadata Schema (session.meta.json)

```json
{
  "schema_version": "1.0",
  "session": {
    "id": "uuid",
    "started_at": "ISO timestamp",
    "ended_at": "ISO timestamp",
    "duration_minutes": 45
  },
  "project": {
    "name": "project-name",
    "directory": "/path/to/project"
  },
  "model": {
    "provider": "anthropic",
    "model_id": "claude-sonnet-4-20250514",
    "access_method": "claude-code-cli"
  },
  "statistics": {
    "turns": 12,
    "human_messages": 12,
    "assistant_messages": 12,
    "thinking_blocks": 5,
    "tool_calls": {"total": 45, "by_type": {"Read": 20, "Edit": 15, "Bash": 10}},
    "tokens": {"input": 50000, "output": 15000, "cache_read": 30000},
    "estimated_cost_usd": 0.85
  },
  "artifacts": {
    "created": [{"path": "src/new.py", "type": "code"}],
    "modified": [{"path": "src/existing.py", "type": "code"}],
    "referenced": [{"path": "README.md", "type": "document"}]
  },
  "relationships": {
    "continues": null,
    "references": [],
    "isPartOf": ["project-name"]
  },
  "auto_generated": {
    "title": "Implementing user authentication",
    "purpose": "Add OAuth2 login flow to the application",
    "tags": ["auth", "oauth", "feature"]
  },
  "three_ps": {
    "prompt_summary": "User requested OAuth2 implementation for their Flask app",
    "process_summary": "Used Read/Edit tools to modify routes.py and add oauth.py",
    "provenance_summary": "Part of the user authentication epic for v2.0 release"
  },
  "plan_files": ["swift-exploring-marshmallow.md"],
  "archive": {
    "archived_at": "ISO timestamp",
    "jsonl_path": "raw-transcript.jsonl",
    "jsonl_sha256": "hash",
    "needs_review": false
  }
}
```

## CATALOG.json Schema

```json
{
  "schema_version": "1.0",
  "generated_at": "ISO timestamp",
  "archive_location": "~/.claude/transcripts",
  "total_sessions": 42,
  "needs_review_count": 3,
  "sessions": [
    {
      "id": "uuid",
      "directory": "2026-01-14-implementing-auth",
      "title": "Implementing user authentication",
      "purpose": "Add OAuth2 login flow",
      "started_at": "ISO timestamp",
      "duration_minutes": 45,
      "tags": ["auth", "oauth"],
      "needs_review": false
    }
  ]
}
```

## Archive Directory Structure

```text
~/.claude/transcripts/                          # Global archive
├── CATALOG.json                                # Central index across all projects
└── -home-user-my-project/                      # Project dir (CC's path encoding)
    ├── CATALOG.json                            # Project-level index
    └── 2026-01-14-implementing-auth/
        ├── index.html                          # Browsable transcript
        ├── session.meta.json                   # Rich metadata
        ├── raw-transcript.jsonl                # Original transcript
        └── plans/                              # Copied plan files (if any)
            └── swift-exploring-marshmallow.md

./ai_transcripts/                               # Local archive (--local)
├── CATALOG.json                                # Project-level index
└── 2026-01-14-implementing-auth/
    └── ...
```

## Verification

1. Build and install locally:

   ```bash
   uv tool install . --force
   ```

2. Test silent mode (simulating hook):

   ```bash
   echo '{"transcript_path": "/path/to/transcript.jsonl", "session_id": "test123"}' | claude-research-transcript --local
   ```

   Verify:
   - HTML generated
   - `session.meta.json` created with `needs_review: true`
   - CATALOG.json updated
   - Sidecar created next to original transcript
   - Original transcript NOT modified

3. Test interactive mode via `/transcript`:
   - Run `/transcript` in a Claude Code session
   - Verify Claude asks clarifying questions
   - Verify complete metadata saved with `needs_review: false`

4. Test error handling:

   ```bash
   echo '{"transcript_path": "/nonexistent", "session_id": "x"}' | claude-research-transcript
   # Should print error to stderr

   echo '{"transcript_path": "/nonexistent", "session_id": "x"}' | claude-research-transcript --quiet
   # Should be silent
   ```
