"""Export commands: log inspection and batch PDF export."""

from __future__ import annotations

import asyncio
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
from pycrdt import Doc, Map, Text
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from sqlalchemy import tstring

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.tags import list_tags_for_workspace
from promptgrimoire.db.workspace_documents import list_documents
from promptgrimoire.db.workspaces import get_workspace, get_workspace_export_metadata
from promptgrimoire.export.filename import (
    PdfExportFilenameContext,
    build_pdf_export_stem,
)
from promptgrimoire.export.pdf import LaTeXCompilationError
from promptgrimoire.export.pdf_export import (
    export_annotation_pdf,
    generate_tex_only,
    markdown_to_latex_notes,
)

console = Console()

export_app = typer.Typer(help="PDF export and log inspection.")


# ---------------------------------------------------------------------------
# Log inspection (existing)
# ---------------------------------------------------------------------------


def _find_export_dir(user_id: str | None) -> Path:
    """Find the export directory for a user or most recent."""
    tmp_dir = Path(tempfile.gettempdir())

    if user_id:
        export_dir = tmp_dir / f"promptgrimoire_export_{user_id}"
        if not export_dir.exists():
            console.print(f"[red]Error:[/] Export directory not found: {export_dir}")
            sys.exit(1)
        return export_dir

    export_dirs = list(tmp_dir.glob("promptgrimoire_export_*"))
    if not export_dirs:
        console.print("[red]Error:[/] No export directories found in temp folder")
        console.print(f"[dim]Searched in: {tmp_dir}[/]")
        sys.exit(1)

    return max(export_dirs, key=lambda p: p.stat().st_mtime)


def _show_error_context(log_file: Path, tex_file: Path) -> None:
    """Show LaTeX error with context from both log and tex file."""
    log_content = log_file.read_text()
    tex_lines = tex_file.read_text().splitlines()

    error_line_match = re.search(r"^l\.(\d+)", log_content, re.MULTILINE)
    error_line = int(error_line_match.group(1)) if error_line_match else None

    console.print("\n[bold red]LaTeX Error (last 100 lines of log):[/]")
    for line in log_content.splitlines()[-100:]:
        if line.startswith("!") or "Error" in line:
            console.print(f"[red]{line}[/]")
        elif line.startswith("l."):
            console.print(f"[yellow]{line}[/]")
        else:
            console.print(line)

    if error_line:
        console.print(f"\n[bold yellow]TeX Source around line {error_line}:[/]")
        start = max(0, error_line - 15)
        end = min(len(tex_lines), error_line + 10)
        context = "\n".join(tex_lines[start:end])
        console.print(
            Syntax(
                context,
                "latex",
                line_numbers=True,
                start_line=start + 1,
                highlight_lines={error_line},
            )
        )
    else:
        console.print("\n[dim]Could not find error line number in log[/]")


@export_app.command("log")
def log(
    user_id: Annotated[
        str | None,
        typer.Argument(help="User ID (default: most recent export)"),
    ] = None,
    tex: Annotated[
        bool,
        typer.Option("--tex", help="Show .tex source instead of log"),
    ] = False,
    both: Annotated[
        bool,
        typer.Option("--both", help="Show error context from log and tex"),
    ] = False,
) -> None:
    """Show the most recent PDF export LaTeX log."""
    export_dir = _find_export_dir(user_id)
    log_file = export_dir / "annotated_document.log"
    tex_file = export_dir / "annotated_document.tex"

    console.print(
        Panel(
            f"[bold]Export Directory:[/] {export_dir}\n"
            f"[bold]TeX Source:[/] {tex_file}\n"
            f"[bold]LaTeX Log:[/] {log_file}",
            title="PDF Export Debug Files",
            border_style="blue",
        )
    )

    if both:
        if not tex_file.exists() or not log_file.exists():
            console.print("[red]Error:[/] Missing .tex or .log file")
            sys.exit(1)
        _show_error_context(log_file, tex_file)
    elif tex:
        if not tex_file.exists():
            console.print(f"[red]Error:[/] TeX file not found: {tex_file}")
            sys.exit(1)
        with console.pager():
            console.print(
                Syntax(
                    tex_file.read_text(),
                    "latex",
                    line_numbers=True,
                )
            )
    else:
        if not log_file.exists():
            console.print(f"[red]Error:[/] Log file not found: {log_file}")
            sys.exit(1)
        with console.pager():
            console.print(log_file.read_text())


