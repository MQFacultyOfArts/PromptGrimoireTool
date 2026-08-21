"""Run provenance and server-side page-load stats for the perf probes.

Every latency number the soak and cram probes print is browser-observed:
it includes Playwright, the co-located browser's own CPU contention, and
the render, so it is not a production-magnitude claim (failure-mode class
G, CLAUDE.md).  The server's own ``page_load_profile`` event is the
production-magnitude number, and this module reads it back out of the
structlog JSONL the measured server writes.

Locating that file needs no new plumbing.  ``setup_logging()`` logs its
absolute path as its final startup line, and ``_start_e2e_server`` sends
the server's stdout to ``test-e2e-server.log``, so the path is readable
from the harness process (same strategy as ``ServerLogReader`` in
``test_browser_perf_377.py``, plus the rotated backups a multi-minute run
produces).

Three sources of provenance land in the run JSON, weakest first:

- ``run_meta.env`` -- the harness process's raw environment.
- ``run_meta.snapshot_enabled`` -- the harness process's resolved config.
  Both processes read the same ``.env`` and the server inherits the
  harness environment, so this is an inference about the server, not an
  observation of it.
- ``server_page_load`` -- read off the measured server's own log lines:
  its pid, branch, commit, chosen pool mode, and (when the snapshot
  service served bundles during the run) a nonzero ``snapshot_served``.
  A run whose ``snapshot_enabled`` is true while ``snapshot_served`` is
  zero is contradicted by its own evidence.
"""

from __future__ import annotations

import json
import math
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping

PAGE_LOAD_EVENT = "page_load_profile"
POOL_MODE_EVENT = "db_pool_mode"
SNAPSHOT_SERVED_EVENT = "snapshot_served"
_TRACKED_EVENTS = frozenset({PAGE_LOAD_EVENT, POOL_MODE_EVENT, SNAPSHOT_SERVED_EVENT})

# Phases aggregated from each page_load_profile event.  total_ms is the
# production-magnitude page-load number; the other two say where it went.
_PHASE_KEYS = ("total_ms", "db_resolve_ms", "tab_panels_ms")

# The route whose page loads the probes are measuring.  A profile from
# another route is excluded and counted; an *unbound* path is kept, so a
# build that stops binding request_path reports its loads rather than a
# confident zero.
_MEASURED_PATH_PREFIX = "/annotation"

# Recorded verbatim in run_meta: the pool-mode and snapshot switches that
# decide what a run actually measured.  A name absent from the harness
# environment records as null, so the key means the same thing whichever
# way the sibling pool work names its flags.
PROVENANCE_ENV_VARS = (
    "SNAPSHOT__ENABLED",
    "_PROMPTGRIMOIRE_USE_NULL_POOL",
    "_PROMPTGRIMOIRE_POOL_FIDELITY",
    "_PROMPTGRIMOIRE_WORKER_NULLPOOL",
    "DATABASE__USE_NULL_POOL",
    "E2E_RECONNECT_TIMEOUT",
    "E2E_INSTRUMENT_OUTBOX",
)

# Recorded as presence booleans only -- these hold DSNs with credentials.
_PRESENCE_ONLY_ENV_VARS = (
    "E2E_PERF_DATABASE_URL",
    "DATABASE__URL",
)

DEFAULT_SERVER_STDOUT_LOG = Path("test-e2e-server.log")
_LOG_PATH_MARKER = "Log file: "
_STARTUP_LINES_SCANNED = 20


def utc_now() -> datetime:
    """Current UTC time, for the run-window bounds."""
    return datetime.now(UTC)


