#!/usr/bin/env python3
"""Convert Claude Code JSONL conversation transcripts to readable Markdown.

Usage:
    uv run python scripts/jsonl_to_md.py <input.jsonl> [output.md]

If output is omitted, writes to stdout.
"""

import json
import sys
from pathlib import Path


def _format_tool_use(tool_name: str, tool_input: dict) -> str:
    """Format a tool use block compactly."""
    match tool_name:
        case "Read":
            return f"**Tool: Read** `{tool_input.get('file_path', '')}`"
        case "Bash":
            cmd = tool_input.get("command", "")
            desc = tool_input.get("description", "")
            prefix = f"**Tool: Bash** ({desc})" if desc else "**Tool: Bash**"
            return f"{prefix}\n```bash\n{cmd}\n```"
        case "Edit" | "Write":
            return f"**Tool: {tool_name}** `{tool_input.get('file_path', '')}`"
        case "Grep":
            pattern = tool_input.get("pattern", "")
            path = tool_input.get("path", ".")
            return f"**Tool: Grep** `{pattern}` in `{path}`"
        case "Glob":
            return f"**Tool: Glob** `{tool_input.get('pattern', '')}`"
        case _:
            return f"**Tool: {tool_name}**"


def _format_block(block: dict) -> str | None:
    """Format a single content block. Returns None if block should be skipped."""
    block_type = block.get("type")
    match block_type:
        case "text":
            return block.get("text", "")
        case "thinking":
            thinking = block.get("thinking", "")
            if thinking:
                return (
                    f"<details><summary>Thinking</summary>\n\n{thinking}\n\n</details>"
                )
        case "tool_use":
            return _format_tool_use(
                block.get("name", "unknown"), block.get("input", {})
            )
        case "tool_result":
            content = block.get("content", "")
            if isinstance(content, str) and len(content) > 500:
                content = content[:500] + "\n... (truncated)"
            if content:
                return f"```\n{content}\n```"
    return None


def extract_text_content(content_list: list) -> str:
    """Extract text from message content blocks."""
    parts = [_format_block(block) for block in content_list]
    return "\n\n".join(p for p in parts if p)


def convert_jsonl_to_md(jsonl_path: Path) -> str:
    """Convert JSONL transcript to markdown."""
    lines = []
    lines.append(f"# Conversation: {jsonl_path.stem}\n")

    with jsonl_path.open() as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if not stripped:
                continue

            try:
                record = json.loads(stripped)
            except json.JSONDecodeError:
                continue

            record_type = record.get("type")
            message = record.get("message", {})

            # Skip non-message records (progress, file-history-snapshot, etc.)
            if record_type not in ("user", "assistant"):
                continue

            role = message.get("role", record_type)
            content = message.get("content", [])

            # Handle string content (simple user messages)
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = extract_text_content(content)
            else:
                continue

            if not text.strip():
                continue

            # Format as markdown
            if role == "user":
                lines.append(f"## User\n\n{text}\n")
            elif role == "assistant":
                lines.append(f"## Assistant\n\n{text}\n")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    md_content = convert_jsonl_to_md(input_path)

    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])
        output_path.write_text(md_content)
        print(f"Written to {output_path}", file=sys.stderr)
    else:
        print(md_content)


if __name__ == "__main__":
    main()
