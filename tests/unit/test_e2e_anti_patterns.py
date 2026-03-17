"""AST guards for E2E anti-patterns that cause flaky tests.

Scans test and source files for patterns that have caused race conditions
and flakes. Each guard encodes a lesson learned the hard way.

Suppression: Add ``# noqa: PG0xx`` to the offending line to suppress
a specific guard.  The noqa code must match:
- PG001 — fixed sleeps (wait_for_timeout, asyncio.sleep)
- PG002 — text-based locators (get_by_text, get_by_role, get_by_placeholder)
- PG003 — hardcoded char offsets in select_chars / create_highlight_with_tag
- PG004 — invoke_callback inside _handle_client_delete
- PG005 — sync element access without _should_see_testid gate (NiceGUI)

Guard 1 (PG001) — wait_for_timeout / asyncio.sleep: Fixed timeouts in
E2E tests are never reliable under parallel execution.  Use condition-based
waits instead.  See: test_edit_mode.py flake (2026-03-12).

Guard 2 (PG002) — get_by_text / get_by_role / get_by_placeholder: E2E
tests must use data-testid locators (get_by_test_id).  Text-based locators
break on copy changes and are ambiguous.
See: docs/testing.md § E2E Locator Convention.

Guard 3 (PG003) — Hardcoded char offsets: select_chars(page, 0, 10) is
brittle — char offsets change when fixture HTML changes.  Use
find_text_range("needle") instead.  See: docs/testing.md.

Guard 4 (PG004) — invoke_callback inside _handle_client_delete:
CLIENT_DELETE events must NOT trigger a full refresh_annotations() rebuild.
Use invoke_peer_left() instead.
See: commit 43d644b8, docs/annotation-architecture.md.
"""

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
_E2E_DIR = _REPO_ROOT / "tests" / "e2e"
_SRC_DIR = _REPO_ROOT / "src"


def _iter_py_files(directory: Path):
    """Yield .py files, skipping __pycache__."""
    for py_file in directory.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        yield py_file


def _parse_file(py_file: Path) -> ast.Module | None:
    """Parse a Python file, returning None on SyntaxError."""
    try:
        return ast.parse(py_file.read_text())
    except SyntaxError:
        return None


def _has_noqa(source_lines: list[str], lineno: int, code: str) -> bool:
    """Check if a source line has a ``# noqa: <code>`` suppression."""
    if lineno < 1 or lineno > len(source_lines):
        return False
    line = source_lines[lineno - 1]
    return f"noqa: {code}" in line or ("noqa" in line and code in line)


def _collect_violations(
    directory: Path,
    checker,
    noqa_code: str,
) -> list[str]:
    """Walk E2E files and collect violations, respecting noqa comments."""
    violations: list[str] = []

    for py_file in _iter_py_files(directory):
        tree = _parse_file(py_file)
        if tree is None:
            continue

        source_lines = py_file.read_text().splitlines()

        for node in ast.walk(tree):
            desc = checker(node)
            if desc is None or not hasattr(node, "lineno"):
                continue
            lineno: int = node.lineno  # type: ignore[union-attr]
            if not _has_noqa(source_lines, lineno, noqa_code):
                rel = py_file.relative_to(_REPO_ROOT)
                violations.append(f"{rel}:{lineno} - {desc}")

    return sorted(violations)


# ---------------------------------------------------------------------------
# Guard 1 (PG001): No fixed sleeps in E2E tests
# ---------------------------------------------------------------------------

_BANNED_SLEEP_METHODS = frozenset({"wait_for_timeout"})


def _check_fixed_sleep(node: ast.AST) -> str | None:
    """Return description if node is a fixed-sleep call, else None."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in _BANNED_SLEEP_METHODS:
        return f"{func.attr}()"
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "asyncio"
        and func.attr == "sleep"
    ):
        return "asyncio.sleep()"
    return None


def test_no_fixed_sleeps_in_e2e() -> None:
    """E2E tests must not use wait_for_timeout() or asyncio.sleep() (PG001).

    Fixed timeouts are unreliable under parallel execution.  They pass
    locally but flake in CI or when the machine is under load.

    Instead, wait for an observable condition:
    - expect(locator).to_be_visible()          — element appears
    - expect(locator).to_have_count(n)         — element count changes
    - page.wait_for_function("() => ...")       — JS condition
    - page.wait_for_url(pattern)               — navigation completes
    - wait_for_text_walker(page)               — text walker ready

    Suppress with: # noqa: PG001
    """
    violations = _collect_violations(_E2E_DIR, _check_fixed_sleep, "PG001")

    assert not violations, (
        "E2E tests must not use fixed sleeps (wait_for_timeout, asyncio.sleep).\n"
        "Use condition-based waits instead (expect, wait_for_function, etc.).\n"
        "Suppress with: # noqa: PG001\n\n"
        "Violations:\n" + "\n".join(f"  {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# Guard 2 (PG002): No text/role/placeholder locators in E2E tests
# ---------------------------------------------------------------------------

_BANNED_LOCATOR_METHODS = frozenset(
    {
        "get_by_text",
        "get_by_role",
        "get_by_placeholder",
    }
)


def _check_text_locator(node: ast.AST) -> str | None:
    """Return description if node uses a banned locator method, else None."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in _BANNED_LOCATOR_METHODS:
        return f"{func.attr}()"
    return None


