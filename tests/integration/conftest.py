"""Integration test configuration.

Provides fixtures specific to database integration tests, mega-document
infrastructure for LaTeX compile-reduction tests, the pdf_exporter
factory fixture for PDF export integration tests, and the ``nicegui_user``
fixture for NiceGUI user-simulation integration tests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pymupdf
import pytest
import pytest_asyncio
from nicegui.testing.user_simulation import user_simulation

from promptgrimoire.export.pandoc import convert_html_with_annotations
from promptgrimoire.export.pdf import LaTeXCompilationError, compile_latex
from promptgrimoire.export.pdf_export import ensure_sty_in_dir
from promptgrimoire.export.platforms import preprocess_for_export
from promptgrimoire.export.preamble import build_annotation_preamble

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Coroutine
    from uuid import UUID

    from nicegui.testing.user import User

    from promptgrimoire.db.models import ExportJob

logger = logging.getLogger(__name__)


# =============================================================================
# Export Job Test Helpers
# =============================================================================


async def claim_own_job(our_ids: set) -> ExportJob | None:
    """Claim the next queued job whose ID is in *our_ids*.

    Production ``claim_next_job()`` is a global queue consumer — under xdist,
    it can claim another worker's job.  This helper uses the same
    ``FOR UPDATE SKIP LOCKED`` pattern but scopes the ``WHERE`` clause to
    only consider jobs created by the calling test.

    Returns ``None`` when no matching job is queued.
    """
    from datetime import UTC, datetime

    from sqlmodel import col, select

    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import ExportJob

    async with get_session() as session:
        stmt = (
            select(ExportJob)
            .where(
                ExportJob.status == "queued",
                col(ExportJob.id).in_(our_ids),
            )
            .order_by(col(ExportJob.created_at).asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = (await session.exec(stmt)).first()
        if job is None:
            return None

        job.status = "running"
        job.started_at = datetime.now(UTC)
        session.add(job)

    return job


# =============================================================================
# NiceGUI User Simulation Fixture
# =============================================================================

_NICEGUI_TEST_APP = Path(__file__).parent / "nicegui_test_app.py"


@pytest_asyncio.fixture
async def nicegui_user() -> AsyncGenerator[User]:
    """Yield a NiceGUI simulated User connected to the test app.

    Uses ``user_simulation(main_file=...)`` so all ``@ui.page`` routes
    registered by ``promptgrimoire.pages`` are available.  The simulated
    user runs in-process -- no browser or server required.

    Tests that use this fixture should be marked ``@pytest.mark.nicegui_ui``
    so the NiceGUI harness stays out of xdist-backed unit/integration
    commands and runs in its own UI lane.
    """
    async with user_simulation(main_file=_NICEGUI_TEST_APP) as u:
        # Gate: verify routes are registered before yielding to tests.
        # user_simulation runs the app script synchronously, but NiceGUI
        # may defer route registration. A 404 here means the fixture is
        # broken, not the test.
        resp = await u.http_client.get("/login", follow_redirects=True)
        assert resp.status_code == 200, (
            f"NiceGUI routes not registered after user_simulation: "
            f"/login returned {resp.status_code}"
        )
        yield u


# =============================================================================
# NiceGUI Auth Helper
# =============================================================================


async def _authenticate(user: User, *, email: str) -> None:
    """Establish an authenticated session for the simulated user.

    Instead of hitting ``/auth/callback`` (whose ``ui.navigate.to("/")``
    creates a background ``user.open()`` that replaces the httpx session
    cookie and loses the storage written by the callback), we:

    1. Open the login page to establish a session cookie.
    2. Ensure the User record exists in the DB.
    3. Write ``auth_user`` directly into ``app.storage.user``.

    This mirrors what ``_set_session_user()`` does in production auth.
    """
    from promptgrimoire.auth.mock import MOCK_INSTRUCTOR_EMAILS
    from promptgrimoire.db.users import find_or_create_user

    # 1. Establish a session (any page will do)
    await user.open("/login")

    # 2. Ensure user record exists in DB
    user_record, _ = await find_or_create_user(
        email=email,
        display_name=email.split("@", maxsplit=1)[0],
    )

    # 3. Build the auth_user dict and inject into session storage
    roles = ["stytch_member"]
    if email in MOCK_INSTRUCTOR_EMAILS:
        roles.append("instructor")

    with user:
        from nicegui import app as _app

        _app.storage.user["auth_user"] = {
            "email": email,
            "member_id": f"mock-member-{email}",
            "organization_id": "mock-org-123",
            "session_token": f"mock-session-{email}",
            "roles": roles,
            "name": email.split("@", maxsplit=1)[0].replace(".", " ").title(),
            "display_name": email.split("@", maxsplit=1)[0].replace(".", " ").title(),
            "auth_method": "mock",
            "user_id": str(user_record.id),
            "is_admin": False,
        }


# =============================================================================
# PDF Export Test Fixtures
# =============================================================================

# Shared output directory for test artifacts (gitignored)
PDF_TEST_OUTPUT_DIR = Path("output/test_output")


@dataclass
class PdfExportResult:
    """Result from PDF export containing paths for inspection."""

    pdf_path: Path
    tex_path: Path
    output_dir: Path


@pytest.fixture
def pdf_exporter() -> Callable[..., Coroutine[Any, Any, PdfExportResult]]:
    """Factory fixture for exporting PDFs using the production pipeline.

    Uses export_annotation_pdf which goes through the full workflow:
    - HTML normalisation
    - Pandoc with libreoffice.lua filter
    - Full preamble with proper settings
    - LuaLaTeX compilation via latexmk

    Usage:
        @pytest.mark.asyncio
        async def test_something(pdf_exporter, parsed_rtf):
            result = await pdf_exporter(
                html=parsed_rtf.html,
                highlights=[...],
                test_name="my_test",
            )
            assert result.pdf_path.exists()
    """
    from promptgrimoire.export.pdf_export import export_annotation_pdf

    async def _export(
        html: str,
        highlights: list[dict[str, Any]],
        test_name: str,
        tag_colours: dict[str, str] | None = None,
        general_notes: str = "",
        acceptance_criteria: str = "",
    ) -> PdfExportResult:
        """Export PDF using production pipeline.

        Args:
            html: HTML content to convert.
            highlights: List of highlight dicts.
            test_name: Name for output files (e.g., "cross_env_test").
            tag_colours: Tag colour mapping. Defaults to empty dict if None.
            general_notes: Optional HTML content for general notes section.
            acceptance_criteria: Optional text prepended to general notes
                describing what the test validates.

        Returns:
            PdfExportResult with paths to generated files.
        """
        # Combine acceptance criteria with general notes
        if acceptance_criteria:
            notes_content = (
                f"<p><b>TEST ACCEPTANCE CRITERIA</b></p><p>{acceptance_criteria}</p>"
            )
            if general_notes:
                notes_content += general_notes
        else:
            notes_content = general_notes

        # Create output directory (purge first for clean state)
        output_dir = PDF_TEST_OUTPUT_DIR / test_name
        if output_dir.exists():
            import shutil

            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Await the async export directly
        pdf_path = await export_annotation_pdf(
            html_content=html,
            highlights=highlights,
            tag_colours=tag_colours if tag_colours is not None else {},
            general_notes=notes_content,
            output_dir=output_dir,
            filename=test_name,
        )

        tex_path = output_dir / f"{test_name}.tex"

        return PdfExportResult(
            pdf_path=pdf_path,
            tex_path=tex_path,
            output_dir=output_dir,
        )

    return _export


# =============================================================================
# Database Fixtures
# =============================================================================


@pytest_asyncio.fixture(autouse=True)
async def reset_db_engine_per_test() -> AsyncGenerator[None]:
    """Dispose shared database engine after each test.

    REQUIRED for service layer tests that use get_session() from the shared
    engine module.  The shared engine's connections bind to the event loop
    that created them.  Without disposal, Test B tries to reuse Test A's
    connections after A's loop closed → RuntimeError.

    This fixture disposes the engine (closing all connections) after
    each test.  The next test lazily creates a fresh engine in its own loop.
    """
    yield

    from promptgrimoire.db.engine import _state, close_db

    if _state.engine is not None:
        await close_db()


# =============================================================================
# CRDT Test Helpers
# =============================================================================


def make_crdt_bytes(markdown: str) -> bytes:
    """Build serialised pycrdt bytes containing the given markdown text.

    Creates a pycrdt Doc with ``Text("content_markdown")`` set to the
    provided string. This mirrors the CRDT structure expected by
    ``wargame/turn_cycle.py:extract_move_text()``.

    Reusable by any test that needs to simulate a CRDT move buffer.
    """
    import pycrdt

    doc = pycrdt.Doc()
    text = doc.get("content_markdown", type=pycrdt.Text)
    text += markdown
    return doc.get_update()


# =============================================================================
# Workspace Test Helpers
# =============================================================================


async def enable_workspace_sharing(workspace_id: UUID) -> None:
    """Set shared_with_class=True on a workspace.

    Convenience helper for integration tests that need to enable
    peer sharing on a workspace without raw session manipulation.
    """
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Workspace

    async with get_session() as session:
        ws = await session.get(Workspace, workspace_id)
        assert ws is not None
        ws.shared_with_class = True
        session.add(ws)


# =============================================================================
# Mega-document Infrastructure
# =============================================================================


@dataclass(frozen=True)
class MegaDocSegment:
    """One segment of a mega-document for compile-reduction testing.

    Each segment becomes a separate subfile that can be compiled
    independently for debugging when the mega-document fails.
    """

    name: str
    """Identifier for subtests and subfile naming."""

    html: str
    """HTML content (raw, before preprocessing)."""

    highlights: list[dict[str, Any]] = field(default_factory=list)
    """Highlight annotations (empty list for no highlights)."""

    tag_colours: dict[str, str] = field(default_factory=dict)
    """Tag colour mapping for this segment's highlights."""

    general_notes: str = ""
    """HTML notes content."""

    notes_latex: str = ""
    """Pre-converted LaTeX notes content."""

    preprocess: bool = True
    """Whether to run preprocess_for_export() on the HTML."""


