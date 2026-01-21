"""Tests to detect insecure coding patterns.

These tests scan the codebase for patterns that may indicate security issues,
helping catch vulnerabilities before they reach production.
"""

import re
from pathlib import Path
from typing import ClassVar

import pytest

# Root of the project
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Directories to scan
SCAN_DIRS = [PROJECT_ROOT / "src"]

# Files/patterns to exclude
EXCLUDE_PATTERNS = {
    "__pycache__",
    ".git",
    ".venv",
    "node_modules",
    ".pyc",
}


def _get_python_files() -> list[Path]:
    """Get all Python files in scan directories."""
    files = []
    for scan_dir in SCAN_DIRS:
        for py_file in scan_dir.rglob("*.py"):
            if any(excl in str(py_file) for excl in EXCLUDE_PATTERNS):
                continue
            files.append(py_file)
    return files


class TestUrlConstruction:
    """Tests for safe URL construction patterns."""

    # Detects f-string URL with query params like f"url?param={var}"
    UNSAFE_URL_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r'f["\']'  # f-string start
        r"[^\"']*"  # URL path
        r"[?&]"  # query string start or continuation
        r"[a-zA-Z_]+"  # parameter name
        r"=\{"  # ={variable}
        r"[^}]+"  # variable name
        r"\}"  # closing brace
    )

    # Files that are allowed to have this pattern (with justification)
    ALLOWED_FILES: ClassVar[set[str]] = set()

    def test_no_unsafe_url_construction(self) -> None:
        """URLs with query params should use urlencode(), not f-string interpolation.

        Unsafe pattern:
            f"https://api.example.com/path?param={value}&other={other}"

        Safe pattern:
            from urllib.parse import urlencode
            params = {"param": value, "other": other}
            url = f"https://api.example.com/path?{urlencode(params)}"

        This prevents URL injection and parameter pollution attacks.
        """
        violations: list[tuple[Path, int, str]] = []

        for py_file in _get_python_files():
            if py_file.name in self.ALLOWED_FILES:
                continue

            content = py_file.read_text()
            for i, line in enumerate(content.splitlines(), start=1):
                # Skip comments
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue

                if self.UNSAFE_URL_PATTERN.search(line):
                    violations.append((py_file, i, line.strip()))

        if violations:
            msg_lines = [
                "Found unsafe URL construction (use urlencode() instead):",
                "",
            ]
            for path, line_num, line in violations:
                rel_path = path.relative_to(PROJECT_ROOT)
                msg_lines.append(f"  {rel_path}:{line_num}")
                msg_lines.append(f"    {line}")
                msg_lines.append("")

            msg_lines.append("Fix: Use urllib.parse.urlencode() for query parameters:")
            msg_lines.append('  params = {"key": value}')
            msg_lines.append('  url = f"https://example.com/path?{urlencode(params)}"')

            pytest.fail("\n".join(msg_lines))


class TestPathTraversal:
    """Tests for path traversal vulnerability patterns."""

    # Known safe usages (file:line patterns to skip)
    KNOWN_SAFE: ClassVar[set[str]] = {
        # These are safe because they use constants or validated paths
        "sillytavern.py:30",  # Uses pathlib for file reading, not user input
        "sillytavern.py:31",
        "jsonl_log.py",  # Internal logging, not user-controlled
        "config.py",  # Reading from env vars, not user input
    }

    def test_document_path_construction_points(self) -> None:
        """Document all Path() constructions for manual security review.

        This test doesn't fail - it generates a report of all Path()
        constructions that should be manually reviewed for path traversal.
        """
        path_constructions: list[tuple[Path, int, str]] = []

        pattern = re.compile(r"Path\([^)]+\)")

        for py_file in _get_python_files():
            content = py_file.read_text()
            for i, line in enumerate(content.splitlines(), start=1):
                if pattern.search(line):
                    rel_path = py_file.relative_to(PROJECT_ROOT)
                    # Skip known safe patterns
                    skip = False
                    for safe in self.KNOWN_SAFE:
                        if safe in str(rel_path) or safe in f"{rel_path.name}:{i}":
                            skip = True
                            break
                    if not skip:
                        path_constructions.append((py_file, i, line.strip()))

        # This test is informational - stored for potential future reporting
        _ = path_constructions  # Currently unused, but kept for manual review


class TestInputValidation:
    """Tests for input validation patterns."""

    def test_auth_tokens_have_validation(self) -> None:
        """Auth callback handlers should validate token format.

        Tokens from query parameters should be validated before use.
        """
        # Look for auth callback files
        auth_file = PROJECT_ROOT / "src" / "promptgrimoire" / "pages" / "auth.py"
        if not auth_file.exists():
            pytest.skip("auth.py not found")

        content = auth_file.read_text()

        # Check that there's some form of token validation
        # This is a simple heuristic - real validation would be more thorough
        has_token_retrieval = "token" in content.lower()
        has_validation_pattern = any(
            pattern in content
            for pattern in [
                "validate",
                "len(token)",
                "re.match",
                "if not token",
                "token is None",
            ]
        )

        # This is a soft check - just ensure we're thinking about validation
        if has_token_retrieval and not has_validation_pattern:
            pytest.fail(
                "auth.py retrieves tokens but may lack validation.\n"
                "Consider adding token format validation before use."
            )
