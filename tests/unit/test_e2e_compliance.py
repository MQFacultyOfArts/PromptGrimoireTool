"""Verify E2E tests comply with CLAUDE.md guidelines.

The JS-injection policy and its allowlist live in
``scripts/check_js_injection.py`` (single source, also run by
pre-commit on changed files). This test enforces it whole-tree in the
unit lane and falsification-checks that the guard actually fires.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "check_js_injection.py"
_spec = importlib.util.spec_from_file_location("check_js_injection", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _swap_e2e_dir(fake_dir: Path, files: list[Path]) -> list[str]:
    """Run find_violations with E2E_DIR pointed at *fake_dir*."""
    original = getattr(_mod, "E2E_DIR")  # noqa: B009 -- dynamic module loaded via importlib
    setattr(_mod, "E2E_DIR", fake_dir)  # noqa: B010 -- dynamic module loaded via importlib
    try:
        return list(_mod.find_violations(files))
    finally:
        setattr(_mod, "E2E_DIR", original)  # noqa: B010 -- dynamic module loaded via importlib


def test_no_js_injection_in_e2e_tests() -> None:
    """E2E test code must not execute browser JS without a listed reason.

    Per CLAUDE.md: E2E tests simulate real user behaviour through
    Playwright events. Exceptions require a documented reason in
    ``ALLOWED_JS_FILES`` (scripts/check_js_injection.py). Helper
    modules are scanned too — the pattern concentrates there.
    """
    violations = _mod.find_violations()
    assert not violations, (
        "JS injection in E2E test code without a listed reason.\n"
        "Fix the site or add the file to ALLOWED_JS_FILES with a specific "
        "written reason (scripts/check_js_injection.py):\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def test_guard_fires_on_injection_shapes(tmp_path: Path) -> None:
    """Falsification: the guard flags spy/injection shapes it exists to catch.

    Writes a file containing the emitEvent-spy shape (caught in the wild
    2026-08-17) plus an add_init_script into a fake e2e dir and asserts
    the checker reports both. Guards the guard: if the scan logic or
    method list regresses, this goes red.
    """
    probe = tmp_path / "test_probe.py"
    probe.write_text(
        "def test_spy(page):\n"
        '    page.evaluate("() => { window.emitEvent = function(){}; }")\n'
        '    page.add_init_script("window.__x = 1;")\n'
    )
    violations = _swap_e2e_dir(tmp_path, [probe])

    assert any("evaluate()" in v for v in violations)
    assert any("add_init_script()" in v for v in violations)


def test_allowlisted_file_is_exempt(tmp_path: Path) -> None:
    """An ALLOWED_JS_FILES entry sanctions its file — and only its file."""
    allowed = tmp_path / "test_tag_colour.py"  # real allowlist name
    allowed.write_text('def test_x(page):\n    page.evaluate("() => 1")\n')
    other = tmp_path / "test_other.py"
    other.write_text('def test_y(page):\n    page.evaluate("() => 1")\n')

    violations = _swap_e2e_dir(tmp_path, [allowed, other])

    assert violations == ["test_other.py:2 - evaluate()"]