# ---------------------------------------------------------------------------
# Batch PDF export — helpers
# ---------------------------------------------------------------------------


_DEFAULT_OUTPUT_DIR = Path(tempfile.gettempdir()) / "grimoire_export_batch"


async def _build_export_stem(workspace_id: UUID) -> str:
    """Build a descriptive filename stem, prefixed with UUID short for uniqueness."""
    meta = await get_workspace_export_metadata(workspace_id)
    ctx = PdfExportFilenameContext(
        course_code=meta.course_code if meta else None,
        activity_title=meta.activity_title if meta else None,
        workspace_title=meta.workspace_title if meta else None,
        owner_display_name=meta.owner_display_name if meta else None,
        export_date=datetime.now().date(),
    )
    stem = build_pdf_export_stem(ctx)
    return f"{str(workspace_id)[:8]}_{stem}"


def _load_crdt(crdt_state: bytes) -> Doc:
    """Load CRDT state into a pycrdt Doc."""
    crdt_doc = Doc()
    crdt_doc.apply_update(crdt_state)
    return crdt_doc


def _extract_crdt_highlights(
    crdt_doc: Doc,
    tags: list,
) -> list[dict]:
    """Extract highlights from a loaded CRDT doc with tag display names."""
    highlights_map = crdt_doc.get("highlights", type=Map)
    highlights: list[dict] = []
    for key in highlights_map:
        val = highlights_map[key]
        if isinstance(val, dict):
            highlights.append(val)

    # Filter to highlights whose tag still exists (dangling highlights
    # reference deleted tags and have no colour defined in the preamble,
    # causing xcolor "Undefined color" errors).  Matches the UI export
    # path's filtering in pdf_export.py.
    tag_name_map = {str(t.id): t.name for t in tags}
    valid = [hl for hl in highlights if str(hl.get("tag", "")) in tag_name_map]
    return [
        {**hl, "tag_name": tag_name_map.get(str(hl.get("tag", "")))} for hl in valid
    ]


def _extract_response_markdown(crdt_doc: Doc) -> str:
    """Extract response_draft_markdown from a loaded CRDT doc."""
    try:
        text = crdt_doc.get("response_draft_markdown", type=Text)
        return str(text)
    except Exception:
        return ""


def _copy_artifacts(
    ws_export_dir: Path,
    output_dir: Path,
    safe_stem: str,
    *,
    with_log: bool,
    with_tex: bool,
) -> None:
    """Copy .tex and .log artifacts from the workspace export dir."""
    if with_tex:
        tex_path = ws_export_dir / f"{safe_stem}.tex"
        if tex_path.exists():
            shutil.copy2(tex_path, output_dir / tex_path.name)

    if with_log:
        log_path = ws_export_dir / f"{safe_stem}.log"
        if log_path.exists():
            shutil.copy2(log_path, output_dir / log_path.name)


# Sentinel for "skipped" (no content / not exportable) vs real errors
_SKIP = "SKIP"


def _extract_error_summary(exc: LaTeXCompilationError) -> str:
    """Build a one-line error summary from a LaTeX compilation error."""
    error_summary = str(exc).split("\n")[0]
    if exc.log_path.exists():
        log_content = exc.log_path.read_text(errors="replace")
        error_lines = [
            line.strip() for line in log_content.splitlines() if line.startswith("!")
        ]
        if error_lines:
            error_summary = f"{error_summary} | {error_lines[0]}"
    return error_summary


