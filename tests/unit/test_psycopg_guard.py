"""Guard test: no raw psycopg.connect() outside bootstrap.

E2E tests and scripts must use SQLAlchemy (via db_fixtures._get_sync_engine or
create_engine with DATABASE__URL) for database access. Raw psycopg is only
permitted in bootstrap.py (CREATE DATABASE requires connecting to the postgres
maintenance DB) and its integration tests.
"""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

# Directories to scan for violations
SCAN_DIRS = [
    PROJECT_ROOT / "tests" / "e2e",
    PROJECT_ROOT / "scripts",
]

# Files allowed to use psycopg (bootstrap and its tests)
ALLOWED_FILES = {
    PROJECT_ROOT / "src" / "promptgrimoire" / "db" / "bootstrap.py",
    PROJECT_ROOT / "tests" / "integration" / "test_settings_db.py",
    PROJECT_ROOT / "tests" / "integration" / "test_db_cloning.py",
}


def _find_psycopg_imports(tree: ast.AST) -> list[int]:
    """Find line numbers of `import psycopg` or `from psycopg import ...`."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "psycopg" or alias.name.startswith("psycopg."):
                    lines.append(node.lineno)
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and (node.module == "psycopg" or node.module.startswith("psycopg."))
        ):
            lines.append(node.lineno)
    return lines


def test_no_psycopg_in_e2e_or_scripts() -> None:
    """E2E tests and scripts must not import psycopg directly.

    Use SQLAlchemy with DATABASE__URL instead (see db_fixtures._get_sync_engine).
    """
    violations: list[str] = []

    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for py_file in scan_dir.rglob("*.py"):
            if py_file.resolve() in {f.resolve() for f in ALLOWED_FILES}:
                continue

            try:
                tree = ast.parse(py_file.read_text())
            except SyntaxError:
                continue

            for lineno in _find_psycopg_imports(tree):
                rel = py_file.relative_to(PROJECT_ROOT)
                violations.append(
                    f"{rel}:{lineno} — psycopg import; "
                    "use SQLAlchemy with DATABASE__URL instead"
                )

    assert not violations, (
        "Raw psycopg imports found outside bootstrap.\n"
        "Use SQLAlchemy (db_fixtures._get_sync_engine or create_engine) instead.\n\n"
        "Violations:\n" + "\n".join(f"  {v}" for v in violations)
    )
