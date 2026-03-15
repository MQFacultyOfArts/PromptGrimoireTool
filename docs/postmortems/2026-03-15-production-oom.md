# Post-Mortem: 2026-03-15 Production OOM Outage

*Written: 2026-03-15*

## Timeline (AEDT)

| Time | Event |
|------|-------|
| 06:13–06:16 | `unattended-upgrade` installs kernel 6.8.0-106 (not direct cause) |
| ~09:34 | Student (TRAN8304 student) clicks PDF export on workspace `ead417b9` |
| 09:36:47 | Export #1 times out after 120s — `LaTeXCompilationError` |
| 09:36:52 | Student retries immediately |
| 09:38:52 | Export #2 times out |
| 09:40:17 | Export #3 starts |
| 09:42:17 | Export #3 times out |
| 09:45:34 | Export #4 starts |
| 09:47:39 | Export #4 times out |
| 10:01:44 | Export #5 starts (different workspace) |
| 10:02:45 | `systemd-journald: Under memory pressure, flushing caches` |
| 10:03–10:06 | Memory pressure messages accelerating every 10–15s |
| 10:06:38 | `INFO: task haproxy:2389405 blocked for more than 122 seconds` |
| 10:08:09 | Last journal entry — system dead |
| ~10:30 | Hard reboot from NCI console |
| 10:31:39 | System boots, fsck recovers journal + 6 orphaned inodes |
| 10:32:59 | System fully up after second boot (first boot was the failed reboot attempt) |

## Root Cause

**Two bugs combined to cause a cascading OOM on a swapless 8 GB VM.**

### Bug 1: `\annot` macro hangs lualatex inside longtable cells

The student's document (translation studies, CJK content) contained highlight annotations inside HTML tables. The LaTeX export pipeline placed `\annot` macros (which contain `\par` via `\marginalia`/`\parbox`) inside `longtable` l-column cells. When `luatexja` is loaded (for CJK font support), this causes a pathological hang — compilation takes 39+ minutes instead of 5 seconds.

The existing `_move_annots_outside_restricted()` post-processor only handled brace-depth restrictions, not table-cell boundaries.

### Bug 2: `compile_latex()` leaked orphaned lualatex processes on timeout

`latexmk` is a Perl script that spawns `lualatex` as a child process. When the 120-second timeout fired, `proc.kill()` sent SIGKILL to the `latexmk` (Perl) process only. The `lualatex` grandchild process continued running as an orphan, consuming ~500 MB–1.25 GB of memory indefinitely.

Each retry by the student leaked another orphaned `lualatex` process. After 5 retries, approximately 2.5–6 GB of memory was consumed by orphaned processes on a VM with 8 GB RAM and no swap.

### Contributing factors

- **No swap**: The VM had zero swap configured. The OOM killer had no buffer before killing processes, and killed `sshd` alongside application processes — making the box completely unresponsive.
- **No concurrency limit**: Multiple LaTeX compilations could run simultaneously with no cap.
- **No per-user rate limiting**: The UI button disabled during export, but multiple tabs could stack requests.
- **HAProxy apparmor audit spam**: Thousands of `apparmor="DENIED"` messages for `rsyslogd` accessing HAProxy's chroot log socket flooded the journal, making it harder to spot real issues.
- **`.nicegui` read-only error**: `ProtectSystem=strict` in the systemd service made `/opt/promptgrimoire/.nicegui` read-only. NiceGUI logged an error on every login. Not crash-causing but noisy.

## Impact

- **Duration**: ~30 minutes of total unavailability (10:08–10:32 AEDT)
- **Users affected**: Any student or instructor attempting to access the application during the outage window
- **Data loss**: None — PostgreSQL recovered cleanly, CRDT state preserved
- **Recovery method**: Hard reboot from NCI Cloud console (SSH was dead)

## Fixes Applied

### Immediate (server-side, 2026-03-15)

| Fix | Effect |
|-----|--------|
| 2 GB swapfile added (`/swapfile`, persisted in `/etc/fstab`) | OOM killer won't kill sshd; admin can intervene |
| systemd override: `MemoryMax=6G` | App can't consume more than 6 GB, leaving 2 GB for OS/sshd/PostgreSQL |
| systemd override: `OOMScoreAdjust=500` | Kernel kills app before sshd |
| systemd override: `ReadWritePaths` includes `.nicegui` | Silences the Errno 30 error on every login |

### Code fixes (PR #348, merged 2026-03-15)

| Fix | File | Effect |
|-----|------|--------|
| Process group kill | `export/pdf.py` | `start_new_session=True` + `os.killpg()` kills entire latexmk→lualatex process tree on timeout |
| Concurrency semaphore | `export/pdf.py` | `asyncio.Semaphore(2)` caps concurrent LaTeX compilations server-wide |
| Per-user export lock | `pages/annotation/pdf_export.py` | `asyncio.Lock` per user prevents retry stacking across tabs |
| Error message | `pages/annotation/pdf_export.py` | "Do not retry. Contact your unit convenor." |

### Code fixes (main, 2026-03-15)

| Fix | File | Effect |
|-----|------|--------|
| Suppress test alerts | `logging_discord.py` | Discord webhook doesn't fire during test harness |
| Server hostname in alerts | `logging_discord.py` | Alerts show which server fired |

### Pending

| Fix | Status |
|-----|--------|
| Move `\annot` macros outside longtable cells | In progress (separate branch) |
| Rehydrate workspace `ead417b9` as test fixture | Blocked on annot fix |

## Lessons Learned

1. **Subprocess cleanup must kill the process group, not just the parent.** Any code that spawns a process which itself spawns children must use `start_new_session=True` and `os.killpg()` on cleanup.

2. **Swapless VMs are fragile.** Even 2 GB of swap buys enough time for the OOM killer to work and for sshd to survive.

3. **systemd resource limits are free safety.** `MemoryMax` and `OOMScoreAdjust` take 2 lines and prevent an application from killing the operating system.

4. **User-facing error messages should discourage retries.** A retry button on a 120-second timeout is an invitation to stack processes.

5. **LaTeX compilation is untrusted input processing.** User content drives the .tex file. Pathological inputs (CJK + tables + annotations) can cause unbounded resource consumption. The compilation pipeline needs the same defence-in-depth as any input processing boundary.