def _enrich_document_highlights(
    doc,
    highlights: list[dict],
    tag_name_map: dict[str, str],
) -> list[dict]:
    """Filter to one document's highlights and enrich each with its tag name."""
    doc_highlights = [h for h in highlights if h.get("document_id") == str(doc.id)]
    valid = [hl for hl in doc_highlights if str(hl.get("tag", "")) in tag_name_map]
    return [
        {**hl, "tag_name": tag_name_map.get(str(hl.get("tag", "")))} for hl in valid
    ]


def _build_export_document_payload(
    doc,
    enriched_highlights: list[dict],
    fallback_index: int,
) -> dict:
    """Build one document's export payload dict."""
    doc_para_map = doc.paragraph_map
    legal_para_map: dict[int, int | None] | None = (
        {int(k): v for k, v in doc_para_map.items()} if doc_para_map else None
    )
    return {
        "title": doc.title or f"Source {fallback_index}",
        "html_content": doc.content or "",
        "highlights": enriched_highlights,
        "word_to_legal_para": legal_para_map,
    }


def _build_export_documents(
    content_docs: list,
    highlights: list[dict],
    tag_name_map: dict[str, str],
) -> list[dict]:
    """Assemble per-document export payloads, enriching highlights with tag names."""
    documents: list[dict] = []
    for i, doc in enumerate(content_docs, 1):
        enriched = _enrich_document_highlights(doc, highlights, tag_name_map)
        documents.append(_build_export_document_payload(doc, enriched, i))
    return documents


@dataclass(frozen=True, slots=True)
class WorkspaceExportJob:
    """A fully-prepared, ready-to-compile single-workspace export."""

    workspace_id: UUID
    safe_stem: str
    tag_colours: dict[str, str]
    notes_latex: str
    documents: list[dict]


async def _compile_workspace_pdf(
    job: WorkspaceExportJob,
    output_dir: Path,
    *,
    with_log: bool,
    with_tex: bool,
) -> tuple[str, str | None]:
    """Compile one workspace's PDF, copy artifacts, and classify any error.

    Returns (filename_stem, error_or_none).
    """
    ws_export_dir = Path(
        tempfile.mkdtemp(
            prefix=f"promptgrimoire_export_{str(job.workspace_id)[:8]}_",
        )
    )

    try:
        pdf_path = await export_annotation_pdf(
            html_content="",
            highlights=[],
            tag_colours=job.tag_colours,
            output_dir=ws_export_dir,
            filename=job.safe_stem,
            workspace_id=str(job.workspace_id),
            notes_latex=job.notes_latex,
            documents=job.documents,
        )
        shutil.copy2(pdf_path, output_dir / pdf_path.name)
        _copy_artifacts(
            ws_export_dir,
            output_dir,
            job.safe_stem,
            with_log=with_log,
            with_tex=with_tex,
        )
        return job.safe_stem, None

    except LaTeXCompilationError as exc:
        _copy_artifacts(
            ws_export_dir,
            output_dir,
            job.safe_stem,
            with_log=with_log,
            with_tex=with_tex,
        )
        return job.safe_stem, _extract_error_summary(exc)

    except Exception as exc:
        return job.safe_stem, f"{type(exc).__name__}: {exc}"

    finally:
        shutil.rmtree(ws_export_dir, ignore_errors=True)


async def _export_single_workspace(
    workspace_id: UUID,
    output_dir: Path,
    *,
    with_log: bool,
    with_tex: bool,
) -> tuple[str, str | None]:
    """Export a single workspace to PDF.

    Returns (filename_stem, error_or_none). Error is _SKIP for
    workspaces without exportable content (no docs, no highlights).
    """
    workspace = await get_workspace(workspace_id)
    if workspace is None:
        return str(workspace_id)[:8], _SKIP

    safe_stem = await _build_export_stem(workspace_id)

    docs = await list_documents(workspace_id)
    content_docs = [d for d in docs if d.content and d.content.strip()]
    if not content_docs:
        return safe_stem, _SKIP

    tags = await list_tags_for_workspace(workspace_id)
    tag_colours = {str(t.id): t.color for t in tags if t.color}

    crdt_doc = _load_crdt(workspace.crdt_state) if workspace.crdt_state else None

    highlights: list[dict] = []
    if crdt_doc is not None:
        highlights = _extract_crdt_highlights(crdt_doc, tags)

    tag_name_map = {str(t.id): t.name for t in tags}
    documents = _build_export_documents(content_docs, highlights, tag_name_map)

    has_highlights = any(d["highlights"] for d in documents)
    if not has_highlights:
        return safe_stem, _SKIP

    # Convert response draft markdown to LaTeX notes
    response_md = _extract_response_markdown(crdt_doc) if crdt_doc else ""
    notes_latex = await markdown_to_latex_notes(response_md) if response_md else ""

    job = WorkspaceExportJob(
        workspace_id=workspace_id,
        safe_stem=safe_stem,
        tag_colours=tag_colours,
        notes_latex=notes_latex,
        documents=documents,
    )
    return await _compile_workspace_pdf(
        job, output_dir, with_log=with_log, with_tex=with_tex
    )