def iso(moment: datetime) -> str:
    """Render *moment* the way structlog renders its timestamps."""
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_ts(value: object) -> datetime | None:
    """Parse a structlog ISO timestamp; None when unusable."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _stats(values: list[float]) -> dict[str, float] | None:
    """Nearest-rank p50/p95 with max and mean; None for no samples.

    None rather than zeros: an empty aggregate must not read as a page
    that loaded instantly.
    """
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)

    def at(quantile: float) -> float:
        return ordered[min(n - 1, max(0, math.ceil(quantile * n) - 1))]

    return {
        "p50": round(at(0.50), 1),
        "p95": round(at(0.95), 1),
        "max": round(ordered[-1], 1),
        "mean": round(sum(ordered) / n, 1),
    }


def _is_measured_path(record: dict[str, Any]) -> bool:
    """Whether a page_load_profile belongs to the measured route."""
    path = record.get("request_path")
    if not isinstance(path, str):
        return True
    return path.startswith(_MEASURED_PATH_PREFIX)


@dataclass
class _Scan:
    """Running totals for one pass over the server's log lines."""

    samples: dict[str, list[float]] = field(
        default_factory=lambda: {key: [] for key in _PHASE_KEYS}
    )
    pids: Counter[str] = field(default_factory=Counter)
    branches: Counter[str] = field(default_factory=Counter)
    commits: Counter[str] = field(default_factory=Counter)
    pool_modes: dict[str, dict[str, Any]] = field(default_factory=dict)
    earliest_log_ts: datetime | None = None
    lines_scanned: int = 0
    unparsed_lines: int = 0
    before_window: int = 0
    after_window: int = 0
    other_path: int = 0
    snapshot_served: int = 0

    def add_profile(self, record: dict[str, Any]) -> None:
        """Fold one in-window, on-route page_load_profile into the stats."""
        self.pids[str(record.get("pid"))] += 1
        if isinstance(branch := record.get("branch"), str):
            self.branches[branch] += 1
        if isinstance(commit := record.get("commit"), str):
            self.commits[commit] += 1
        for key in _PHASE_KEYS:
            if isinstance(value := record.get(key), int | float):
                self.samples[key].append(float(value))


def _consume(
    scan: _Scan,
    record: dict[str, Any],
    timestamp: datetime,
    *,
    window_start: datetime,
    window_end: datetime,
) -> None:
    """Fold one parsed log record into *scan*."""
    event = record.get("event")
    in_window = window_start <= timestamp <= window_end

    if event == POOL_MODE_EVENT:
        # Emitted once at engine init, ahead of the run window; keep the
        # latest per pid and pick the server's after the scan.
        if timestamp <= window_end:
            scan.pool_modes[str(record.get("pid"))] = {
                "mode": record.get("mode"),
                "reason": record.get("reason"),
                "timestamp": record.get("timestamp"),
            }
        return

    if event == SNAPSHOT_SERVED_EVENT:
        if in_window:
            scan.snapshot_served += 1
        return

    if event != PAGE_LOAD_EVENT:
        return
    if not in_window:
        if timestamp < window_start:
            scan.before_window += 1
        else:
            scan.after_window += 1
        return
    if not _is_measured_path(record):
        scan.other_path += 1
        return
    scan.add_profile(record)


def _scan_lines(
    lines: Iterable[str],
    *,
    window_start: datetime,
    window_end: datetime,
) -> _Scan:
    """Parse *lines*, folding tracked events into a :class:`_Scan`."""
    scan = _Scan()
    for raw_line in lines:
        scan.lines_scanned += 1
        line = raw_line.strip()
        if not line:
            continue
        # Cheap reject before JSON parsing: a soak scans tens of MB and
        # only three event types matter.  The first line is parsed
        # regardless, since it dates the oldest retained log.
        interesting = any(event in line for event in _TRACKED_EVENTS)
        if not interesting and scan.earliest_log_ts is not None:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            scan.unparsed_lines += 1
            continue
        timestamp = (
            _parse_ts(record.get("timestamp")) if isinstance(record, dict) else None
        )
        if timestamp is None:
            scan.unparsed_lines += 1
            continue
        if scan.earliest_log_ts is None:
            scan.earliest_log_ts = timestamp
        if interesting:
            _consume(
                scan,
                record,
                timestamp,
                window_start=window_start,
                window_end=window_end,
            )
    return scan


