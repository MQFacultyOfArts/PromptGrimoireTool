"""Backfill paragraph maps for existing WorkspaceDocument rows.

Queries all documents where ``paragraph_map`` is empty (``{}``),
runs ``detect_source_numbering()`` + ``build_paragraph_map()`` on each,
and updates the ``auto_number_paragraphs`` and ``paragraph_map`` columns.

Idempotent: documents with a non-empty ``paragraph_map`` are skipped.
Documents whose content produces an empty map are also skipped (no
meaningful paragraphs to number).

Usage:
    uv run backfill-paragraph-maps              # update all documents
    uv run backfill-paragraph-maps --dry-run    # report without modifying
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from rich.console import Console

from promptgrimoire.config import get_settings

console = Console()

BATCH_SIZE = 50


async def _backfill(*, dry_run: bool) -> None:
    """Run the backfill against the database."""
    # Deferred imports to avoid circular import through
    # input_pipeline.__init__ -> html_input -> export -> highlight_spans
    from sqlmodel import col, select

    from promptgrimoire.db.engine import get_session, init_db
    from promptgrimoire.db.models import WorkspaceDocument
    from promptgrimoire.input_pipeline.paragraph_map import (
        build_paragraph_map,
        detect_source_numbering,
    )

    await init_db()

    processed = 0
    updated = 0
    skipped_empty = 0
    errors = 0

    async with get_session() as session:
        # Fetch all documents with empty paragraph_map.
        # JSON '{}' is the default; we match it with a cast comparison.
        stmt = (
            select(WorkspaceDocument)
            .where(col(WorkspaceDocument.paragraph_map) == {})
            .order_by(col(WorkspaceDocument.created_at))
        )
        results = await session.exec(stmt)
        documents = results.all()

        total = len(documents)
        console.print(f"Found [bold]{total}[/] document(s) with empty paragraph_map.")

        if total == 0:
            console.print("[green]Nothing to do.[/]")
            return

        for doc in documents:
            processed += 1

            try:
                has_source = detect_source_numbering(doc.content)
                auto_number = not has_source
                para_map = build_paragraph_map(doc.content, auto_number=auto_number)

                if not para_map:
                    skipped_empty += 1
                    continue

                if dry_run:
                    console.print(
                        f"  [dim]Would update[/] {doc.id} "
                        f"(auto_number={auto_number}, "
                        f"map_size={len(para_map)})"
                    )
                else:
                    doc.auto_number_paragraphs = auto_number
                    doc.paragraph_map = {str(k): v for k, v in para_map.items()}
                    session.add(doc)

                updated += 1

                # Flush in batches to avoid long-running transactions.
                if not dry_run and updated % BATCH_SIZE == 0:
                    await session.flush()
                    console.print(f"  Flushed batch ({updated}/{total} updated)")

            except Exception as exc:
                errors += 1
                console.print(f"  [red]Error[/] processing {doc.id}: {exc}")

        # Final flush for remaining documents.
        if not dry_run:
            await session.flush()

    mode = "[yellow]DRY RUN[/] " if dry_run else ""
    console.print()
    console.print(f"{mode}Backfill complete:")
    console.print(f"  Processed:    {processed}")
    console.print(f"  Updated:      {updated}")
    console.print(f"  Skipped (empty map): {skipped_empty}")
    console.print(f"  Errors:       {errors}")


def main() -> None:
    """CLI entry point for paragraph map backfill."""
    parser = argparse.ArgumentParser(
        description="Backfill paragraph maps for existing documents.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be updated without modifying the database.",
    )
    args = parser.parse_args()

    if not get_settings().database.url:
        console.print("[red]Error:[/] DATABASE__URL not set")
        sys.exit(1)

    asyncio.run(_backfill(dry_run=args.dry_run))
