# Incident Analysis Tools Implementation Plan — Phase 1

**Goal:** Bash script on the production server that packages time-windowed telemetry into a provenance-tracked tarball.

**Architecture:** Single bash script following deploy/restart.sh conventions. Exports journal via journalctl (native time filtering), filters JSONL via jq and HAProxy via awk (server-side time windowing), copies PG log in full (multi-line grouping too fragile for bash). Computes sha256 per file, writes manifest.json with provenance metadata, produces gzipped tarball.

**Tech Stack:** Bash, journalctl, sha256sum, jq, tar, timedatectl

**Scope:** Phase 1 of 6 from original design

**Codebase verified:** 2026-03-16

---

## Acceptance Criteria Coverage

This phase implements and tests:

### incident-analysis-tools.AC1: Collection script produces valid tarball
- **incident-analysis-tools.AC1.1 Success:** Running `collect-telemetry.sh --start "2026-03-16 14:50" --end "2026-03-16 17:20"` produces a `.tar.gz` containing journal JSON, JSONL, HAProxy log, PG log, and `manifest.json`
- **incident-analysis-tools.AC1.2 Success:** `manifest.json` contains sha256, size, mtime for each collected file, plus server hostname, timezone, and requested window in both AEDT and UTC
- **incident-analysis-tools.AC1.3 Success:** sha256 values in manifest match `sha256sum` of the corresponding extracted files
- **incident-analysis-tools.AC1.4 Failure:** Missing `--start` or `--end` argument prints usage and exits non-zero
- **incident-analysis-tools.AC1.5 Edge:** Journal export for a window with zero events produces an empty file but still appears in manifest

---

<!-- START_TASK_1 -->
### Task 1: Create deploy/collect-telemetry.sh

**Verifies:** None (infrastructure task — verified operationally)

**Files:**
- Create: `deploy/collect-telemetry.sh`

**Implementation:**

Create a bash script following `deploy/restart.sh` conventions:

```bash
#!/usr/bin/env bash
# collect-telemetry.sh — Package time-windowed telemetry for incident analysis.
#
# Usage:
#   collect-telemetry.sh --start "2026-03-16 14:50" --end "2026-03-16 17:20"
#
# Requires root (reads journal, copies system logs).
# Produces /tmp/telemetry-YYYYMMDD-HHMM.tar.gz with manifest.json.

set -euo pipefail

# -------------------------------------------------------------------
# Configuration — edit these if log paths change on the server
# -------------------------------------------------------------------
JSONL_LOG="/home/promptgrimoire/PromptGrimoireTool/logs/promptgrimoire.jsonl"
HAPROXY_LOG="/var/log/haproxy.log"
PG_LOG_DIR="/var/log/postgresql"
UNIT_NAME="promptgrimoire.service"

# -------------------------------------------------------------------
# Helpers (same pattern as restart.sh)
# -------------------------------------------------------------------
step() { echo "==> $1"; }

usage() {
    cat >&2 <<EOF
Usage: $0 --start "YYYY-MM-DD HH:MM" --end "YYYY-MM-DD HH:MM"

Times are interpreted as local (server timezone, typically AEDT).
Produces /tmp/telemetry-YYYYMMDD-HHMM.tar.gz
EOF
    exit 1
}

# -------------------------------------------------------------------
# Argument parsing
# -------------------------------------------------------------------
START=""
END=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --start) START="$2"; shift 2 ;;
        --end)   END="$2";   shift 2 ;;
        *)       usage ;;
    esac
done

[[ -z "$START" || -z "$END" ]] && usage

# -------------------------------------------------------------------
# Root guard (same pattern as restart.sh)
# -------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: Must run as root (need journal + log access)." >&2
    exit 1
fi

# -------------------------------------------------------------------
# Prepare workspace
# -------------------------------------------------------------------
TIMESTAMP=$(date +%Y%m%d-%H%M)
WORKDIR=$(mktemp -d "/tmp/telemetry-${TIMESTAMP}.XXXXXX")
trap 'rm -rf "$WORKDIR"' EXIT

step "Collecting telemetry for window: $START → $END"
step "Working directory: $WORKDIR"

# -------------------------------------------------------------------
# 1. Export systemd journal as JSON
# -------------------------------------------------------------------
step "Exporting systemd journal (JSON)..."
JOURNAL_FILE="$WORKDIR/journal.json"
journalctl --unit="$UNIT_NAME" --output=json \
    --since="$START" --until="$END" \
    > "$JOURNAL_FILE" 2>/dev/null || true
# --since/--until use local time by default, matching our AEDT input.
# Empty window → empty file (AC1.5).

# -------------------------------------------------------------------
# Compute ISO 8601 UTC bounds with 5-minute buffer for filtering.
# Used by JSONL (jq) and HAProxy (awk) server-side filters.
# -------------------------------------------------------------------
FILTER_START_UTC=$(date --utc -d "$START - 5 minutes" +"%Y-%m-%dT%H:%M:%SZ")
FILTER_END_UTC=$(date --utc -d "$END + 5 minutes" +"%Y-%m-%dT%H:%M:%SZ")
# Also compute local ISO 8601 bounds for HAProxy (rsyslog uses local time).
FILTER_START_LOCAL=$(date -d "$START - 5 minutes" +"%Y-%m-%dT%H:%M:%S%:z")
FILTER_END_LOCAL=$(date -d "$END + 5 minutes" +"%Y-%m-%dT%H:%M:%S%:z")

step "Filter window (UTC): $FILTER_START_UTC → $FILTER_END_UTC"

# -------------------------------------------------------------------
# 2. Filter application JSONL log by timestamp window
# -------------------------------------------------------------------
step "Filtering structlog JSONL..."
JSONL_FILE="$WORKDIR/structlog.jsonl"
if [[ -f "$JSONL_LOG" ]]; then
    if command -v jq &>/dev/null; then
        # ISO 8601 timestamps sort lexicographically — jq string comparison works.
        jq -c "select(.timestamp >= \"$FILTER_START_UTC\" and .timestamp <= \"$FILTER_END_UTC\")" \
            "$JSONL_LOG" > "$JSONL_FILE" 2>/dev/null || true
    else
        # Fallback: copy in full if jq unavailable.
        echo "WARNING: jq not found, copying full JSONL file" >&2
        cp "$JSONL_LOG" "$JSONL_FILE"
    fi
else
    echo "WARNING: JSONL log not found at $JSONL_LOG" >&2
    touch "$JSONL_FILE"
fi

# -------------------------------------------------------------------
# 3. Filter HAProxy log by rsyslog timestamp prefix
# -------------------------------------------------------------------
step "Filtering HAProxy log..."
HAPROXY_FILE="$WORKDIR/haproxy.log"
if [[ -f "$HAPROXY_LOG" ]]; then
    # rsyslog ISO 8601 prefix (e.g. "2026-03-16T16:06:30+11:00") is the first
    # space-delimited field. ISO 8601 with fixed-offset sorts lexicographically.
    awk -v start="$FILTER_START_LOCAL" -v end="$FILTER_END_LOCAL" \
        '{ ts = substr($1, 1, 25); if (ts >= start && ts <= end) print }' \
        "$HAPROXY_LOG" > "$HAPROXY_FILE" 2>/dev/null || true
else
    echo "WARNING: HAProxy log not found at $HAPROXY_LOG" >&2
    touch "$HAPROXY_FILE"
fi

# -------------------------------------------------------------------
# 4. Copy PostgreSQL log (most recent)
# -------------------------------------------------------------------
step "Copying PostgreSQL log..."
PG_FILE="$WORKDIR/postgresql.log"
# Find the most recent .log file in the PG log directory.
PG_LATEST=$(find "$PG_LOG_DIR" -name "*.log" -type f -printf '%T@ %p\n' 2>/dev/null \
    | sort -rn | head -1 | cut -d' ' -f2-)
if [[ -n "$PG_LATEST" ]]; then
    cp "$PG_LATEST" "$PG_FILE"
else
    echo "WARNING: No PostgreSQL log found in $PG_LOG_DIR" >&2
    touch "$PG_FILE"
fi

# -------------------------------------------------------------------
# 5. Build manifest.json
# -------------------------------------------------------------------
step "Building manifest.json..."

SERVER_HOSTNAME=$(hostname -f)
SERVER_TZ=$(timedatectl show --property=Timezone --value)
COLLECTION_TS=$(date --utc +"%Y-%m-%dT%H:%M:%SZ")

# Convert local start/end to UTC for manifest.
# GNU date can parse "YYYY-MM-DD HH:MM" in local time and emit UTC.
START_UTC=$(date --utc -d "$START" +"%Y-%m-%dT%H:%M:%SZ")
END_UTC=$(date --utc -d "$END" +"%Y-%m-%dT%H:%M:%SZ")

# Build per-file metadata.
file_entry() {
    local filepath="$1"
    local basename
    basename=$(basename "$filepath")
    local sha256
    sha256=$(sha256sum "$filepath" | cut -d' ' -f1)
    local size
    size=$(stat --format="%s" "$filepath")
    local mtime
    mtime=$(stat --format="%Y" "$filepath")
    printf '{"filename":"%s","sha256":"%s","size":%s,"mtime":%s}' \
        "$basename" "$sha256" "$size" "$mtime"
}

# Collect file entries into a JSON array.
FILES_JSON="["
first=true
for f in "$JOURNAL_FILE" "$JSONL_FILE" "$HAPROXY_FILE" "$PG_FILE"; do
    if [[ "$first" == true ]]; then
        first=false
    else
        FILES_JSON+=","
    fi
    FILES_JSON+=$(file_entry "$f")
done
FILES_JSON+="]"

# Assemble manifest.
cat > "$WORKDIR/manifest.json" <<MANIFEST_EOF
{
    "hostname": "$SERVER_HOSTNAME",
    "timezone": "$SERVER_TZ",
    "collection_timestamp": "$COLLECTION_TS",
    "requested_window": {
        "start_local": "$START",
        "end_local": "$END",
        "start_utc": "$START_UTC",
        "end_utc": "$END_UTC"
    },
    "files": $FILES_JSON
}
MANIFEST_EOF

# Pretty-print with jq if available (non-fatal if missing).
if command -v jq &>/dev/null; then
    jq . "$WORKDIR/manifest.json" > "$WORKDIR/manifest.json.tmp" \
        && mv "$WORKDIR/manifest.json.tmp" "$WORKDIR/manifest.json"
fi

# -------------------------------------------------------------------
# 6. Create tarball
# -------------------------------------------------------------------
TARBALL="/tmp/telemetry-${TIMESTAMP}.tar.gz"
step "Creating tarball: $TARBALL"

tar -czf "$TARBALL" -C "$WORKDIR" .

# Cancel the cleanup trap — we want the tarball to survive.
trap - EXIT
rm -rf "$WORKDIR"

step "Done. Tarball: $TARBALL"
echo ""
echo "To copy to your local machine:"
echo "  scp grimoire.drbbs.org:$TARBALL ."
```

