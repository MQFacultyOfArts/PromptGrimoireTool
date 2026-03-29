"""Guard test: console log handler must not leak PII via show_locals.

The structlog ConsoleRenderer defaults to RichTracebackFormatter(show_locals=True),
which dumps all local variables from exception stack frames into the log output.
For a web app handling student data, this leaks PII (names, emails, document
content) into systemd journal and stderr.

This guard ensures:
1. show_locals is disabled on ConsoleRenderer's exception formatter
2. Non-TTY stderr produces JSON (not ANSI-coloured rich output)

See: incident 2026-03-21 — student PII found in journal via show_locals dumps.
"""

import ast
from pathlib import Path

import structlog

SRC_FILE = (
    Path(__file__).parent.parent.parent / "src" / "promptgrimoire" / "logging_config.py"
)


def test_console_renderer_show_locals_disabled_in_source() -> None:
    """ConsoleRenderer must pass show_locals=False to RichTracebackFormatter.

    AST-level guard: scans __init__.py for ConsoleRenderer instantiation and
    verifies that exception_formatter is constructed with show_locals=False.
    """
    tree = ast.parse(SRC_FILE.read_text())

    # Find all ConsoleRenderer(...) calls
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "ConsoleRenderer"
        ):
            continue

        # Look for exception_formatter keyword arg
        for kw in node.keywords:
            if kw.arg == "exception_formatter":
                # Should be RichTracebackFormatter(show_locals=False)
                inner = kw.value
                assert isinstance(inner, ast.Call), (
                    f"Line {node.lineno}: exception_formatter must be a "
                    f"RichTracebackFormatter(...) call"
                )
                for inner_kw in inner.keywords:
                    if inner_kw.arg == "show_locals":
                        assert isinstance(inner_kw.value, ast.Constant), (
                            f"Line {node.lineno}: show_locals must be a literal False"
                        )
                        assert inner_kw.value.value is False, (
                            f"Line {node.lineno}: show_locals must be False "
                            f"to prevent PII leakage in tracebacks. "
                            f"Got: {inner_kw.value.value}"
                        )
                        return  # Found and verified

    # If we get here, either no ConsoleRenderer or no show_locals override
    # Check that ConsoleRenderer exists at all (it should for TTY mode)
    has_console_renderer = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "ConsoleRenderer"
        for node in ast.walk(tree)
    )
    if has_console_renderer:
        raise AssertionError(
            "ConsoleRenderer found but show_locals not explicitly set to False. "
            "The default is show_locals=True which leaks PII."
        )


def test_non_tty_stderr_uses_json_renderer() -> None:
    """When stderr is not a TTY, console handler must use JSONRenderer.

    This prevents ANSI escape codes, rich box-drawing characters, and
    show_locals dumps from contaminating systemd journal output.
    """
    tree = ast.parse(SRC_FILE.read_text())

    # Find the isatty() branch — there should be an if/else that selects
    # between ConsoleRenderer (TTY) and JSONRenderer (non-TTY)
    found_tty_guard = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            # Check if the test involves isatty()
            test_src = ast.dump(node.test)
            if "isatty" in test_src:
                found_tty_guard = True
                # The else branch should contain JSONRenderer
                else_src = ast.dump(ast.Module(body=node.orelse, type_ignores=[]))
                assert "JSONRenderer" in else_src, (
                    "Non-TTY branch must use JSONRenderer, not ConsoleRenderer"
                )
                break

    assert found_tty_guard, (
        "No sys.stderr.isatty() guard found in logging setup. "
        "Console handler must check for TTY to avoid ANSI/rich output "
        "in systemd journal."
    )


def test_json_output_excludes_locals_on_exception() -> None:
    """JSONRenderer with format_exc_info must not include local variables.

    Functional test: raise an exception with PII in local scope, format it
    through the JSON pipeline, and verify no PII appears in the output.
    """
    import json
    import logging
    from io import StringIO

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )

    buf = StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(formatter)

    test_logger = logging.getLogger("test_pii_guard")
    test_logger.handlers.clear()
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.DEBUG)

    # Simulate a handler with student PII in local scope
    try:
        student_name = "Molly Jinks"  # noqa: F841
        student_email = "molly.jinks@students.example.edu"  # noqa: F841
        workspace_data = {"tags": [{"author": "Molly Jinks"}]}  # noqa: F841
        raise RuntimeError("export failure simulation")
    except RuntimeError:
        test_logger.error("Failed to export PDF", exc_info=True)

    output = buf.getvalue()

    # Must be valid JSON
    parsed = json.loads(output.strip())
    assert parsed["event"] == "Failed to export PDF"

    # Must not contain PII
    assert "Molly" not in output, f"Student name leaked into log output: {output}"
    assert "students.example.edu" not in output, f"Email leaked: {output}"

    # Must not contain ANSI
    assert "\x1b[" not in output, f"ANSI codes in output: {output}"

    # Traceback should be present but plain (no locals)
    exc_text = parsed.get("exception", "")
    assert "RuntimeError: export failure simulation" in exc_text
    assert "student_name" not in exc_text, "Local variable name leaked"