@dataclass
class MegaDocResult:
    """Results from compiling a mega-document."""

    pdf_path: Path
    """Path to the compiled PDF."""

    tex_path: Path
    """Path to the main document .tex file."""

    output_dir: Path
    """Directory containing all output files."""

    segment_tex: dict[str, str]
    """Mapping of segment name to its LaTeX body content."""

    pdf_text: str
    """Full PDF text extraction via pymupdf."""

    subfile_paths: dict[str, Path]
    """Mapping of segment name to subfile .tex path."""


def extract_pdf_text_pymupdf(pdf_path: Path) -> str:
    """Extract full text from PDF using pymupdf."""
    doc = pymupdf.open(str(pdf_path))
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text


def _escape_latex_name(name: str) -> str:
    """Escape a segment name for use in LaTeX section headings.

    Replaces underscores with escaped underscores since _ is special
    in LaTeX.
    """
    return name.replace("_", r"\_")


async def compile_mega_document(
    segments: list[MegaDocSegment],
    output_dir: Path,
) -> MegaDocResult:
    """Build and compile a mega-document from multiple segments.

    Each segment is processed through the export pipeline and written as a
    subfile. The main document includes all subfiles with a shared preamble.
    On compilation failure, each subfile is compiled independently to identify
    the failing segment(s).

    Args:
        segments: List of document segments to combine.
        output_dir: Directory for all output files.

    Returns:
        MegaDocResult with compilation results and extracted text.

    Raises:
        LaTeXCompilationError: If compilation fails (with per-subfile
            isolation report appended to the error message).
    """
    # Copy .sty to output directory so latexmk can find it
    ensure_sty_in_dir(output_dir)

    # Union all tag colours across segments for the shared preamble
    all_tag_colours: dict[str, str] = {}
    for seg in segments:
        all_tag_colours.update(seg.tag_colours)

    # Process each segment through the pipeline
    segment_tex: dict[str, str] = {}
    subfile_paths: dict[str, Path] = {}

    for seg in segments:
        # Preprocess HTML if requested
        processed_html = preprocess_for_export(seg.html) if seg.preprocess else seg.html

        # Convert HTML to LaTeX body with annotations
        latex_body = await convert_html_with_annotations(
            html=processed_html,
            highlights=seg.highlights,
            tag_colours=seg.tag_colours,
        )

        # Append notes sections if present
        if seg.notes_latex:
            latex_body += f"\n\\section*{{General Notes}}\n{seg.notes_latex}\n"
        elif seg.general_notes:
            from promptgrimoire.export.pdf_export import html_to_latex_notes

            notes_content = html_to_latex_notes(seg.general_notes)
            if notes_content:
                latex_body += f"\n\\section*{{General Notes}}\n{notes_content}\n"

        segment_tex[seg.name] = latex_body

        # Write subfile
        escaped_name = _escape_latex_name(seg.name)
        subfile_content = (
            "\\documentclass[mega_test.tex]{subfiles}\n"
            "\\begin{document}\n"
            f"\\section*{{{escaped_name}}}\n"
            f"{latex_body}\n"
            "\\end{document}\n"
        )
        subfile_path = output_dir / f"{seg.name}.tex"
        subfile_path.write_text(subfile_content)
        subfile_paths[seg.name] = subfile_path

    # Build shared preamble with dynamic font loading from combined body text
    combined_body = "\n".join(segment_tex.values())
    preamble = build_annotation_preamble(all_tag_colours, body_text=combined_body)

    # Build main document
    body_parts: list[str] = []
    for i, seg in enumerate(segments):
        if i > 0:
            body_parts.append("\\clearpage")
        body_parts.append(f"\\subfile{{{seg.name}}}")

    main_body = "\n".join(body_parts)

    main_document = (
        "\\documentclass[a4paper,12pt]{article}\n"
        "\\usepackage{subfiles}\n"
        f"{preamble}\n"
        "\n"
        "\\begin{document}\n"
        "\n"
        f"{main_body}\n"
        "\n"
        "\\end{document}\n"
    )

    tex_path = output_dir / "mega_test.tex"
    tex_path.write_text(main_document)

    # Compile the mega-document
    try:
        pdf_path = await compile_latex(tex_path, output_dir)
    except LaTeXCompilationError:
        # Subfile fallback: compile each subfile independently to identify
        # the failing segment(s)
        isolation_results: dict[str, str] = {}
        for name, sf_path in subfile_paths.items():
            try:
                await compile_latex(sf_path, output_dir)
                isolation_results[name] = "ok"
            except LaTeXCompilationError as sf_err:
                isolation_results[name] = f"FAILED - {sf_err.args[0]}"
            except Exception as sf_err:
                isolation_results[name] = f"FAILED - {sf_err}"

        # Build enhanced error message
        report_lines = ["Subfile isolation results:"]
        for name, result in isolation_results.items():
            report_lines.append(f"  {name}: {result}")
        isolation_report = "\n".join(report_lines)

        # Suppress the original traceback (`from None`) because the
        # isolation report above is more useful for debugging than the
        # raw LaTeXCompilationError — it shows which subfiles compiled
        # and which failed, plus the log path for the full output.
        log_path = output_dir / "mega_test.log"
        raise LaTeXCompilationError(
            f"Mega-document compilation failed.\n{isolation_report}",
            tex_path=tex_path,
            log_path=log_path,
        ) from None

    # Extract PDF text
    pdf_text = extract_pdf_text_pymupdf(pdf_path)

    return MegaDocResult(
        pdf_path=pdf_path,
        tex_path=tex_path,
        output_dir=output_dir,
        segment_tex=segment_tex,
        pdf_text=pdf_text,
        subfile_paths=subfile_paths,
    )