def summarise_page_load_profile(
    lines: Iterable[str],
    *,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, Any]:
    """Aggregate server-side page-load events over the run window.

    *lines* are raw JSONL log lines in chronological order (rotated
    backups first).  Only ``page_load_profile`` events inside
    ``[window_start, window_end]`` feed the latency statistics.

    The returned ``coverage`` block states what the scan could see:
    ``earliest_log_ts`` with ``window_start_covered`` says whether
    rotation discarded the head of the window, in which case ``count`` is
    a lower bound rather than the run's load total.  Events dropped by
    the window or the route filter are counted rather than discarded
    silently, so a zero aggregate can be told apart from a filter that
    matched nothing.
    """
    scan = _scan_lines(lines, window_start=window_start, window_end=window_end)
    earliest_log_ts = scan.earliest_log_ts
    server_pid = scan.pids.most_common(1)[0][0] if scan.pids else None
    summary: dict[str, Any] = {
        "count": sum(scan.pids.values()),
        "pids": dict(scan.pids),
        "server_pid": int(server_pid) if server_pid is not None else None,
        "server_branch": (
            scan.branches.most_common(1)[0][0] if scan.branches else None
        ),
        "server_commit": scan.commits.most_common(1)[0][0] if scan.commits else None,
        "pool_mode": scan.pool_modes.get(server_pid) if server_pid else None,
        "snapshot_served": scan.snapshot_served,
        "coverage": {
            "window_start": iso(window_start),
            "window_end": iso(window_end),
            "lines_scanned": scan.lines_scanned,
            "unparsed_lines": scan.unparsed_lines,
            "earliest_log_ts": iso(earliest_log_ts) if earliest_log_ts else None,
            "window_start_covered": (
                earliest_log_ts is not None and earliest_log_ts <= window_start
            ),
            "profiles_before_window": scan.before_window,
            "profiles_after_window": scan.after_window,
            "profiles_other_path": scan.other_path,
        },
    }
    summary.update({key: _stats(scan.samples[key]) for key in _PHASE_KEYS})
    return summary