def test_no_text_based_locators_in_e2e() -> None:
    """E2E tests must use get_by_test_id(), not text-based locators (PG002).

    Text-based locators break when copy changes, fail across locales,
    and are ambiguous when multiple elements share text.  All interactable
    UI elements must have data-testid attributes.

    Fix: Add data-testid to the element in the source, then use
    page.get_by_test_id("my-element") in the test.

    Suppress with: # noqa: PG002

    See: CLAUDE.md § E2E Locator Convention
    """
    violations = _collect_violations(_E2E_DIR, _check_text_locator, "PG002")

    assert not violations, (
        "E2E tests must use get_by_test_id(), not text-based locators.\n"
        "Text locators break on copy changes and are ambiguous.\n"
        "Suppress with: # noqa: PG002\n\n"
        "Violations:\n" + "\n".join(f"  {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# Guard 3 (PG003): No hardcoded char offsets in highlight selectors
# ---------------------------------------------------------------------------

_CHAR_OFFSET_FUNCTIONS = frozenset({"select_chars", "create_highlight_with_tag"})


def _check_hardcoded_char_offset(node: ast.AST) -> str | None:
    """Return description if node calls select_chars with literal int args.

    Good: select_chars(page, *find_text_range(page, "word"))
    Bad:  select_chars(page, 0, 10)
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func

    # Match both bare name and attribute access (module.func)
    func_name: str | None = None
    if isinstance(func, ast.Name) and func.id in _CHAR_OFFSET_FUNCTIONS:
        func_name = func.id
    elif isinstance(func, ast.Attribute) and func.attr in _CHAR_OFFSET_FUNCTIONS:
        func_name = func.attr

    if func_name is None:
        return None

    # Check positional args after the first (page).
    # If any positional arg (after page) is a literal int, flag it.
    # Starred args like *find_text_range() are fine — ast.Starred.
    pos_args = node.args[1:]  # skip page arg
    for arg in pos_args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
            return f"{func_name}() with hardcoded char offset"

    return None


def test_no_hardcoded_char_offsets_in_e2e() -> None:
    """Highlight selectors must use find_text_range(), not literal offsets (PG003).

    Hardcoded char offsets like select_chars(page, 0, 10) break when
    fixture HTML changes.  Use find_text_range("needle") to locate text
    by content instead.

    Good: select_chars(page, *find_text_range(page, "plaintiff"))
    Bad:  select_chars(page, 0, 10)

    Suppress with: # noqa: PG003
    """
    violations = _collect_violations(_E2E_DIR, _check_hardcoded_char_offset, "PG003")

    assert not violations, (
        "Highlight selectors must use find_text_range(), not literal char offsets.\n"
        "Hardcoded offsets break when fixture HTML changes.\n"
        "Suppress with: # noqa: PG003\n\n"
        "Violations:\n" + "\n".join(f"  {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# Guard 4 (PG004): _handle_client_delete must not call invoke_callback
# ---------------------------------------------------------------------------


def test_client_delete_uses_peer_left_not_callback() -> None:
    """_handle_client_delete must call invoke_peer_left, NOT invoke_callback (PG004).

    CLIENT_DELETE events mean a peer disconnected.  They change zero CRDT
    state.  Calling invoke_callback() triggers refresh_annotations() which
    does a full DOM rebuild — this races with in-flight user interactions
    (fill + click), destroying input values and button handlers mid-action.

    invoke_peer_left() only updates the user count display.

    See: commit 43d644b8 (fix: use lightweight peer-left callback)
    See: docs/annotation-architecture.md
    """
    broadcast_file = (
        _SRC_DIR / "promptgrimoire" / "pages" / "annotation" / "broadcast.py"
    )
    assert broadcast_file.exists(), f"Cannot find {broadcast_file}"

    tree = _parse_file(broadcast_file)
    assert tree is not None, f"Cannot parse {broadcast_file}"

    delete_fn: ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_handle_client_delete"
        ):
            delete_fn = node
            break

    assert delete_fn is not None, (
        "_handle_client_delete function not found in broadcast.py"
    )

    violations: list[str] = []
    for node in ast.walk(delete_fn):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "invoke_callback":
                violations.append(
                    f"broadcast.py:{node.lineno} - "
                    "invoke_callback() inside _handle_client_delete"
                )

    assert not violations, (
        "_handle_client_delete must use invoke_peer_left(), NOT invoke_callback().\n"
        "invoke_callback() triggers full DOM rebuild which races with user input.\n"
        "See: commit 43d644b8\n\n"
        "Violations:\n" + "\n".join(f"  {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# Guard 5 (PG005): Sync element access needs _should_see_testid gate
# ---------------------------------------------------------------------------

_INTEGRATION_DIR = _REPO_ROOT / "tests" / "integration"

_SYNC_ACCESS_FUNCTIONS = frozenset({"_set_input_value", "_click_testid"})


def _extract_testid_arg(node: ast.Call) -> str | None:
    """Extract the testid string from a helper call.

    Pattern: ``_set_input_value(user, "testid", value)`` or
    ``_click_testid(user, "testid")``.  Returns the second
    positional argument if it is a string literal.
    """
    if len(node.args) < 2:
        return None
    arg = node.args[1]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    # f-string testids (e.g. f"group-add-tag-btn-{id}") are dynamic —
    # can't statically match them to _should_see_testid calls.
    return None


def _iter_calls_in_order(node: ast.AST) -> list[ast.Call]:
    """Collect all Call nodes in source order (by line number).

    ``ast.walk`` does not guarantee traversal order.  This function
    collects every ``ast.Call`` in the subtree, then sorts by line
    number to ensure gates are seen before the accesses they protect.
    """
    calls: list[ast.Call] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and hasattr(child, "lineno"):
            calls.append(child)
    calls.sort(key=lambda c: (c.lineno, c.col_offset))
    return calls


def _check_ungated_sync_access(
    func_node: ast.AsyncFunctionDef,
    source_lines: list[str],
) -> list[tuple[int, str]]:
    """Find sync element accesses not preceded by _should_see_testid.

    Returns list of (lineno, description) for violations.
    """
    gated: set[str] = set()
    violations: list[tuple[int, str]] = []

    for node in _iter_calls_in_order(func_node):
        func = node.func

        # Check for _should_see_testid(user, "testid")
        if isinstance(func, ast.Name) and func.id == "_should_see_testid":
            testid = _extract_testid_arg(node)
            if testid:
                gated.add(testid)

        # Check for _set_input_value / _click_testid
        if isinstance(func, ast.Name) and func.id in _SYNC_ACCESS_FUNCTIONS:
            testid = _extract_testid_arg(node)
            if testid is None:
                # Dynamic testid — can't check statically, skip
                continue
            if testid not in gated:
                lineno = node.lineno
                if _has_noqa(source_lines, lineno, "PG005"):
                    continue
                violations.append(
                    (
                        lineno,
                        f"{func.id}(_, {testid!r}) without "
                        f"preceding _should_see_testid gate",
                    )
                )

    return violations


def test_nicegui_sync_access_has_testid_gate() -> None:
    """NiceGUI sync element access must be preceded by _should_see_testid (PG005).

    ``_set_input_value`` and ``_click_testid`` are synchronous — they
    do not yield to the event loop.  If an async page handler has not
    finished rendering the target element, these calls fail.

    ``_should_see_testid`` polls with ``await asyncio.sleep()`` which
    yields to the event loop, letting pending async renders complete.

    Every ``_set_input_value(user, "X", ...)`` and
    ``_click_testid(user, "X")`` must be preceded (in the same test
    function) by ``await _should_see_testid(user, "X")``.

    See: 2026-03-17 CI failure — TestEnrollStudent.test_enroll_student
    Suppress with: # noqa: PG005
    """
    all_violations: list[str] = []

    for py_file in _iter_py_files(_INTEGRATION_DIR):
        tree = _parse_file(py_file)
        if tree is None:
            continue

        source_lines = py_file.read_text().splitlines()

        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue

            violations = _check_ungated_sync_access(node, source_lines)
            rel = py_file.relative_to(_REPO_ROOT)
            for lineno, desc in violations:
                all_violations.append(f"{rel}:{lineno} - {desc}")

    assert not all_violations, (
        "NiceGUI integration tests: sync element access without "
        "_should_see_testid gate.\n"
        "_set_input_value / _click_testid are synchronous and will "
        "fail if the async page handler\n"
        "hasn't finished rendering. Add: await _should_see_testid"
        '(user, "testid") before access.\n'
        "Suppress with: # noqa: PG005\n\n"
        "Violations:\n" + "\n".join(f"  {v}" for v in all_violations)
    )
