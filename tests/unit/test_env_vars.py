"""Tests to ensure .env.example stays in sync with actual env var usage.

This test validates that:
1. All environment variables used in code are documented in .env.example
2. All variables in .env.example are actually used in code
3. .env (if it exists) has the same variables as .env.example
"""

import re
from pathlib import Path

import pytest

# Root of the project
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Files/patterns to exclude from env var scanning
EXCLUDE_PATTERNS = {
    "__pycache__",
    ".git",
    ".venv",
    "node_modules",
    ".pyc",
}


def _extract_env_vars_from_code() -> set[str]:
    """Extract all environment variable names used in Python code.

    Scans both src/ and tests/ directories.
    """
    env_vars: set[str] = set()

    # Patterns to match environment variable access
    patterns = [
        r'os\.environ\.get\(["\']([A-Z_][A-Z0-9_]*)["\']',
        r'os\.environ\[["\']([A-Z_][A-Z0-9_]*)["\']',
        r'os\.getenv\(["\']([A-Z_][A-Z0-9_]*)["\']',
    ]

    # Scan both src/ and tests/ directories
    scan_dirs = [PROJECT_ROOT / "src", PROJECT_ROOT / "tests"]
    for scan_dir in scan_dirs:
        for py_file in scan_dir.rglob("*.py"):
            if any(excl in str(py_file) for excl in EXCLUDE_PATTERNS):
                continue

            content = py_file.read_text()
            for pattern in patterns:
                matches = re.findall(pattern, content)
                env_vars.update(matches)

    return env_vars


def _extract_env_vars_from_file(
    filepath: Path, include_commented: bool = False
) -> set[str]:
    """Extract all environment variable names defined in an env file.

    Args:
        filepath: Path to the env file.
        include_commented: If True, also extract vars from commented lines like
            `# VAR_NAME=value` (for .env.example optional vars).

    Returns:
        Set of environment variable names found.
    """
    env_vars: set[str] = set()

    if not filepath.exists():
        return env_vars

    # Pattern for commented-out env vars: # VAR_NAME=value
    commented_var_pattern = re.compile(r"^#\s*([A-Z_][A-Z0-9_]*)\s*=")

    content = filepath.read_text()
    for line in content.splitlines():
        stripped = line.strip()

        if not stripped:
            continue

        # Check for commented-out variable definitions
        if stripped.startswith("#"):
            if include_commented:
                match = commented_var_pattern.match(stripped)
                if match:
                    env_vars.add(match.group(1))
            continue

        # Extract variable name (before =)
        if "=" in stripped:
            var_name = stripped.split("=", 1)[0].strip()
            if var_name:
                env_vars.add(var_name)

    return env_vars


def _extract_env_vars_from_env_example(include_commented: bool = True) -> set[str]:
    """Extract all environment variable names defined in .env.example.

    Args:
        include_commented: If True (default), include commented-out optional vars.

    Returns:
        Set of environment variable names found.
    """
    return _extract_env_vars_from_file(
        PROJECT_ROOT / ".env.example", include_commented=include_commented
    )


def _extract_env_vars_from_env() -> set[str]:
    """Extract all environment variable names defined in .env."""
    return _extract_env_vars_from_file(PROJECT_ROOT / ".env")


class TestEnvVarsSync:
    """Tests to ensure .env.example stays in sync with code."""

    def test_env_example_exists(self) -> None:
        """Ensure .env.example file exists."""
        env_example = PROJECT_ROOT / ".env.example"
        assert env_example.exists(), ".env.example file must exist"

    def test_all_code_env_vars_documented(self) -> None:
        """All env vars used in code must be documented in .env.example."""
        code_vars = _extract_env_vars_from_code()
        example_vars = _extract_env_vars_from_env_example()

        undocumented = code_vars - example_vars
        assert not undocumented, (
            f"Environment variables used in code but not in .env.example:\n"
            f"{sorted(undocumented)}\n\n"
            f"Add these to .env.example with appropriate documentation."
        )

    def test_all_example_vars_used_in_code(self) -> None:
        """All vars in .env.example must be used somewhere in code."""
        code_vars = _extract_env_vars_from_code()
        example_vars = _extract_env_vars_from_env_example()

        unused = example_vars - code_vars
        assert not unused, (
            f"Environment variables in .env.example but not used in code:\n"
            f"{sorted(unused)}\n\n"
            f"Remove these from .env.example or add usage in code."
        )

    def test_env_example_has_comments(self) -> None:
        """Each env var in .env.example should have a preceding comment."""
        env_example = PROJECT_ROOT / ".env.example"
        content = env_example.read_text()
        lines = content.splitlines()

        vars_without_docs: list[str] = []
        prev_was_comment = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("#"):
                prev_was_comment = True
            elif not stripped:
                # Blank lines don't reset comment status if following a comment
                pass
            elif "=" in stripped:
                var_name = stripped.split("=", 1)[0].strip()
                # Var should have a comment before it (possibly with blank line between)
                if not prev_was_comment:
                    vars_without_docs.append(var_name)
                prev_was_comment = False
            else:
                prev_was_comment = False

        assert not vars_without_docs, (
            f"Environment variables without documentation comments:\n"
            f"{vars_without_docs}\n\n"
            f"Add a comment above each variable explaining its purpose."
        )


class TestEnvFileSync:
    """Tests to ensure .env matches .env.example."""

    def test_env_has_all_required_vars(self) -> None:
        """.env must have all required (uncommented) variables from .env.example."""
        env_file = PROJECT_ROOT / ".env"
        if not env_file.exists():
            pytest.skip(".env file does not exist")

        # Only require uncommented (non-optional) vars
        required_vars = _extract_env_vars_from_env_example(include_commented=False)
        env_vars = _extract_env_vars_from_env()

        missing = required_vars - env_vars
        assert not missing, (
            f"Required variables in .env.example but missing from .env:\n"
            f"{sorted(missing)}\n\n"
            f"Add these to .env (copy from .env.example)."
        )

    def test_env_has_no_extra_vars(self) -> None:
        """.env must not have variables not in .env.example."""
        env_file = PROJECT_ROOT / ".env"
        if not env_file.exists():
            pytest.skip(".env file does not exist")

        # Include commented vars - any var in .env should be documented somewhere
        example_vars = _extract_env_vars_from_env_example(include_commented=True)
        env_vars = _extract_env_vars_from_env()

        extra = env_vars - example_vars
        assert not extra, (
            f"Variables in .env but not in .env.example:\n"
            f"{sorted(extra)}\n\n"
            f"Either remove from .env or add to .env.example (with documentation)."
        )


@pytest.fixture
def env_vars_from_code() -> set[str]:
    """Fixture providing all env vars found in code."""
    return _extract_env_vars_from_code()


@pytest.fixture
def env_vars_from_example() -> set[str]:
    """Fixture providing all env vars in .env.example."""
    return _extract_env_vars_from_env_example()