def find_server_jsonl(
    server_stdout_log: Path = DEFAULT_SERVER_STDOUT_LOG,
) -> tuple[Path | None, str]:
    """Resolve the JSONL file the measured server is writing to.

    ``setup_logging()`` ends with "Structured logging configured. Log
    file: <abs path>", which the E2E CLI captures in
    ``test-e2e-server.log``.  That names the file of the process actually
    under measurement.

    Returns the path and the strategy that found it.  The strategy is
    reported in the run JSON because the two are not equally
    trustworthy: ``startup_line`` names the measured process's own file,
    while ``glob_fallback`` picks the newest log under ``logs/`` and can
    land on a different branch's or a previous run's file without any
    other symptom.
    """
    if server_stdout_log.exists():
        with server_stdout_log.open(encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle):
                if line_number >= _STARTUP_LINES_SCANNED:
                    break
                if _LOG_PATH_MARKER not in line:
                    continue
                try:
                    event = json.loads(line).get("event", "")
                except json.JSONDecodeError:
                    event = line
                if not isinstance(event, str):
                    continue
                _, _, tail = event.partition(_LOG_PATH_MARKER)
                candidate = Path(tail.strip())
                if candidate.is_file():
                    return candidate, "startup_line"

    candidates = sorted(
        Path("logs").rglob("promptgrimoire*.jsonl"),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        return None, "not_found"
    return candidates[-1], "glob_fallback"


def rotated_log_paths(base: Path) -> list[Path]:
    """*base* and its RotatingFileHandler backups, oldest first.

    A soak run writes well past the 10 MB rotation threshold, so the
    current file alone holds only the tail of the window.
    """
    backups = sorted(
        (
            path
            for path in base.parent.glob(base.name + ".*")
            if path.suffix.lstrip(".").isdigit()
        ),
        key=lambda path: int(path.suffix.lstrip(".")),
        reverse=True,
    )
    return [*backups, base]


def _iter_lines(paths: Iterable[Path]) -> Iterator[str]:
    """Stream lines from *paths* in order, skipping any that vanished."""
    for path in paths:
        if not path.is_file():
            continue
        with path.open(encoding="utf-8", errors="replace") as handle:
            yield from handle


def collect_server_page_load(
    *,
    window_start: datetime,
    window_end: datetime,
    server_stdout_log: Path = DEFAULT_SERVER_STDOUT_LOG,
) -> dict[str, Any]:
    """Read the server's page-load profile for the run window.

    Returns the aggregate, or an ``unavailable`` block naming what was
    searched -- an unreadable log must be visible as a gap in the
    evidence rather than as an absence of slow page loads.
    """
    if override := os.environ.get("E2E_SERVER_STDOUT_LOG"):
        server_stdout_log = Path(override)
    base, resolved_by = find_server_jsonl(server_stdout_log)
    if base is None:
        return {
            "unavailable": "server JSONL log not located",
            "log_resolved_by": resolved_by,
            "searched": [str(server_stdout_log), "logs/**/promptgrimoire*.jsonl"],
        }
    paths = rotated_log_paths(base)
    summary = summarise_page_load_profile(
        _iter_lines(paths),
        window_start=window_start,
        window_end=window_end,
    )
    summary["log_resolved_by"] = resolved_by
    summary["log_paths"] = [str(path) for path in paths if path.is_file()]
    return summary


def build_run_meta(
    *,
    probe: str,
    env: Mapping[str, str],
    started: datetime,
    ended: datetime,
    knobs: Mapping[str, Any],
    snapshot_enabled: bool,
    branch: str | None,
) -> dict[str, Any]:
    """Describe what this run was, so its JSON stands alone.

    *env* is the harness process's environment (the probe passes
    ``os.environ``); the switches in :data:`PROVENANCE_ENV_VARS` are
    recorded verbatim, and DSN-bearing variables as presence booleans
    only.  ``snapshot_enabled`` is the harness's resolved config, which
    is an inference about the server -- ``server_page_load`` carries the
    server's own account.
    """
    return {
        "probe": probe,
        "started_utc": iso(started),
        "ended_utc": iso(ended),
        "duration_s": round((ended - started).total_seconds(), 1),
        "branch": branch,
        "snapshot_enabled": snapshot_enabled,
        "knobs": dict(knobs),
        "env": {name: env.get(name) for name in PROVENANCE_ENV_VARS}
        | {f"{name}_set": name in env for name in _PRESENCE_ONLY_ENV_VARS},
    }


def print_server_page_load(summary: Mapping[str, Any]) -> None:
    """Print the server-side page-load block next to the browser table."""
    print("--- server-side page load (structlog page_load_profile) ---")
    if "unavailable" in summary:
        print(f"  UNAVAILABLE: {summary['unavailable']}")
        print(f"  searched: {summary['searched']}")
        return
    coverage = summary["coverage"]
    total = summary["total_ms"]
    rendered = (
        "n/a"
        if total is None
        else (
            f"p50={total['p50']}ms p95={total['p95']}ms "
            f"max={total['max']}ms mean={total['mean']}ms"
        )
    )
    print(f"  total_ms n={summary['count']}  {rendered}")
    if db_resolve := summary["db_resolve_ms"]:
        print(
            f"  db_resolve_ms   p50={db_resolve['p50']}ms "
            f"p95={db_resolve['p95']}ms max={db_resolve['max']}ms"
        )
    print(
        f"  pid={summary['server_pid']} commit={summary['server_commit']} "
        f"pool={summary['pool_mode']} snapshot_served={summary['snapshot_served']}"
    )
    print(
        f"  coverage: window_start_covered={coverage['window_start_covered']} "
        f"earliest_log={coverage['earliest_log_ts']} "
        f"lines={coverage['lines_scanned']} "
        f"unparsed={coverage['unparsed_lines']} "
        f"outside_window={coverage['profiles_before_window']}"
        f"/{coverage['profiles_after_window']} "
        f"other_path={coverage['profiles_other_path']}"
    )