**Key conventions from restart.sh:**
- `set -euo pipefail` at top
- `step()` helper for progress output
- Root guard with clear error message
- `trap` for cleanup
- Variables for configurable paths at top
- Graceful degradation (missing files → warning + empty file, not hard fail)

**Server-side filtering strategy:**
- **Journal:** `journalctl --since/--until` (native, exact)
- **JSONL:** `jq` with ISO 8601 string comparison (lexicographic, correct for UTC timestamps). Falls back to full copy if jq unavailable.
- **HAProxy:** `awk` on rsyslog ISO 8601 prefix field (lexicographic, uses local time bounds). Falls back to empty file if awk fails.
- **PG log:** Copied in full — multi-line entry grouping (ERROR + DETAIL + STATEMENT) is too fragile for bash filtering. PG logs are typically the smallest source.
- **Buffer:** 5 minutes on each side of the requested window, matching the parser-side buffer (defence in depth).

**Verification:**

1. Make executable:
```bash
chmod +x deploy/collect-telemetry.sh
```

2. Verify syntax:
```bash
bash -n deploy/collect-telemetry.sh
```
Expected: No output (clean parse)

3. Verify missing args produce usage:
```bash
bash deploy/collect-telemetry.sh 2>&1; echo "Exit: $?"
```
Expected: Usage message, exit code 1

**Commit:**
```bash
git add deploy/collect-telemetry.sh
git commit -m "feat: add telemetry collection script for incident analysis"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Manual verification on production server

**Verifies:** incident-analysis-tools.AC1.1, incident-analysis-tools.AC1.2, incident-analysis-tools.AC1.3, incident-analysis-tools.AC1.4, incident-analysis-tools.AC1.5

This task is a **human UAT step** — it cannot be automated locally because the script requires the production server's journal, log files, and root access.

**Steps:**

1. Copy script to production:
```bash
scp deploy/collect-telemetry.sh grimoire.drbbs.org:/tmp/
```

2. Run on production with known time window:
```bash
sudo bash /tmp/collect-telemetry.sh --start "2026-03-16 14:50" --end "2026-03-16 17:20"
```

3. Copy tarball back:
```bash
scp grimoire.drbbs.org:/tmp/telemetry-*.tar.gz .
```

4. Extract and verify:
```bash
mkdir /tmp/verify && tar -xzf telemetry-*.tar.gz -C /tmp/verify
```

5. **AC1.1:** Check all expected files present:
```bash
ls /tmp/verify/
# Expected: journal.json  structlog.jsonl  haproxy.log  postgresql.log  manifest.json
```

6. **AC1.2:** Check manifest contents:
```bash
cat /tmp/verify/manifest.json | python3 -m json.tool
# Verify: hostname, timezone, collection_timestamp, requested_window (local + UTC), files array with sha256/size/mtime
```

7. **AC1.3:** Verify hashes:
```bash
cd /tmp/verify
for f in journal.json structlog.jsonl haproxy.log postgresql.log; do
    manifest_hash=$(python3 -c "import json; m=json.load(open('manifest.json')); print([e['sha256'] for e in m['files'] if e['filename']=='$f'][0])")
    actual_hash=$(sha256sum "$f" | cut -d' ' -f1)
    if [[ "$manifest_hash" == "$actual_hash" ]]; then
        echo "✓ $f hash matches"
    else
        echo "✗ $f MISMATCH: manifest=$manifest_hash actual=$actual_hash"
    fi
done
```

8. **AC1.4:** Verify missing args:
```bash
sudo bash /tmp/collect-telemetry.sh 2>&1; echo "Exit: $?"
# Expected: Usage message, exit 1
sudo bash /tmp/collect-telemetry.sh --start "2026-03-16 14:50" 2>&1; echo "Exit: $?"
# Expected: Usage message, exit 1
```

9. **AC1.5:** Verify empty journal window:
```bash
sudo bash /tmp/collect-telemetry.sh --start "2020-01-01 00:00" --end "2020-01-01 00:01"
# Extract and check journal.json exists but is empty (0 bytes)
```
<!-- END_TASK_2 -->
