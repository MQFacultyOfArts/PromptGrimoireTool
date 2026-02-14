"""Tests to ensure .env.example stays in sync with Settings schema.

This test validates that:
1. All Settings fields have a corresponding entry in .env.example
2. All variables in .env.example correspond to a Settings field
3. All nested field env vars use double-underscore convention
4. .env (if it exists) has the same variables as .env.example
5. No load_dotenv() calls exist in application code (AC6.1)
6. No os.environ.get() calls exist in application code (AC6.2)
7. No direct dotenv imports exist anywhere (AC6.3)
"""

import re
from pathlib import Path

import pytest
from pydantic import BaseModel

from promptgrimoire.config import Settings

# Root of the project
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Env vars documented in .env.example but managed outside pydantic-settings
# (e.g. runtime coordination vars set programmatically by CLI commands).
_NON_SETTINGS_ENV_VARS = {
    "E2E_BASE_URL",  # Set by `test-e2e` CLI, read by conftest fixture
}


def _derive_env_var_names(settings_cls: type[Settings]) -> set[str]:
    """Derive expected env var names from Settings schema.

    For each sub-model field (e.g. ``stytch: StytchConfig``), iterates
    the sub-model's fields and produces ``STYTCH__PROJECT_ID`` etc.
    Direct fields on Settings are uppercased without a prefix.
    """
    names: set[str] = set()
    delimiter = settings_cls.model_config.get("env_nested_delimiter", "__")

    for field_name, field_info in settings_cls.model_fields.items():
        annotation = field_info.annotation
        # Unwrap Optional, etc. to find the actual type
        origin = getattr(annotation, "__origin__", None)
        if origin is not None:
            args = getattr(annotation, "__args__", ())
            annotation = args[0] if args else annotation

        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            prefix = field_name.upper()
            for sub_field_name in annotation.model_fields:
                names.add(f"{prefix}{delimiter}{sub_field_name.upper()}")
        else:
            names.add(field_name.upper())

    return names


def _extract_env_vars_from_file(
    filepath: Path, *, include_commented: bool = False
) -> set[str]:
    """Extract all environment variable names from an env file.

    Args:
        filepath: Path to the env file.
        include_commented: If True, include commented-out vars like
            ``# VAR_NAME=value``.
    """
    env_vars: set[str] = set()
    if not filepath.exists():
        return env_vars

    commented_var_pattern = re.compile(r"^#\s*([A-Z_][A-Z0-9_]*)\s*=")

    for line in filepath.read_text().splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("#"):
            if include_commented:
                match = commented_var_pattern.match(stripped)
                if match:
                    env_vars.add(match.group(1))
            continue

        if "=" in stripped:
            var_name = stripped.split("=", 1)[0].strip()
            if var_name:
                env_vars.add(var_name)

    return env_vars


def _extract_env_vars_from_env_example(
    *,
    include_commented: bool = True,
) -> set[str]:
    """Extract all environment variable names from .env.example."""
    return _extract_env_vars_from_file(
        PROJECT_ROOT / ".env.example", include_commented=include_commented
    )


class TestSettingsEnvVarsSync:
    """Ensure .env.example stays in sync with Settings schema."""

    def test_env_example_exists(self) -> None:
        env_example = PROJECT_ROOT / ".env.example"
        assert env_example.exists(), ".env.example file must exist"

    def test_all_settings_fields_in_env_example(self) -> None:
        """Every derived env var name must appear in .env.example (AC5.1)."""
        schema_vars = _derive_env_var_names(Settings)
        example_vars = _extract_env_vars_from_env_example()

        missing = schema_vars - example_vars
        assert not missing, (
            f"Settings fields not documented in .env.example:\n"
            f"{sorted(missing)}\n\n"
            f"Add these to .env.example with documentation."
        )

    def test_all_env_example_vars_in_settings(self) -> None:
        """Every .env.example var must correspond to a Settings field (AC5.2)."""
        schema_vars = _derive_env_var_names(Settings)
        example_vars = _extract_env_vars_from_env_example()

        extra = example_vars - schema_vars - _NON_SETTINGS_ENV_VARS
        assert not extra, (
            f"Variables in .env.example but not in Settings schema:\n"
            f"{sorted(extra)}\n\n"
            f"Remove from .env.example or add a Settings field."
        )

    def test_env_var_names_use_double_underscore(self) -> None:
        """All nested field env vars must use __ delimiter (AC5.3)."""
        schema_vars = _derive_env_var_names(Settings)
        # Every derived name for a nested field must contain __
        for field_name, field_info in Settings.model_fields.items():
            annotation = field_info.annotation
            origin = getattr(annotation, "__origin__", None)
            if origin is not None:
                args = getattr(annotation, "__args__", ())
                annotation = args[0] if args else annotation

            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                prefix = field_name.upper()
                for sub_field_name in annotation.model_fields:
                    var_name = f"{prefix}__{sub_field_name.upper()}"
                    assert var_name in schema_vars
                    assert "__" in var_name

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
                pass  # blank lines don't reset comment status
            elif "=" in stripped:
                var_name = stripped.split("=", 1)[0].strip()
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
    """Ensure .env matches .env.example."""

    def test_env_has_all_required_vars(self) -> None:
        """.env must have all required (uncommented) variables from .env.example."""
        env_file = PROJECT_ROOT / ".env"
        if not env_file.exists():
            pytest.skip(".env file does not exist")

        required_vars = _extract_env_vars_from_env_example(include_commented=False)
        env_vars = _extract_env_vars_from_file(PROJECT_ROOT / ".env")

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

        example_vars = _extract_env_vars_from_env_example(include_commented=True)
        env_vars = _extract_env_vars_from_file(PROJECT_ROOT / ".env")

        extra = env_vars - example_vars
        assert not extra, (
            f"Variables in .env but not in .env.example:\n"
            f"{sorted(extra)}\n\n"
            f"Either remove from .env or add to .env.example."
        )


