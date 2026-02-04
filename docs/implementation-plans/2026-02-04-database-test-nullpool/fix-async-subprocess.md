# Fix: Async Subprocess for PDF Export

**Issue:** `test_cross_env_highlight_compiles_to_pdf` fails with xdist parallelism due to event loop collision.

**Root Cause Chain:**
1. `subprocess.run()` in `pdf.py` is synchronous
2. `export_annotation_pdf()` is async but wraps sync subprocess call
3. `pdf_exporter` fixture uses `asyncio.run()` to call async from sync test
4. Test is sync, but `reset_db_engine_per_test` is async autouse fixture
5. With xdist, pytest-asyncio tries to run async fixture against sync test → event loop collision

**Fix:**
1. Convert `subprocess.run()` to `asyncio.create_subprocess_exec()` in `pdf.py`
2. Make `pdf_exporter` fixture async (remove `asyncio.run()` wrapper)
3. Make PDF tests async

**Files to modify:**
- `src/promptgrimoire/export/pdf.py` - async subprocess
- `tests/conftest.py` - async `pdf_exporter` fixture
- `tests/integration/test_cross_env_highlights.py` - async test
- Any other tests using `pdf_exporter`

**Async subprocess pattern:**
```python
proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd=work_dir,
)
stdout, stderr = await proc.communicate()
if proc.returncode != 0:
    raise subprocess.CalledProcessError(proc.returncode, cmd, stdout, stderr)
```

**Discovered during:** Phase 2 verification of database-test-nullpool implementation
