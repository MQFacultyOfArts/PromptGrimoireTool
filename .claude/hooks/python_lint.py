#!/usr/bin/env python3
"""Post-write feedback hook: format the file, report its current lint state.

Runs after any Write or Edit on a .py file:
1. ruff format (keeps files formatted without spending a tool call)
2. ruff check --ignore F401 (report only, no autofix)
3. ty check on the file (report only)

Findings are returned as PostToolUse ``additionalContext`` — purely
informational, never framed as a blocking error.  A finding here is the
file's state *right now*, which legitimately fails mid-way through a
batched multi-edit or in a TDD red step (a test written before its
module).  The authoritative gates are the Stop hook (final_lint.py),
explicit verification runs, and pre-commit.

Exit codes:
- 0: Always.  Findings ride the JSON additionalContext channel.
"""

import json
import subprocess
import sys
from pathlib import Path

# Keep hook output bounded so a long diagnostic dump cannot flood the
# conversation context.
_MAX_REPORT_CHARS = 4000


def _run(command: list[str], timeout: int) -> tuple[int, str]:
    """Run a check, returning (returncode, combined output)."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 1, f"timed out after {timeout}s: {' '.join(command)}"
    return result.returncode, (result.stdout + result.stderr).strip()


def main() -> int:
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    file_path = input_data.get("tool_input", {}).get("file_path", "")
    if not file_path.endswith(".py"):
        return 0

    path = Path(file_path)
    if not path.exists():
        return 0

    # Merge conflict markers make every check fail noisily; skip.
    if "<<<<<<< " in path.read_text(errors="replace"):
        return 0

    findings: list[str] = []

    code, output = _run(
        ["uv", "run", "--quiet", "ruff", "format", file_path], timeout=30
    )
    if code != 0:
        findings.append(f"ruff format failed:\n{output}")

    code, output = _run(
        ["uv", "run", "--quiet", "ruff", "check", "--ignore", "F401", file_path],
        timeout=30,
    )
    if code != 0:
        findings.append(f"ruff check:\n{output}")

    code, output = _run(["uvx", "--quiet", "ty@0.0.24", "check", file_path], timeout=60)
    if code != 0:
        findings.append(f"ty check:\n{output}")

    if findings:
        report = "\n\n".join(findings)
        if len(report) > _MAX_REPORT_CHARS:
            report = report[:_MAX_REPORT_CHARS] + "\n… (truncated)"
        context = (
            f"Lint state of {file_path} as of this edit (informational — "
            "expected to fail mid-batch or on a TDD red; the Stop hook and "
            f"pre-commit are the gates):\n{report}"
        )
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": context,
                    }
                }
            )
        )
    else:
        print(json.dumps({"continue": True, "suppressOutput": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
