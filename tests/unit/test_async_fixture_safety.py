"""Verify async fixtures use pytest_asyncio.fixture, not pytest.fixture.

Using @pytest.fixture on async functions causes 'Runner.run() cannot be called
from a running event loop' under pytest-xdist parallel execution. All async
fixtures MUST use @pytest_asyncio.fixture instead.

See: docs/implementation-plans/2026-02-04-database-test-nullpool/fix-async-subprocess.md
See: commit bb5307a (fix: use pytest_asyncio.fixture for async mock_stytch_client)
"""

import ast
from pathlib import Path

TESTS_DIR = Path(__file__).parent.parent


def _is_pytest_fixture_decorator(decorator: ast.expr) -> bool:
    """Check if decorator is @pytest.fixture or @pytest.fixture(...)."""
    # @pytest.fixture
    if (
        isinstance(decorator, ast.Attribute)
        and isinstance(decorator.value, ast.Name)
        and decorator.value.id == "pytest"
        and decorator.attr == "fixture"
    ):
        return True
    # @pytest.fixture(...)
    return (
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and isinstance(decorator.func.value, ast.Name)
        and decorator.func.value.id == "pytest"
        and decorator.func.attr == "fixture"
    )


def test_no_sync_decorator_on_async_fixtures() -> None:
    """Async fixtures must use @pytest_asyncio.fixture, not @pytest.fixture.

    @pytest.fixture on an async function causes Runner.run() event loop
    collisions under pytest-xdist parallel workers. This has bitten us
    multiple times (bb5307a, integration/conftest.py reset_db_engine_per_test).

    Fix: replace @pytest.fixture with @pytest_asyncio.fixture on any async def
    in test conftest or fixture files.
    """
    violations: list[str] = []

    for py_file in TESTS_DIR.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue

        content = py_file.read_text()
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                for decorator in node.decorator_list:
                    if _is_pytest_fixture_decorator(decorator):
                        rel = py_file.relative_to(TESTS_DIR)
                        violations.append(
                            f"{rel}:{decorator.lineno} - "
                            f"@pytest.fixture on async def {node.name}()"
                        )

    assert not violations, (
        "Async fixtures must use @pytest_asyncio.fixture, not @pytest.fixture.\n"
        "Using @pytest.fixture on async functions causes 'Runner.run() cannot be\n"
        "called from a running event loop' under pytest-xdist.\n\n"
        "Violations:\n" + "\n".join(f"  {v}" for v in violations)
    )