async def _export_single_workspace_tex_only(
    workspace_id: UUID,
    output_dir: Path,
) -> tuple[str, str | None]:
    """Generate .tex for a workspace without compiling.

    Copies .tex and .sty to output_dir. Returns (stem, error_or_none).
    Error is _SKIP for workspaces without exportable content.
    """
    workspace = await get_workspace(workspace_id)
    if workspace is None:
        return str(workspace_id)[:8], _SKIP

    safe_stem = await _build_export_stem(workspace_id)

    docs = await list_documents(workspace_id)
    content_docs = [d for d in docs if d.content and d.content.strip()]
    if not content_docs:
        return safe_stem, _SKIP

    tags = await list_tags_for_workspace(workspace_id)
    tag_colours = {str(t.id): t.color for t in tags if t.color}

    crdt_doc = _load_crdt(workspace.crdt_state) if workspace.crdt_state else None

    highlights: list[dict] = []
    if crdt_doc is not None:
        highlights = _extract_crdt_highlights(crdt_doc, tags)

    doc = content_docs[0]
    doc_highlights = [h for h in highlights if h.get("document_id") == str(doc.id)]
    if not doc_highlights:
        return safe_stem, _SKIP

    ws_export_dir = Path(
        tempfile.mkdtemp(
            prefix=f"promptgrimoire_export_{str(workspace_id)[:8]}_",
        )
    )

    try:
        tex_path = await generate_tex_only(
            html_content=doc.content or "",
            highlights=doc_highlights,
            tag_colours=tag_colours,
            output_dir=ws_export_dir,
            filename=safe_stem,
        )
        shutil.copy2(tex_path, output_dir / tex_path.name)
        # Copy .sty (needed for compilation)
        sty_in_dir = ws_export_dir / "promptgrimoire-export.sty"
        sty_dest = output_dir / "promptgrimoire-export.sty"
        if sty_in_dir.exists() and not sty_dest.exists():
            shutil.copy2(sty_in_dir, sty_dest)
        return safe_stem, None

    except Exception as exc:
        return safe_stem, f"{type(exc).__name__}: {exc}"

    finally:
        shutil.rmtree(ws_export_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Batch scope resolution
# ---------------------------------------------------------------------------


async def _resolve_scope_workspace_ids(scope: str) -> list[UUID]:
    """Resolve a --scope value to a list of exportable workspace IDs.

    Query-shaped read migrated to raw SQL per ADR 0004/0005 -- SQLModel
    column expressions in .join()/.where()/.in_() do not type-check under
    ty (astral-sh/ty#3421). The "exportable" predicate (crdt_state set, a
    document with non-empty content) is repeated per branch rather than
    shared, since t-string SQL fragments aren't composable the way
    SQLAlchemy expression objects were.
    """
    async with get_session() as session:
        if scope == "server":
            rows = await session.execute(
                tstring(
                    t"""
                    SELECT DISTINCT w.id
                    FROM workspace w
                    JOIN workspace_document wd ON wd.workspace_id = w.id
                    WHERE w.crdt_state IS NOT NULL
                      AND wd.content IS NOT NULL
                      AND wd.content != ''
                    """
                )
            )
        elif scope.startswith("unit:"):
            course_id = UUID(scope.removeprefix("unit:"))
            rows = await session.execute(
                tstring(
                    t"""
                    SELECT DISTINCT w.id
                    FROM workspace w
                    JOIN workspace_document wd ON wd.workspace_id = w.id
                    WHERE w.crdt_state IS NOT NULL
                      AND wd.content IS NOT NULL
                      AND wd.content != ''
                      AND (
                        w.course_id = {course_id}
                        OR w.activity_id IN (
                            SELECT a.id
                            FROM activity a
                            JOIN week wk ON wk.id = a.week_id
                            WHERE wk.course_id = {course_id}
                        )
                      )
                    """
                )
            )
        elif scope.startswith("activity:"):
            activity_id = UUID(scope.removeprefix("activity:"))
            rows = await session.execute(
                tstring(
                    t"""
                    SELECT DISTINCT w.id
                    FROM workspace w
                    JOIN workspace_document wd ON wd.workspace_id = w.id
                    WHERE w.crdt_state IS NOT NULL
                      AND wd.content IS NOT NULL
                      AND wd.content != ''
                      AND w.activity_id = {activity_id}
                    """
                )
            )
        else:
            console.print(
                f"[red]Error:[/] Invalid scope '{scope}'. "
                "Use 'server', 'unit:<uuid>', or 'activity:<uuid>'."
            )
            sys.exit(1)

        return [row[0] for row in rows.all()]


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------


def _print_dry_run(workspace_ids: list[UUID]) -> None:
    """Print dry-run listing of workspaces."""
    table = Table(title="Workspaces to export (dry run)")
    table.add_column("UUID", style="cyan")
    table.add_column("Short ID", style="dim")
    for ws_id in workspace_ids:
        table.add_row(str(ws_id), str(ws_id)[:8])
    console.print(table)
    console.print(f"\n[bold]{len(workspace_ids)}[/] workspaces would be exported.")


def _purge_successes(
    output_dir: Path,
    results: list[tuple[str, str, str | None]],
) -> None:
    """Remove all artifacts for successful exports (--only-errors mode).

    Skipped workspaces (error == _SKIP) produce no artifacts, so they
    are harmless and ignored here.
    """
    for _short_id, stem, error in results:
        if error is None:  # success — purge
            for ext in (".pdf", ".tex", ".log"):
                artifact = output_dir / f"{stem}{ext}"
                if artifact.exists():
                    artifact.unlink()


def _print_results_table(
    results: list[tuple[str, str, str | None]],
    *,
    only_errors: bool,
    tex_only: bool,
    output_dir: Path,
) -> None:
    """Print the summary results table."""
    table = Table(title="Export Results")
    table.add_column("UUID", style="cyan", no_wrap=True)
    table.add_column("Filename", style="dim")
    table.add_column("Status")
    table.add_column("Error")

    successes = 0
    failures = 0
    skipped = 0
    for short_id, stem, error in results:
        if error == _SKIP:
            skipped += 1
        elif error:
            failures += 1
            table.add_row(short_id, stem, "[red]FAIL[/]", error)
        else:
            successes += 1
            if not only_errors:
                table.add_row(short_id, stem, "[green]OK[/]", "")

    console.print()
    console.print(table)

    mode_label = "tex-only" if tex_only else "PDF"
    purge_note = " (successes purged)" if only_errors else ""
    console.print(
        f"\n[bold]{successes}[/] succeeded, [bold]{failures}[/] failed, "
        f"[dim]{skipped}[/] skipped (no content/annotations). "
        f"Output [{mode_label}]: {output_dir}{purge_note}"
    )


async def _resolve_workspace_unit_mapping(
    workspace_ids: list[UUID],
) -> dict[UUID, tuple[str, list[str]]]:
    """Map workspace IDs to (owner_email, [unit_names]).

    Uses ACL owner entries for the owner, and course_enrollment for
    unit membership. Multi-enrolled users appear under every unit.
    Users with no enrollment get ["_unenrolled"].

    Query-shaped read migrated to raw SQL per ADR 0004/0005 -- SQLModel
    column expressions in .join()/.where()/.in_() do not type-check under
    ty (astral-sh/ty#3421).
    """
    mapping: dict[UUID, tuple[str, list[str]]] = {}
    async with get_session() as session:
        # workspace -> owner email
        # Row indexing beyond [0] doesn't type-check for raw execute()
        # results (ty infers `Row[Any]` as length-1); attribute access by
        # column label does, so every column here is explicitly aliased.
        owner_rows = await session.execute(
            tstring(
                t"""
                SELECT a.workspace_id AS workspace_id,
                       u.email AS email,
                       u.id AS user_id
                FROM acl_entry a
                JOIN "user" u ON u.id = a.user_id
                WHERE a.workspace_id = ANY({workspace_ids})
                  AND a.permission = 'owner'
                """
            )
        )
        ws_owner: dict[UUID, tuple[str, UUID]] = {}
        for row in owner_rows:
            ws_owner[row.workspace_id] = (row.email, row.user_id)

        # user -> enrolled unit names
        user_ids = list({uid for _, uid in ws_owner.values()})
        user_units: dict[UUID, list[str]] = {}
        if user_ids:
            enroll_rows = await session.execute(
                tstring(
                    t"""
                    SELECT ce.user_id AS user_id, c.name AS unit_name
                    FROM course_enrollment ce
                    JOIN course c ON c.id = ce.course_id
                    WHERE ce.user_id = ANY({user_ids})
                    """
                )
            )
            for row in enroll_rows:
                user_units.setdefault(row.user_id, []).append(row.unit_name)

        for ws_id in workspace_ids:
            if ws_id in ws_owner:
                email, uid = ws_owner[ws_id]
                units = user_units.get(uid, ["_unenrolled"])
                mapping[ws_id] = (email, units)
            else:
                mapping[ws_id] = ("_unknown_owner", ["_unenrolled"])

    return mapping


def _sanitise_dirname(name: str) -> str:
    """Make a string safe for use as a directory name."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip(". ")


def _resolve_reorganise_target(
    result: tuple[str, str, str | None],
    short_to_full: dict[str, UUID],
    ws_mapping: dict[UUID, tuple[str, list[str]]],
    output_dir: Path,
) -> tuple[str, list[str], list[Path]] | None:
    """Resolve one export result to (owner_email, units, matching_files).

    Returns None if the result should be skipped (failed, unmapped, or
    no matching files on disk).
    """
    short_id, stem, error = result
    if error is not None:
        return None
    ws_id = short_to_full.get(short_id)
    if ws_id is None or ws_id not in ws_mapping:
        return None

    email, units = ws_mapping[ws_id]
    files = list(output_dir.glob(f"{stem}.*"))
    if not files:
        return None

    return email, units, files


def _copy_files_to_unit_dirs(
    files: list[Path],
    units: list[str],
    output_dir: Path,
    safe_email: str,
) -> None:
    """Copy exported files into output_dir/<unit>/<email>/ for every unit."""
    for unit_name in units:
        safe_unit = _sanitise_dirname(unit_name)
        dest_dir = output_dir / safe_unit / safe_email
        dest_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            shutil.copy2(f, dest_dir / f.name)


def _reorganise_by_unit(
    output_dir: Path,
    results: list[tuple[str, str, str | None]],
    ws_mapping: dict[UUID, tuple[str, list[str]]],
    workspace_ids: list[UUID],
) -> None:
    """Move exported files from flat output_dir into unit/email/ subdirs."""
    # Build short_id -> workspace_id lookup
    short_to_full: dict[str, UUID] = {str(ws_id)[:8]: ws_id for ws_id in workspace_ids}

    moved = 0
    for result in results:
        target = _resolve_reorganise_target(
            result, short_to_full, ws_mapping, output_dir
        )
        if target is None:
            continue
        email, units, files = target

        safe_email = _sanitise_dirname(email)
        _copy_files_to_unit_dirs(files, units, output_dir, safe_email)

        # Remove the flat copies
        for f in files:
            f.unlink()
        moved += 1

    console.print(
        f"\n[bold]Reorganised:[/] {moved} workspaces into unit/email/ folders"
    )


async def _resolve_ids(ids_or_scope: list[UUID] | str) -> list[UUID] | None:
    """Resolve workspace IDs, handling scope strings inside the event loop."""
    if isinstance(ids_or_scope, list):
        return ids_or_scope
    workspace_ids = await _resolve_scope_workspace_ids(ids_or_scope)
    if not workspace_ids:
        console.print("[yellow]No exportable workspaces found for scope.[/]")
        return None
    console.print(f"[bold]{len(workspace_ids)}[/] exportable workspaces resolved.")
    return workspace_ids


@dataclass(frozen=True, slots=True)
class BatchExportOptions:
    """Flags controlling one batch export run."""

    with_log: bool = False
    with_tex: bool = False
    dry_run: bool = False
    tex_only: bool = False
    only_errors: bool = False
    by_unit: bool = False


async def _run_batch_export(
    workspace_ids_or_scope: list[UUID] | str,
    output_dir: Path,
    options: BatchExportOptions,
) -> None:
    """Export multiple workspaces sequentially.

    Accepts either pre-parsed UUIDs or a scope string. Scope resolution
    happens inside this coroutine so that only one event loop is used
    (avoids orphaning asyncpg connections from a prior asyncio.run).
    """
    resolved = await _resolve_ids(workspace_ids_or_scope)
    if resolved is None:
        return
    workspace_ids = resolved

    if options.dry_run:
        _print_dry_run(workspace_ids)
        return

    # Clear output dir to prevent stale artifacts from prior runs
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # --only-errors implies --with-log --with-tex for failures
    effective_with_log = options.with_log or options.only_errors
    effective_with_tex = options.with_tex or options.only_errors

    results: list[tuple[str, str, str | None]] = []
    for i, ws_id in enumerate(workspace_ids, 1):
        short_id = str(ws_id)[:8]
        console.print(
            f"[dim][{i}/{len(workspace_ids)}][/] Exporting {short_id}...",
            end=" ",
        )
        if options.tex_only:
            stem, error = await _export_single_workspace_tex_only(ws_id, output_dir)
        else:
            stem, error = await _export_single_workspace(
                ws_id,
                output_dir,
                with_log=effective_with_log,
                with_tex=effective_with_tex,
            )
        if error == _SKIP:
            console.print("[dim]SKIP[/]")
        elif error:
            console.print("[red]FAIL[/]")
        else:
            console.print("[green]OK[/]")
        results.append((short_id, stem, error))

    if options.only_errors:
        _purge_successes(output_dir, results)

    if options.by_unit:
        console.print("\n[bold]Resolving unit/user mapping...[/]")
        ws_mapping = await _resolve_workspace_unit_mapping(workspace_ids)
        _reorganise_by_unit(output_dir, results, ws_mapping, workspace_ids)

    _print_results_table(
        results,
        only_errors=options.only_errors,
        tex_only=options.tex_only,
        output_dir=output_dir,
    )


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


def _validate_workspace_args(
    workspace_ids: list[str] | None,
    scope: str | None,
) -> list[UUID] | str:
    """Validate CLI arguments and return parsed UUIDs or scope string.

    Returns a list of UUIDs if explicit IDs were given, or the scope
    string for deferred async resolution (avoiding a second asyncio.run
    that would orphan asyncpg connections).
    """
    if not workspace_ids and not scope:
        console.print(
            "[red]Error:[/] Provide workspace UUIDs or --scope. See --help for usage."
        )
        raise typer.Exit(1)

    if workspace_ids and scope:
        console.print(
            "[red]Error:[/] Cannot combine workspace UUIDs with --scope. "
            "Use one or the other."
        )
        raise typer.Exit(1)

    if workspace_ids:
        parsed: list[UUID] = []
        for ws_str in workspace_ids:
            try:
                parsed.append(UUID(ws_str))
            except ValueError:
                console.print(f"[red]Error:[/] Invalid UUID: {ws_str}")
                raise typer.Exit(1) from None
        return parsed

    # workspace_ids is falsy here. The first guard proved
    # `workspace_ids or scope`, so scope must be set -- ty can't trace that
    # cross-branch boolean invariant, hence the explicit assert.
    assert scope is not None  # noqa: S101 - guarded by early exits above
    return scope


def _build_artifacts_label(
    *,
    tex_only: bool,
    only_errors: bool,
    with_tex: bool,
    with_log: bool,
) -> str:
    """Build the artifacts description for the info panel."""
    mode = "TeX only" if tex_only else "PDF"
    if only_errors:
        mode += " (only-errors)"
    if not tex_only:
        if with_tex:
            mode += " + .tex"
        if with_log:
            mode += " + .log"
    return mode


# PLR0913/PLR0917 (too many arguments): each parameter is an independent
# Typer CLI flag with its own --help text; Typer maps one Python parameter
# per flag, so there is no param-object form to bundle these into without
# adopting a codebase-wide Typer pattern this project doesn't otherwise use
# (see the matching noqa on `run`/`firefox` in cli/e2e/__init__.py).
@export_app.command("run")
def run(  # noqa: PLR0913, PLR0917
    workspace_ids: Annotated[
        list[str] | None,
        typer.Argument(help="Workspace UUIDs to export"),
    ] = None,
    scope: Annotated[
        str | None,
        typer.Option(
            "--scope",
            help="Batch scope: 'server', 'unit:<uuid>', or 'activity:<uuid>'",
        ),
    ] = None,
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output directory for exported files"),
    ] = _DEFAULT_OUTPUT_DIR,
    with_log: Annotated[
        bool,
        typer.Option("--with-log", help="Include .log files in output"),
    ] = False,
    with_tex: Annotated[
        bool,
        typer.Option("--with-tex", help="Include .tex files in output"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="List workspaces without exporting"),
    ] = False,
    tex_only: Annotated[
        bool,
        typer.Option("--tex-only", help="Generate .tex + .sty only (no compilation)"),
    ] = False,
    only_errors: Annotated[
        bool,
        typer.Option(
            "--only-errors",
            help="Compile all, purge successes, keep only failures with .tex/.log",
        ),
    ] = False,
    by_unit: Annotated[
        bool,
        typer.Option(
            "--by-unit",
            help="Organise output into unit/email/ subdirectories via enrollment",
        ),
    ] = False,
) -> None:
    """Export workspaces to PDF.

    Pass workspace UUIDs as arguments, or use --scope for batch export.

    \b
    Examples:
        grimoire export run 3c33265d-1202-4488-a08a-1eb0a7348994
        grimoire export run --scope server --with-log --with-tex
        grimoire export run --scope server --only-errors
        grimoire export run --scope server --tex-only
        grimoire export run --scope server --by-unit
        grimoire export run --scope activity:abc123 --dry-run
    """
    ids_or_scope = _validate_workspace_args(workspace_ids, scope)

    artifacts = _build_artifacts_label(
        tex_only=tex_only,
        only_errors=only_errors,
        with_tex=with_tex,
        with_log=with_log,
    )
    layout = " (by unit/email)" if by_unit else ""
    count = (
        len(ids_or_scope) if isinstance(ids_or_scope, list) else f"scope:{ids_or_scope}"
    )
    console.print(
        Panel(
            f"[bold]Workspaces:[/] {count}\n"
            f"[bold]Output:[/] {output}{layout}\n"
            f"[bold]Artifacts:[/] {artifacts}",
            title="PDF Batch Export",
            border_style="blue",
        )
    )

    asyncio.run(
        _run_batch_export(
            ids_or_scope,
            output,
            BatchExportOptions(
                with_log=with_log,
                with_tex=with_tex,
                dry_run=dry_run,
                tex_only=tex_only,
                only_errors=only_errors,
                by_unit=by_unit,
            ),
        )
    )
