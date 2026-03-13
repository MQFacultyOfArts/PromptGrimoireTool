#!/usr/bin/env python3
"""Fetch LaTeX export logs from systemd PrivateTmp directories.

systemd's PrivateTmp=true isolates /tmp inside the service namespace,
making export logs invisible to normal users.  This script discovers
the private tmp path and retrieves logs.

Usage:
    # List all export directories (most recent first)
    sudo python3 scripts/fetch_export_logs.py

    # Filter by workspace ID prefix
    sudo python3 scripts/fetch_export_logs.py 8859bf9a

    # Filter by filename fragment
    sudo python3 scripts/fetch_export_logs.py Savage

    # Copy log to stdout
    sudo python3 scripts/fetch_export_logs.py 8859bf9a --cat

    # Copy log + tex to a local directory
    sudo python3 scripts/fetch_export_logs.py 8859bf9a --copy-to /tmp/debug

Requires root (sudo) to traverse systemd private tmp directories.
"""

from __future__ import annotations

import argparse
import datetime
import shutil
import sys
import tempfile
from pathlib import Path

SERVICE_NAME = "promptgrimoire.service"
EXPORT_PREFIX = "promptgrimoire_export_"


def find_private_tmp() -> Path | None:
    """Find the systemd PrivateTmp base for the promptgrimoire service."""
    tmp_root = Path(tempfile.gettempdir())
    matches = sorted(
        tmp_root.glob(f"systemd-private-*-{SERVICE_NAME}-*/tmp"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if matches:
        return matches[0]
    return None


def find_export_dirs(base: Path) -> list[Path]:
    """Find all promptgrimoire export directories, newest first."""
    dirs = [
        d for d in base.iterdir() if d.is_dir() and d.name.startswith(EXPORT_PREFIX)
    ]
    return sorted(dirs, key=lambda d: d.stat().st_mtime, reverse=True)


def match_filter(export_dir: Path, query: str) -> bool:
    """Check if an export dir matches the query.

    Matches against:
    - The directory name (includes workspace ID prefix if recent code)
    - Any .tex/.log filenames inside the directory
    """
    query_lower = query.lower()

    # Match dir name (e.g. promptgrimoire_export_8859bf9a_abc123)
    if query_lower in export_dir.name.lower():
        return True

    # Match filenames inside (e.g. JJ_Savage_Sons_v_Blakney)
    return any(query_lower in child.name.lower() for child in export_dir.iterdir())


def format_dir_info(export_dir: Path) -> str:
    """Format a single export dir for display."""
    mtime = export_dir.stat().st_mtime
    dt = datetime.datetime.fromtimestamp(mtime)
    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")

    # Extract workspace ID from dir name if present
    # Format: promptgrimoire_export_<ws_id_8>_<random>
    dir_suffix = export_dir.name[len(EXPORT_PREFIX) :]
    parts = dir_suffix.split("_", 1)
    ws_prefix = parts[0] if len(parts) > 1 and len(parts[0]) == 8 else "unknown"

    # Find tex/log files
    tex_files = list(export_dir.glob("*.tex"))
    log_files = list(export_dir.glob("*.log"))
    pdf_files = list(export_dir.glob("*.pdf"))

    tex_name = tex_files[0].stem if tex_files else "(no .tex)"

    status = "PDF" if pdf_files else "FAILED" if log_files else "empty"

    return (
        f"  {timestamp}  ws={ws_prefix}  [{status}]\n"
        f"    dir:  {export_dir.name}\n"
        f"    doc:  {tex_name}"
    )


def cat_log(export_dir: Path) -> None:
    """Print the .log file to stdout."""
    log_files = list(export_dir.glob("*.log"))
    if not log_files:
        print(f"No .log file in {export_dir}", file=sys.stderr)
        sys.exit(1)

    log_path = log_files[0]
    print(f"=== {log_path.name} ===", file=sys.stderr)
    sys.stdout.write(log_path.read_text(errors="replace"))


def copy_to(export_dir: Path, dest: Path) -> None:
    """Copy .log and .tex files to a destination directory."""
    dest.mkdir(parents=True, exist_ok=True)

    copied = []
    for ext in ("*.log", "*.tex", "*.pdf"):
        for f in export_dir.glob(ext):
            target = dest / f.name
            shutil.copy2(f, target)
            copied.append(target)

    if copied:
        print(f"Copied {len(copied)} files to {dest}:")
        for c in copied:
            print(f"  {c}")
    else:
        print(f"No log/tex/pdf files found in {export_dir}", file=sys.stderr)


def _collect_export_dirs() -> tuple[Path | None, list[tuple[str, Path]]]:
    """Discover export dirs from systemd private tmp and local tmp."""
    private_tmp = find_private_tmp()
    plain_tmp = Path(tempfile.gettempdir())

    bases: list[tuple[str, Path]] = []
    if private_tmp:
        bases.append(("systemd", private_tmp))
    bases.append(("local", plain_tmp))

    all_dirs: list[tuple[str, Path]] = []
    for label, base in bases:
        for d in find_export_dirs(base):
            all_dirs.append((label, d))

    all_dirs.sort(key=lambda x: x[1].stat().st_mtime, reverse=True)
    return private_tmp, all_dirs


def _list_dirs(
    all_dirs: list[tuple[str, Path]],
    has_private: bool,
) -> None:
    """Print export directories to stdout."""
    print(f"Found {len(all_dirs)} export directories:\n")
    for label, d in all_dirs:
        source = f"[{label}]" if has_private else ""
        print(f"{source}")
        print(format_dir_info(d))
        print()


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Fetch LaTeX export logs from systemd PrivateTmp",
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Filter: workspace ID prefix, filename fragment, or dir name",
    )
    parser.add_argument(
        "--cat",
        action="store_true",
        help="Print the .log file to stdout",
    )
    parser.add_argument(
        "--copy-to",
        metavar="DIR",
        help="Copy log/tex/pdf files to this directory",
    )
    parser.add_argument(
        "--service",
        default=SERVICE_NAME,
        help=f"systemd service name (default: {SERVICE_NAME})",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    private_tmp, all_dirs = _collect_export_dirs()

    if not all_dirs:
        print("No export directories found.", file=sys.stderr)
        return 1

    if args.query:
        all_dirs = [(label, d) for label, d in all_dirs if match_filter(d, args.query)]
        if not all_dirs:
            print(f"No export directories matching '{args.query}'", file=sys.stderr)
            return 1

    if args.cat or args.copy_to:
        _, target_dir = all_dirs[0]
        if args.cat:
            cat_log(target_dir)
        if args.copy_to:
            copy_to(target_dir, Path(args.copy_to))
        return 0

    _list_dirs(all_dirs, has_private=private_tmp is not None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
