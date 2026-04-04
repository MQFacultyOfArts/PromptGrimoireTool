"""Tests for export pipeline structured logging instrumentation.

Verifies ACs:
- structured-logging-339.AC3.1: Export produces log events for each stage
  (pandoc_convert, tex_generate, latex_compile, export_complete) with
  export_id, export_stage, stage_duration_ms
- structured-logging-339.AC3.2: All stage events share the same export_id
- structured-logging-339.AC3.3: LaTeX compilation failure produces log event
  with latex_errors containing extracted !-prefixed lines
- structured-logging-339.AC3.4: Successful export includes font_fallbacks
  field with detect_scripts() result
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest
import structlog

from promptgrimoire.export.pdf import reset_compile_semaphore

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _reset_semaphore() -> None:
    """Ensure a fresh semaphore — prevents cross-test leakage under xdist."""
    reset_compile_semaphore()


# ---------------------------------------------------------------------------
# Log-capture helpers
# ---------------------------------------------------------------------------


def _setup_json_logging(tmp_path: Path) -> Path:
    """Set up structlog + stdlib JSON logging to a temp file.

    Returns the log file path.
    """
    from promptgrimoire.config import AppConfig, DevConfig, Settings
    from promptgrimoire.logging_config import setup_logging

    # Reset logging first
    root = logging.getLogger()
    for handler in root.handlers[:]:
        handler.close()
        root.removeHandler(handler)
    structlog.reset_defaults()

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]  # pydantic-settings private init arg
        app=AppConfig(log_dir=tmp_path),
        dev=DevConfig(branch_db_suffix=False),
    )
    with (
        patch(
            "promptgrimoire.logging_config._get_settings_for_logging",
            return_value=settings,
        ),
        patch(
            "promptgrimoire.logging_config._get_current_branch_for_logging",
            return_value="main",
        ),
        patch(
            "promptgrimoire.logging_config._branch_db_suffix_for_logging",
            return_value="",
        ),
    ):
        setup_logging()

    return tmp_path / "promptgrimoire.jsonl"


def _flush_and_read_all(log_file: Path) -> list[dict[str, Any]]:
    """Flush all handlers and return all JSON log lines."""
    for h in logging.getLogger().handlers:
        h.flush()
    lines = [ln for ln in log_file.read_text().splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def _reset_logging() -> None:
    root = logging.getLogger()
    for handler in root.handlers[:]:
        handler.close()
        root.removeHandler(handler)
    structlog.reset_defaults()


@pytest.fixture(autouse=True)
def _clean_logging():
    _reset_logging()
    yield
    _reset_logging()
    structlog.contextvars.clear_contextvars()


# ---------------------------------------------------------------------------
# AC3.1 + AC3.2: Export stage timing and correlation
# ---------------------------------------------------------------------------


class TestExportStageTiming:
    """AC3.1: Stage events with export_id, export_stage, stage_duration_ms.

    AC3.2: All stage events share the same export_id.
    """

    async def test_export_produces_four_stage_events(self, tmp_path: Path) -> None:
        """AC3.1: Successful export logs pandoc_convert, tex_generate,
        latex_compile, export_complete stages."""
        log_file = _setup_json_logging(tmp_path)

        # Create a minimal but valid export environment
        output_dir = tmp_path / "export_out"
        output_dir.mkdir()

        # Mock compile_latex to return a fake PDF path (avoid real latexmk)
        fake_pdf = output_dir / "annotated_document.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 fake")

        with patch(
            "promptgrimoire.export.pdf_export.compile_latex",
            new_callable=AsyncMock,
            return_value=fake_pdf,
        ):
            from promptgrimoire.export.pdf_export import export_annotation_pdf

            await export_annotation_pdf(
                html_content="<p>Hello world</p>",
                highlights=[],
                tag_colours={},
                output_dir=output_dir,
            )

        all_events = _flush_and_read_all(log_file)
        stage_events = [e for e in all_events if e.get("export_stage") is not None]

        expected_stages = {
            "pandoc_convert",
            "tex_generate",
            "latex_compile",
        }
        actual_stages = {e["export_stage"] for e in stage_events}
        assert expected_stages <= actual_stages, (
            f"Missing stages: {expected_stages - actual_stages}"
        )

        # Verify export_complete event exists
        complete_events = [e for e in all_events if e.get("event") == "export_complete"]
        assert len(complete_events) == 1, "Expected one export_complete event"

        for ev in stage_events:
            assert "export_id" in ev, f"Missing export_id in {ev['export_stage']}"
            assert "stage_duration_ms" in ev, (
                f"Missing stage_duration_ms in {ev['export_stage']}"
            )
            assert isinstance(ev["stage_duration_ms"], int), (
                f"stage_duration_ms should be int, got {type(ev['stage_duration_ms'])}"
            )

    async def test_all_stages_share_same_export_id(self, tmp_path: Path) -> None:
        """AC3.2: All stage events for one export share the same export_id."""
        log_file = _setup_json_logging(tmp_path)

        output_dir = tmp_path / "export_out"
        output_dir.mkdir()

        fake_pdf = output_dir / "annotated_document.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 fake")

        with patch(
            "promptgrimoire.export.pdf_export.compile_latex",
            new_callable=AsyncMock,
            return_value=fake_pdf,
        ):
            from promptgrimoire.export.pdf_export import export_annotation_pdf

            await export_annotation_pdf(
                html_content="<p>Hello world</p>",
                highlights=[],
                tag_colours={},
                output_dir=output_dir,
            )

        all_events = _flush_and_read_all(log_file)
        stage_events = [e for e in all_events if e.get("export_stage") is not None]

        export_ids = {e["export_id"] for e in stage_events}
        assert len(export_ids) == 1, (
            f"Expected one export_id across all stages, got {export_ids}"
        )

    async def test_stage_duration_is_nonnegative(self, tmp_path: Path) -> None:
        """stage_duration_ms should be >= 0."""
        log_file = _setup_json_logging(tmp_path)

        output_dir = tmp_path / "export_out"
        output_dir.mkdir()

        fake_pdf = output_dir / "annotated_document.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 fake")

        with patch(
            "promptgrimoire.export.pdf_export.compile_latex",
            new_callable=AsyncMock,
            return_value=fake_pdf,
        ):
            from promptgrimoire.export.pdf_export import export_annotation_pdf

            await export_annotation_pdf(
                html_content="<p>Hello world</p>",
                highlights=[],
                tag_colours={},
                output_dir=output_dir,
            )

        all_events = _flush_and_read_all(log_file)
        stage_events = [e for e in all_events if e.get("export_stage") is not None]

        for ev in stage_events:
            duration = ev["stage_duration_ms"]
            assert isinstance(duration, int)
            assert duration >= 0


# ---------------------------------------------------------------------------
# AC3.3: LaTeX error extraction
# ---------------------------------------------------------------------------


class TestLatexErrorExtraction:
    """AC3.3: LaTeX compilation failure produces latex_errors field."""

    async def test_latex_errors_extracted_from_log(self, tmp_path: Path) -> None:
        """AC3.3: compile_latex failure logs extracted !-prefixed error lines."""
        log_file = _setup_json_logging(tmp_path)

        from promptgrimoire.export.pdf import LaTeXCompilationError

        # Create a fake .tex file and .log file with errors
        tex_path = tmp_path / "test.tex"
        tex_path.write_text(r"\documentclass{article}\begin{document}\end{document}")

        log_path = tmp_path / "test.log"
        log_path.write_text(
            "This is pdfTeX, Version 3.14159265\n"
            "! Undefined control sequence.\n"
            "l.42 \\badcommand\n"
            "! Missing $ inserted.\n"
            "some other line\n"
        )

        # Mock the subprocess to fail
        with (
            patch(
                "promptgrimoire.export.pdf.get_latexmk_path",
                return_value="/usr/bin/latexmk",
            ),
            patch(
                "promptgrimoire.export.pdf.asyncio.create_subprocess_exec",
            ) as mock_exec,
        ):
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (
                b"stdout content",
                b"stderr content",
            )
            mock_proc.returncode = 1
            mock_exec.return_value = mock_proc

            with pytest.raises(LaTeXCompilationError):
                from promptgrimoire.export.pdf import compile_latex

                await compile_latex(tex_path, output_dir=tmp_path)

        all_events = _flush_and_read_all(log_file)
        error_events = [e for e in all_events if e.get("latex_errors") is not None]

        assert len(error_events) >= 1
        latex_errors = error_events[0]["latex_errors"]
        assert isinstance(latex_errors, list)
        assert len(latex_errors) == 2
        assert "! Undefined control sequence." in latex_errors
        assert "! Missing $ inserted." in latex_errors

    async def test_latex_errors_empty_when_no_bang_lines(self, tmp_path: Path) -> None:
        """When log has no !-prefixed lines, latex_errors is empty list."""
        log_file = _setup_json_logging(tmp_path)

        from promptgrimoire.export.pdf import LaTeXCompilationError

        tex_path = tmp_path / "test.tex"
        tex_path.write_text(r"\documentclass{article}\begin{document}\end{document}")

        log_path = tmp_path / "test.log"
        log_path.write_text("This is pdfTeX\nNo errors here\n")

        with (
            patch(
                "promptgrimoire.export.pdf.get_latexmk_path",
                return_value="/usr/bin/latexmk",
            ),
            patch(
                "promptgrimoire.export.pdf.asyncio.create_subprocess_exec",
            ) as mock_exec,
        ):
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 1
            mock_exec.return_value = mock_proc

            with pytest.raises(LaTeXCompilationError):
                from promptgrimoire.export.pdf import compile_latex

                await compile_latex(tex_path, output_dir=tmp_path)

        all_events = _flush_and_read_all(log_file)
        error_events = [e for e in all_events if e.get("latex_errors") is not None]
        assert len(error_events) >= 1
        assert error_events[0]["latex_errors"] == []


# ---------------------------------------------------------------------------
# AC3.4: Font fallback logging
# ---------------------------------------------------------------------------


class TestFontFallbackLogging:
    """AC3.4: Successful export includes font_fallbacks field."""

    async def test_font_fallbacks_logged_on_success(self, tmp_path: Path) -> None:
        """AC3.4: Successful export logs font_fallbacks from detect_scripts()."""
        log_file = _setup_json_logging(tmp_path)

        output_dir = tmp_path / "export_out"
        output_dir.mkdir()

        fake_pdf = output_dir / "annotated_document.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 fake")

        with patch(
            "promptgrimoire.export.pdf_export.compile_latex",
            new_callable=AsyncMock,
            return_value=fake_pdf,
        ):
            from promptgrimoire.export.pdf_export import export_annotation_pdf

            await export_annotation_pdf(
                html_content="<p>Hello world</p>",
                highlights=[],
                tag_colours={},
                output_dir=output_dir,
            )

        all_events = _flush_and_read_all(log_file)
        font_events = [e for e in all_events if e.get("font_fallbacks") is not None]

        assert len(font_events) >= 1
        assert isinstance(font_events[0]["font_fallbacks"], list)

    async def test_font_fallbacks_detects_cjk(self, tmp_path: Path) -> None:
        """AC3.4: CJK content produces non-empty font_fallbacks."""
        log_file = _setup_json_logging(tmp_path)

        output_dir = tmp_path / "export_out"
        output_dir.mkdir()

        fake_pdf = output_dir / "annotated_document.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 fake")

        # Include Japanese text that triggers CJK detection
        with patch(
            "promptgrimoire.export.pdf_export.compile_latex",
            new_callable=AsyncMock,
            return_value=fake_pdf,
        ):
            from promptgrimoire.export.pdf_export import export_annotation_pdf

            await export_annotation_pdf(
                html_content="<p>Hello \u3053\u3093\u306b\u3061\u306f</p>",
                highlights=[],
                tag_colours={},
                output_dir=output_dir,
            )

        all_events = _flush_and_read_all(log_file)
        font_events = [e for e in all_events if e.get("font_fallbacks") is not None]

        assert len(font_events) >= 1
        fallbacks = font_events[0]["font_fallbacks"]
        assert isinstance(fallbacks, list)
        assert len(fallbacks) > 0  # CJK should trigger font fallbacks


# ---------------------------------------------------------------------------
# Task 4: Subprocess output capture
# ---------------------------------------------------------------------------


class TestSubprocessOutputCapture:
    """Subprocess stdout/stderr captured and logged on failure."""

    async def test_subprocess_output_logged_on_failure(self, tmp_path: Path) -> None:
        """On compile failure, stdout/stderr appear in structured log."""
        log_file = _setup_json_logging(tmp_path)

        from promptgrimoire.export.pdf import LaTeXCompilationError

        tex_path = tmp_path / "test.tex"
        tex_path.write_text(r"\documentclass{article}\begin{document}\end{document}")

        log_path = tmp_path / "test.log"
        log_path.write_text("! Fatal error occurred\n")

        with (
            patch(
                "promptgrimoire.export.pdf.get_latexmk_path",
                return_value="/usr/bin/latexmk",
            ),
            patch(
                "promptgrimoire.export.pdf.asyncio.create_subprocess_exec",
            ) as mock_exec,
        ):
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (
                b"latexmk stdout output here",
                b"latexmk stderr output here",
            )
            mock_proc.returncode = 1
            mock_exec.return_value = mock_proc

            with pytest.raises(LaTeXCompilationError):
                from promptgrimoire.export.pdf import compile_latex

                await compile_latex(tex_path, output_dir=tmp_path)

        all_events = _flush_and_read_all(log_file)
        subprocess_events = [e for e in all_events if e.get("latex_stdout") is not None]

        assert len(subprocess_events) >= 1
        ev = subprocess_events[0]
        assert "latexmk stdout output here" in str(ev["latex_stdout"])
        assert "latexmk stderr output here" in str(ev["latex_stderr"])
        assert ev["return_code"] == 1

    async def test_subprocess_output_truncated_to_4k(self, tmp_path: Path) -> None:
        """Subprocess output is truncated to last 4096 chars."""
        log_file = _setup_json_logging(tmp_path)

        from promptgrimoire.export.pdf import LaTeXCompilationError

        tex_path = tmp_path / "test.tex"
        tex_path.write_text(r"\documentclass{article}\begin{document}\end{document}")

        log_path = tmp_path / "test.log"
        log_path.write_text("! error\n")

        big_output = "X" * 10000

        with (
            patch(
                "promptgrimoire.export.pdf.get_latexmk_path",
                return_value="/usr/bin/latexmk",
            ),
            patch(
                "promptgrimoire.export.pdf.asyncio.create_subprocess_exec",
            ) as mock_exec,
        ):
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (
                big_output.encode(),
                b"short stderr",
            )
            mock_proc.returncode = 1
            mock_exec.return_value = mock_proc

            with pytest.raises(LaTeXCompilationError):
                from promptgrimoire.export.pdf import compile_latex

                await compile_latex(tex_path, output_dir=tmp_path)

        all_events = _flush_and_read_all(log_file)
        subprocess_events = [e for e in all_events if e.get("latex_stdout") is not None]

        assert len(subprocess_events) >= 1
        ev = subprocess_events[0]
        assert len(ev["latex_stdout"]) <= 4096