# ---------------------------------------------------------------------------
# AC6 guard tests: prevent re-introduction of load_dotenv / os.environ
# ---------------------------------------------------------------------------

# Directories to scan for regression
_SRC_DIR = PROJECT_ROOT / "src" / "promptgrimoire"
_ALEMBIC_DIR = PROJECT_ROOT / "alembic"

# Legitimate os.environ usages (subprocess env passing, not config reading)
_ALLOWED_OS_ENVIRON = {
    # subprocess env pass-through
    _SRC_DIR / "db" / "bootstrap.py",
    # subprocess env override for test database
    _SRC_DIR / "cli.py",
}

_TESTS_DIR = PROJECT_ROOT / "tests"

# Test files that legitimately manipulate os.environ (setting, not reading config)
_ALLOWED_TEST_OS_ENVIRON_GET = {
    # conftest sets env vars to control Settings — legitimate infrastructure
    _TESTS_DIR / "conftest.py",
    # E2E conftest reads E2E_BASE_URL (set by test runner, not .env config)
    _TESTS_DIR / "e2e" / "conftest.py",
    # This file itself references os.environ in test assertions/comments
    _TESTS_DIR / "unit" / "test_env_vars.py",
}


def _scan_python_files(*dirs: Path) -> list[Path]:
    """Collect all .py files in directories."""
    files: list[Path] = []
    for d in dirs:
        files.extend(d.rglob("*.py"))
    return files


class TestNoDirectEnvAccess:
    """Structural guards preventing re-introduction of load_dotenv/os.environ.

    All configuration must flow through get_settings(). These tests
    catch regressions at commit time.
    """

    def test_no_load_dotenv_calls(self) -> None:
        """No load_dotenv() calls in application code or alembic (AC6.1)."""
        violations: list[str] = []
        for py_file in _scan_python_files(_SRC_DIR, _ALEMBIC_DIR):
            content = py_file.read_text()
            for i, line in enumerate(content.splitlines(), 1):
                if "load_dotenv" in line and not line.strip().startswith("#"):
                    violations.append(f"{py_file.relative_to(PROJECT_ROOT)}:{i}")

        assert not violations, (
            "load_dotenv() found in application code. "
            "Use get_settings() instead.\n" + "\n".join(violations)
        )

    def test_no_os_environ_get_in_app_code(self) -> None:
        """No os.environ.get() / os.getenv() for config reading (AC6.2).

        Legitimate subprocess env operations (env=dict(os.environ),
        os.environ[\"VAR\"] = ...) in allowlisted files are permitted.
        """
        config_read_patterns = re.compile(
            r"os\.environ\.get\(|os\.getenv\(|os\.environ\["
        )
        violations: list[str] = []

        for py_file in _scan_python_files(_SRC_DIR, _ALEMBIC_DIR):
            if py_file in _ALLOWED_OS_ENVIRON:
                continue
            content = py_file.read_text()
            for i, line in enumerate(content.splitlines(), 1):
                if line.strip().startswith("#"):
                    continue
                if config_read_patterns.search(line):
                    violations.append(f"{py_file.relative_to(PROJECT_ROOT)}:{i}")

        assert not violations, (
            "os.environ access found in application code. "
            "Use get_settings() instead.\n" + "\n".join(violations)
        )

    def test_no_os_environ_get_in_test_code(self) -> None:
        """No os.environ.get() / os.getenv() for config reading in tests.

        Test code should read configuration via Settings, not os.environ.
        conftest files that SET env vars for Settings are allowlisted.
        """
        config_read_patterns = re.compile(r"os\.environ\.get\(|os\.getenv\(")
        violations: list[str] = []

        for py_file in _scan_python_files(_TESTS_DIR):
            if py_file in _ALLOWED_TEST_OS_ENVIRON_GET:
                continue
            content = py_file.read_text()
            for i, line in enumerate(content.splitlines(), 1):
                if line.strip().startswith("#"):
                    continue
                if config_read_patterns.search(line):
                    violations.append(f"{py_file.relative_to(PROJECT_ROOT)}:{i}")

        assert not violations, (
            "os.environ.get() / os.getenv() found in test code. "
            "Use get_settings() or construct Settings() explicitly.\n"
            + "\n".join(violations)
        )

    def test_no_direct_dotenv_imports(self) -> None:
        """No direct 'from dotenv' or 'import dotenv' anywhere (AC6.3)."""
        dotenv_import = re.compile(r"^\s*(from dotenv|import dotenv)")
        violations: list[str] = []

        all_dirs = [_SRC_DIR, _ALEMBIC_DIR, PROJECT_ROOT / "tests"]
        for py_file in _scan_python_files(*all_dirs):
            content = py_file.read_text()
            for i, line in enumerate(content.splitlines(), 1):
                if dotenv_import.match(line):
                    violations.append(f"{py_file.relative_to(PROJECT_ROOT)}:{i}")

        assert not violations, (
            "Direct dotenv imports found. pydantic-settings reads "
            ".env natively — no load_dotenv() needed.\n" + "\n".join(violations)
        )
