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
    """Version should follow semver format (x.y.z)."""
    parts = __version__.split(".")
    assert len(parts) >= 2, "Version should have at least major.minor"
    # First two parts should be numeric
    assert parts[0].isdigit(), "Major version should be numeric"
    assert parts[1].isdigit(), "Minor version should be numeric"
