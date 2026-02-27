#!/usr/bin/env python3
"""Backfill paragraph maps for existing WorkspaceDocument rows.

Thin wrapper around ``promptgrimoire.cli_backfill`` for standalone use.

Usage:
    uv run backfill-paragraph-maps              # via pyproject.toml entry point
    uv run backfill-paragraph-maps --dry-run    # report without modifying
    uv run python scripts/backfill_paragraph_maps.py --dry-run
"""

from promptgrimoire.cli_backfill import main

if __name__ == "__main__":
    main()
