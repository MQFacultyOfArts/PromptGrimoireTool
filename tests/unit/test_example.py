"""Example test demonstrating TDD pattern.

This test file shows the expected testing workflow:
1. Write a failing test that describes desired behavior
2. Implement minimal code to make it pass
3. Refactor as needed
"""

from promptgrimoire import __version__


def test_version_exists() -> None:
    """Package should have a version string."""
    assert __version__ is not None
    assert isinstance(__version__, str)
    assert len(__version__) > 0


def test_version_format() -> None:
    """Version should follow semver format (major.minor.patch).

    HIGH-12 fix: Strengthened assertion to require exactly 3 parts.
    """
    parts = __version__.split(".")
    assert len(parts) == 3, f"Version should be major.minor.patch, got: {__version__}"
    # All three parts should be numeric
    assert parts[0].isdigit(), f"Major version should be numeric, got: {parts[0]}"
    assert parts[1].isdigit(), f"Minor version should be numeric, got: {parts[1]}"
    assert parts[2].isdigit(), f"Patch version should be numeric, got: {parts[2]}"
