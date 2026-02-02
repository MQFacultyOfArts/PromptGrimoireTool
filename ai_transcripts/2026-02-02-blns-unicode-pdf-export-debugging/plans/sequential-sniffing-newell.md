# Plan: Add Janitor Thread for JSON File Cleanup

## Problem

The current architecture writes one JSON file per (result_id, category_id) pair to `out/`. At full scale:
- 6,440 results × 21 categories = **135,240 files** in a single directory
- This creates filesystem pressure, slow `ls`/`glob` operations, and Syncthing overhead

## Proposed Solution: Janitor Thread

Add a dedicated "janitor" thread to `unified_processor.py` that continuously:
1. Scans for completed JSON files
2. Imports them to SQLite (INSERT OR IGNORE)
3. Deletes the JSON file after confirmed write

This keeps the file count low during processing while maintaining crash-safety.

### Architecture

```
                                    ┌─────────────────┐
                                    │  Reader Thread  │
                                    │  (DB → queue)   │
                                    └────────┬────────┘
                                             │
                                             ▼
┌─────────────────┐              ┌─────────────────────┐
│  Janitor Thread │◄─────────── │     work_queue      │
│  (JSON → DB)    │              └──────────┬──────────┘
└────────┬────────┘                         │
         │                                  ▼
         │                       ┌─────────────────────┐
         ▼                       │   Worker Threads    │
    ┌─────────┐                  │   (HTTP requests)   │
    │  SQLite │                  └──────────┬──────────┘
    │   DB    │                             │
    └─────────┘                             ▼
                                 ┌─────────────────────┐
                                 │    out/*.json       │
                                 │   (temp storage)    │
                                 └─────────────────────┘
```

### Key Design Decisions

1. **Janitor runs in separate thread** - Single SQLite writer, no contention
2. **Batch imports** - Janitor collects files, imports in batches (e.g., 50 at a time)
3. **Delete after commit** - Only delete JSON after SQLite transaction commits
4. **Graceful shutdown** - On stop, janitor does final sweep before exit
5. **File age check** - Only process files older than N seconds (avoid race with workers)

### Implementation Details

#### New function: `janitor_thread_fn()`

```python
def janitor_thread_fn(
    db_path: str,
    output_dir: Path,
    stop_event: threading.Event,
    metrics: Metrics,
    batch_size: int = 50,
    min_age_seconds: float = 2.0,
) -> None:
    """
    Janitor thread: import JSON files to DB, delete after confirmed write.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    total_imported = 0
    total_deleted = 0

    while not stop_event.is_set():
        # Find JSON files older than min_age_seconds
        now = time.time()
        candidates = []
        for f in output_dir.glob("r*_c*.json"):
            if now - f.stat().st_mtime >= min_age_seconds:
                candidates.append(f)

        if not candidates:
            time.sleep(1.0)
            continue

        # Process batch
        batch = candidates[:batch_size]
        imported_files = []

        for json_file in batch:
            try:
                data = json.loads(json_file.read_text())
                cursor.execute("""
                    INSERT OR IGNORE INTO result_category
                    (result_id, category_id, match, reasoning_trace)
                    VALUES (?, ?, ?, ?)
                """, (data["result_id"], data["category_id"],
                      data["match"], data.get("reasoning_trace", "")))

                if cursor.rowcount > 0:
                    for bq in data.get("blockquotes", []):
                        cursor.execute("""
                            INSERT INTO result_category_blockquote
                            (result_id, category_id, blockquote)
                            VALUES (?, ?, ?)
                        """, (data["result_id"], data["category_id"], bq))

                imported_files.append(json_file)
            except Exception as e:
                log(f"Janitor: error processing {json_file.name}: {e}")

        # Commit then delete
        conn.commit()

        for f in imported_files:
            f.unlink()
            total_deleted += 1

        total_imported += len(imported_files)

        if imported_files:
            log(f"Janitor: imported {len(imported_files)} files, {total_deleted} total deleted")

    # Final sweep on shutdown
    # ... (same logic, but without stop_event check)

    conn.close()
```

#### Modifications to `process_corpus()`

1. Start janitor thread alongside reader and sampler
2. Pass `--enable-janitor` flag (default: off for backwards compatibility)
3. Add janitor stats to final summary

### CLI Changes

```bash
uv run python unified_processor.py \
    --db corpus.db \
    --output-dir out/ \
    --server-url http://localhost:8000 \
    --concurrency 128 \
    --enable-janitor              # NEW: enable cleanup
    --janitor-batch-size 50       # NEW: optional tuning
    --janitor-min-age 2.0         # NEW: seconds before eligible
```

### Alternative Considered: Subdirectories

Instead of cleaning up, reduce per-directory pressure:

```
out/
├── 000/     # results 0-999
│   ├── r10_c1.json
│   └── r10_c2.json
├── 001/     # results 1000-1999
│   └── r1050_c5.json
```

**Rejected because**:
- Still accumulates files (just in more directories)
- Complicates `import_results.py`
- Doesn't solve Syncthing overhead

### Files to Modify

| File | Change |
|------|--------|
| [unified_processor.py](unified_processor.py) | Add `janitor_thread_fn()`, CLI flags, thread orchestration |

### Testing Plan

1. Run with `--limit 100 --enable-janitor`
2. Verify JSON files are being deleted during processing
3. Verify database has all results after completion
4. Verify `out/` directory has low file count during run
5. Test crash recovery: kill mid-run, restart, verify no data loss

### Rollback

The janitor is opt-in (`--enable-janitor`). Default behaviour unchanged.
If problems occur:
- Remove flag to disable
- Run `import_results.py` manually to import any remaining JSONs
