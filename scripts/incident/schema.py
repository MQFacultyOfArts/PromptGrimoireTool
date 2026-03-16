"""SQLite schema for incident analysis database."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

# ruff: noqa: E501 — SQL readability trumps line-length lint.
SCHEMA_DDL = """\
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    format TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    size INTEGER NOT NULL,
    mtime INTEGER NOT NULL,
    hostname TEXT NOT NULL,
    timezone TEXT NOT NULL,
    window_start_utc TEXT NOT NULL,
    window_end_utc TEXT NOT NULL,
    ingested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS journal_events (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    ts_utc TEXT NOT NULL,
    priority INTEGER,
    pid INTEGER,
    unit TEXT,
    message TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS jsonl_events (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    ts_utc TEXT NOT NULL,
    level TEXT,
    event TEXT,
    user_id TEXT,
    workspace_id TEXT,
    request_path TEXT,
    exc_info TEXT,
    extra_json TEXT
);

CREATE TABLE IF NOT EXISTS haproxy_events (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    ts_utc TEXT NOT NULL,
    client_ip TEXT,
    status_code INTEGER,
    tr_ms INTEGER,
    tw_ms INTEGER,
    tc_ms INTEGER,
    tr_resp_ms INTEGER,
    ta_ms INTEGER,
    backend TEXT,
    server TEXT,
    method TEXT,
    path TEXT,
    bytes_read INTEGER
);

CREATE TABLE IF NOT EXISTS pg_events (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    ts_utc TEXT NOT NULL,
    pid INTEGER,
    level TEXT,
    error_type TEXT,
    detail TEXT,
    statement TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS beszel_metrics (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    ts_utc TEXT NOT NULL,
    cpu REAL,
    mem_used REAL,
    mem_percent REAL,
    net_sent REAL,
    net_recv REAL,
    disk_read REAL,
    disk_write REAL,
    load_1 REAL,
    load_5 REAL,
    load_15 REAL
);

CREATE INDEX IF NOT EXISTS idx_journal_ts ON journal_events(ts_utc);
CREATE INDEX IF NOT EXISTS idx_jsonl_ts ON jsonl_events(ts_utc);
CREATE INDEX IF NOT EXISTS idx_haproxy_ts ON haproxy_events(ts_utc);
CREATE INDEX IF NOT EXISTS idx_pg_ts ON pg_events(ts_utc);
CREATE INDEX IF NOT EXISTS idx_beszel_ts ON beszel_metrics(ts_utc);

CREATE VIEW IF NOT EXISTS timeline AS
SELECT source_id, ts_utc, 'journal' AS source, priority AS level_or_status, message, NULL AS extra
FROM journal_events
UNION ALL
SELECT source_id, ts_utc, 'jsonl' AS source, level AS level_or_status, event AS message, extra_json AS extra
FROM jsonl_events
UNION ALL
SELECT source_id, ts_utc, 'haproxy' AS source, CAST(status_code AS TEXT) AS level_or_status,
       method || ' ' || path AS message, NULL AS extra
FROM haproxy_events
UNION ALL
SELECT source_id, ts_utc, 'pglog' AS source, level AS level_or_status, message, detail AS extra
FROM pg_events
ORDER BY ts_utc;
"""


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all tables, indexes, and views. Enable WAL mode."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA_DDL)
