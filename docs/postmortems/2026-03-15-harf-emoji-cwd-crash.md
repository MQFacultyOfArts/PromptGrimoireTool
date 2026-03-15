# Root Cause: luaotfload harf-plug crash on server (color emoji PNG cache)

**Date:** 2026-03-15
**Issue:** #351 (discovered during UAT of PR #356)
**Symptom:** Yuki workspace PDF export produces corrupt/empty PDF on production server; compiles fine locally from identical .tex file.

## Root Cause

`luaotfload`'s HarfBuzz color-emoji shaper (`harf-plug.lua:713-726`) writes bitmap glyph data as PNG cache files to a temp directory:

```lua
tmpdirname = tmpdirname or os.tmpdir()
local path = format('%s/%i.png', tmpdirname, tmpcount)
io.open(path, "wb"):write(data):close()
```

The immediate failure was not "generic HarfBuzz shaping". It was the PNG cache write path itself: if `io.open(path, "wb")` returns `nil`, the chained `:write(...)` raises `attempt to index a nil value` at line 721.

Under the production systemd service:
- `ProtectSystem=strict` makes the filesystem read-only except for explicitly listed `ReadWritePaths`
- `WorkingDirectory=/opt/promptgrimoire` (read-only)
- `PrivateTmp=true` provides a writable `/tmp`, but LuaTeX's temp-dir handling in this code path proved cwd-sensitive rather than reliably landing in a writable location under the service sandbox

The `asyncio.create_subprocess_exec()` call in `pdf.py` did not set `cwd`, so the LuaTeX subprocess inherited the service's read-only working directory. In that context, LuaTeX's temp-dir resolution for the color-emoji PNG cache did not yield a usable writable path. That made `io.open(path, "wb")` return `nil`, which then crashed with `attempt to index a nil value` at `harf-plug.lua:721`.

## Why It Worked Locally

The developer's working directory is writable. In that context, LuaTeX's temp-path handling produced a usable writable location for the PNG cache. The same .tex, same engine, same font, same luaotfload — different cwd writability.

## Confirmed By

Running the exact failing .tex on the server from a writable cwd (`/tmp/yuki-debug` with `chmod 777`) produced a valid 18-page, 193KB PDF identical to local output.

## What We Ruled Out

- **Different TeX/font versions:** local and server matched on LuaHBTeX version, `luaotfload` version, `luaotfload-harf-plug.lua` md5, and `NotoColorEmoji.ttf` md5.
- **Corrupt/stale local-only artifact theory:** once clean server `.tex/.log/.pdf` were recopied, the server log clearly showed the `promptgrimoire` user environment and the same `harf-plug.lua:721` failure.
- **Memory pressure / OOM:** the TeX log showed a normal Lua error at the PNG cache write site, not an OOM kill. This was not a `MemoryMax=6G` issue.
- **Annotated table logic as the immediate trigger:** the failing line was an `AccSupp`-wrapped emoji in a regular paragraph, not a table cell. The table fix exposed the issue during UAT, but was not the direct crash mechanism.

## Fix

Pass `cwd=str(output_dir)` to `asyncio.create_subprocess_exec()` in `src/promptgrimoire/export/pdf.py:_run_latexmk()`. The `output_dir` is always a writable temp directory created by the export pipeline.

## Verification

The discriminating test was:

1. Export the failing Yuki workspace on the server and capture the exact `.tex/.log/.pdf`.
2. Run that exact `.tex` under the server TeX install from a writable directory.
3. Observe that the document compiles successfully without changing fonts, TeX packages, or content.

That isolated the variable to service execution context, specifically writable temp-path resolution for the emoji PNG cache.

## Environment Details

| Component | Value |
|-----------|-------|
| LuaHBTeX | 1.24.0 (TeX Live 2026) |
| luaotfload | v3.29 (2024-12-03) |
| harf-plug.lua md5 | `6257d6011bc38cd0b21efba6f7385ef4` |
| NotoColorEmoji.ttf md5 | `d199a086f11e2b86232ec35c8b9617ff` |
| systemd | `ProtectSystem=strict`, `PrivateTmp=true` |
| Service WorkingDirectory | `/opt/promptgrimoire` (read-only) |

## Process Notes

This bug was found during UAT of the CJK + annotated table fix (PR #356). Initial investigation was hampered by:

1. **Evidence contamination** — compiling the server .tex locally in the same scratch directory overwrote the original server log/pdf
2. **Premature fix attempts** — proposed code changes before isolating root cause
3. **Collapsed hypotheses** — treated `jacharrange`, `luatexja`, `harf`, `AccSupp`, and service environment as a single variable instead of testing independently

Correct diagnosis came from recognizing that `harf-plug.lua:721` is the PNG cache write path, not the core shaping algorithm. The fix follows from that narrower mechanism: give LuaTeX a writable working directory for temp PNG emission rather than changing fonts or weakening the systemd sandbox.
