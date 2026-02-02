# Plan: Claude Code Transcript Archiving System

## Goal

Set up hooks to automatically archive Claude Code conversations to `ai_transcripts/` with:

1. AI-generated titles that reflect the actual topic(s) - generated once after first exchange
2. Dated filenames
3. Persistent storage (not auto-deleted)
4. Pretty-printed HTML output using Simon Willison's [claude-code-transcripts](https://github.com/simonw/claude-code-transcripts) tool
5. Continuous archiving on every Stop event (updates existing archive)
6. A `/retitle` slash command to regenerate the title if needed

## Implementation Steps

### Step 1: Install Dependencies

```bash
uv tool install claude-code-transcripts
pip install anthropic  # For AI-generated titles
```

This provides the `claude-code-transcripts` CLI for converting JSONL transcripts to readable HTML.

### Step 2: Create Archive Script (Python)

Create `tools/archive_transcript.py` that:

- Receives hook payload via stdin (contains `transcript_path`, `session_id`)
- On first archive: generates AI title and creates `ai_transcripts/YYYY-MM-DD-<ai-title>/`
- On subsequent updates: reuses existing directory (no title regeneration)
- Runs `claude-code-transcripts json` to produce HTML output
- Tracks session→directory mapping in a manifest file

### Step 3: Configure Stop Hook

Add to `.claude/settings.local.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /home/brian/people/Jodie/ai-literacy-training-phase-1/tools/archive_transcript.py"
          }
        ]
      }
    ]
  }
}
```

The Stop hook fires after each Claude response, updating the archive incrementally.

### Step 4: Create `/retitle` Slash Command

Create `.claude/commands/retitle.md` to allow manual title regeneration:

```markdown
Regenerate the AI title for the current transcript archive.

Run this command when the conversation topic has evolved and you want a more accurate title.
```

This triggers the archive script with a `--retitle` flag.

### Step 5: Script Implementation Details

**tools/archive_transcript.py** will:

```python
#!/usr/bin/env python3
"""Archive Claude Code transcripts with AI-generated titles."""
import argparse
import json
import sys
import subprocess
import re
from datetime import datetime
from pathlib import Path

try:
    import anthropic
except ImportError:
    anthropic = None

PROJECT_DIR = Path("/home/brian/people/Jodie/ai-literacy-training-phase-1")
ARCHIVE_DIR = PROJECT_DIR / "ai_transcripts"
MANIFEST_FILE = ARCHIVE_DIR / ".session_manifest.json"

def load_manifest() -> dict:
    """Load session→directory mapping."""
    if MANIFEST_FILE.exists():
        return json.loads(MANIFEST_FILE.read_text())
    return {}

def save_manifest(manifest: dict):
    """Save session→directory mapping."""
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))

def extract_fallback_title(content: str) -> str:
    """Extract title from first user message if API unavailable."""
    for line in content.split('\n'):
        try:
            obj = json.loads(line)
            if obj.get('type') == 'human':
                msg = obj.get('message', {}).get('content', '')
                if isinstance(msg, str):
                    return msg[:50]
        except json.JSONDecodeError:
            continue
    return "untitled-conversation"

def generate_title(transcript_content: str) -> str:
    """Generate a descriptive title using Claude Haiku (fast/cheap)."""
    if anthropic is None:
        return extract_fallback_title(transcript_content)

    client = anthropic.Anthropic()
    snippet = transcript_content[:4000]  # More context for better titles

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=50,
        messages=[{
            "role": "user",
            "content": f"Generate a short (3-7 word) title summarizing this conversation. "
                       f"Return ONLY the title, no quotes or punctuation:\n\n{snippet}"
        }]
    )
    return response.content[0].text.strip()

def sanitize_filename(title: str) -> str:
    """Make title safe for filesystem."""
    safe = re.sub(r'[^\w\s-]', '', title)
    safe = re.sub(r'\s+', '-', safe)
    return safe[:50].lower().strip('-')

def archive(session_id: str, transcript_path: Path, force_retitle: bool = False):
    """Archive a transcript, generating title only on first run or if forced."""
    if not transcript_path.exists():
        return

    content = transcript_path.read_text()
    manifest = load_manifest()

    # Check if we already have a directory for this session
    existing_dir = manifest.get(session_id)

    if existing_dir and not force_retitle:
        output_dir = Path(existing_dir)
    else:
        # Generate new title (first archive or retitle requested)
        title = generate_title(content)
        safe_title = sanitize_filename(title)
        date_str = datetime.now().strftime("%Y-%m-%d")
        output_name = f"{date_str}-{safe_title or session_id[:8]}"
        output_dir = ARCHIVE_DIR / output_name

        # If retitling, rename the old directory
        if existing_dir and force_retitle and Path(existing_dir).exists():
            Path(existing_dir).rename(output_dir)

        # Update manifest
        manifest[session_id] = str(output_dir)
        save_manifest(manifest)

    # Check if content changed (skip if unchanged)
    marker_file = output_dir / ".last_size"
    current_size = transcript_path.stat().st_size

    if marker_file.exists() and not force_retitle:
        last_size = int(marker_file.read_text())
        if current_size == last_size:
            return  # No changes

    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate HTML
    subprocess.run([
        "claude-code-transcripts", "json",
        str(transcript_path),
        "-o", str(output_dir),
        "--json"
    ], capture_output=True)

    # Keep raw backup
    (output_dir / "raw-transcript.jsonl").write_text(content)
    marker_file.write_text(str(current_size))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--retitle", action="store_true", help="Force regenerate title")
    args = parser.parse_args()

    payload = json.load(sys.stdin)
    transcript_path = Path(payload['transcript_path'])
    session_id = payload['session_id']

    archive(session_id, transcript_path, force_retitle=args.retitle)

if __name__ == "__main__":
    main()
```

## Files to Modify/Create

| File                                                       | Action                        |
| ---------------------------------------------------------- | ----------------------------- |
| [.claude/settings.local.json](.claude/settings.local.json) | Add Stop hook configuration   |
| tools/archive_transcript.py                                | Create archive script         |
| .claude/commands/retitle.md                                | Create `/retitle` command     |

## Verification

1. Start a new Claude Code conversation
2. Have a brief exchange (the first AI response triggers title generation)
3. Continue the conversation (subsequent updates reuse the same directory)
4. Check `ai_transcripts/` for:
   - Dated directory with meaningful name (e.g., `2026-01-12-setting-up-transcript-archiving`)
   - `index.html` with timeline view
   - `page-*.html` with detailed content
   - `raw-transcript.jsonl` backup
   - `.session_manifest.json` tracking session→directory mapping
5. Test `/retitle` command to verify title regeneration works

## Notes

- **Title generation happens once** - on first archive only, not on every Stop
- **`/retitle` command** - manually regenerate title when conversation topic evolves
- **Manifest file** - tracks which session maps to which directory
- Transcripts stored in project (not `~/.claude/projects/`), avoiding 30-day auto-deletion
- Raw JSONL preserved alongside HTML for future re-processing
- AI title uses Claude Haiku (~$0.001 per call)
- Falls back to first user message if anthropic SDK unavailable

## Sources

- [Simon Willison's claude-code-transcripts article](https://simonwillison.net/2025/Dec/25/claude-code-transcripts/)
- [claude-code-transcripts GitHub](https://github.com/simonw/claude-code-transcripts)
- [Claude Code Hooks documentation](https://code.claude.com/docs/en/hooks)
- [Anthropic blog on hook configuration](https://claude.com/blog/how-to-configure-hooks)
