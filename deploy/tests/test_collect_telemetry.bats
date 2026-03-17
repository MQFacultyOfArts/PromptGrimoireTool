#!/usr/bin/env bats
# Unit tests for deploy/collect-telemetry.sh
#
# These tests exercise the collector with stubbed host commands and
# temporary log files. They verify the actual incident-analysis contract:
# exact requested window in the manifest, buffered log capture, provenance,
# and ingest-compatible filenames.

SCRIPT="$BATS_TEST_DIRNAME/../collect-telemetry.sh"

setup() {
    TEST_ROOT=$(mktemp -d)
    BIN_DIR="$TEST_ROOT/bin"
    APP_DIR="$TEST_ROOT/app"
    JSONL_FILE="$APP_DIR/logs/sessions/promptgrimoire.jsonl"
    HAPROXY_FILE="$TEST_ROOT/haproxy.log"
    PG_DIR="$TEST_ROOT/pg"
    EXTRACT_DIR="$TEST_ROOT/extracted"

    mkdir -p "$BIN_DIR" "$(dirname "$JSONL_FILE")" "$PG_DIR" "$EXTRACT_DIR"

    cat >"$BIN_DIR/journalctl" <<'EOF'
#!/usr/bin/env bash
if [[ "${FAKE_JOURNAL_FAIL:-0}" == "1" ]]; then
    echo "journal exploded" >&2
    exit 1
fi
printf '%s\n' '{"__REALTIME_TIMESTAMP":"1773637200000000","MESSAGE":"journal event"}'
EOF

    cat >"$BIN_DIR/timedatectl" <<'EOF'
#!/usr/bin/env bash
echo "${FAKE_TIMEZONE:-Australia/Sydney}"
EOF

    cat >"$BIN_DIR/hostname" <<'EOF'
#!/usr/bin/env bash
echo "grimoire.test"
EOF

    chmod +x "$BIN_DIR/journalctl" "$BIN_DIR/timedatectl" "$BIN_DIR/hostname"
}

teardown() {
    if [[ -n "${TARBALL_PATH:-}" && -f "$TARBALL_PATH" ]]; then
        rm -f "$TARBALL_PATH"
    fi
    rm -rf "$TEST_ROOT"
}

run_collect() {
    run env \
        PATH="$BIN_DIR:$PATH" \
        TZ="Australia/Sydney" \
        COLLECT_TELEMETRY_ALLOW_NON_ROOT=1 \
        APP_DIR="$APP_DIR" \
        JSONL_LOG="$JSONL_FILE" \
        HAPROXY_LOG="$HAPROXY_FILE" \
        PG_LOG_DIR="$PG_DIR" \
        bash "$SCRIPT" --start "2026-03-16 14:50" --end "2026-03-16 17:20"
}

extract_tarball() {
    TARBALL_PATH=$(printf '%s\n' "$output" | grep -oE '/tmp/telemetry-[^ ]+\.tar\.gz' | tail -1)
    [[ -n "$TARBALL_PATH" ]]
    [[ -f "$TARBALL_PATH" ]]
    tar -xzf "$TARBALL_PATH" -C "$EXTRACT_DIR"
}

manifest_query() {
    jq -r "$1" "$EXTRACT_DIR/manifest.json"
}

@test "no arguments prints usage and exits non-zero" {
    run bash "$SCRIPT"
    [ "$status" -ne 0 ]
    [[ "$output" == *"Usage:"* ]]
}

@test "--start without --end prints usage" {
    run bash "$SCRIPT" --start "2026-03-16 14:50"
    [ "$status" -ne 0 ]
    [[ "$output" == *"Usage:"* ]]
}

@test "--end without --start prints usage" {
    run bash "$SCRIPT" --end "2026-03-16 17:20"
    [ "$status" -ne 0 ]
    [[ "$output" == *"Usage:"* ]]
}

@test "unknown flag prints usage" {
    run bash "$SCRIPT" --bogus
    [ "$status" -ne 0 ]
    [[ "$output" == *"Usage:"* ]]
}

@test "non-root user is rejected" {
    if [ "$EUID" -eq 0 ]; then
        skip "running as root"
    fi
    run bash "$SCRIPT" --start "2026-03-16 14:50" --end "2026-03-16 17:20"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Must run as root"* ]]
}

@test "manifest records exact requested UTC window while JSONL filtering keeps a five-minute buffer" {
    cat >"$JSONL_FILE" <<'EOF'
{"timestamp":"2026-03-16T03:44:00Z","event":"too_early"}
{"timestamp":"2026-03-16T03:46:00Z","event":"buffer_start"}
{"timestamp":"2026-03-16T04:00:00Z","event":"inside"}
{"timestamp":"2026-03-16T06:24:00Z","event":"buffer_end"}
{"timestamp":"2026-03-16T06:26:00Z","event":"too_late"}
EOF
    : >"$HAPROXY_FILE"
    : >"$PG_DIR/postgresql-16-main.log"

    run_collect
    [ "$status" -eq 0 ]
    extract_tarball

    [ "$(manifest_query '.requested_window.start_utc')" = "2026-03-16T03:50:00Z" ]
    [ "$(manifest_query '.requested_window.end_utc')" = "2026-03-16T06:20:00Z" ]
    [ "$(grep -c '"timestamp"' "$EXTRACT_DIR/structlog.jsonl")" -eq 3 ]
    grep -q 'buffer_start' "$EXTRACT_DIR/structlog.jsonl"
    grep -q 'inside' "$EXTRACT_DIR/structlog.jsonl"
    grep -q 'buffer_end' "$EXTRACT_DIR/structlog.jsonl"
    run grep -q 'too_early' "$EXTRACT_DIR/structlog.jsonl"
    [ "$status" -ne 0 ]
    run grep -q 'too_late' "$EXTRACT_DIR/structlog.jsonl"
    [ "$status" -ne 0 ]
}

@test "missing JSONL log records a warning and still creates an empty placeholder file" {
    : >"$HAPROXY_FILE"
    : >"$PG_DIR/postgresql-16-main.log"

    run_collect
    [ "$status" -eq 0 ]
    [[ "$output" == *"JSONL log not found"* ]]
    extract_tarball

    [ -f "$EXTRACT_DIR/structlog.jsonl" ]
    [ ! -s "$EXTRACT_DIR/structlog.jsonl" ]
    [ "$(manifest_query '.warnings | length')" -ge 1 ]
    [[ "$(manifest_query '.warnings[0]')" == *"JSONL log not found"* ]]
}

@test "HAProxy provenance records both current and rotated log sources" {
    : >"$JSONL_FILE"
    cat >"${HAPROXY_FILE}.1" <<'EOF'
2026-03-16T14:46:00+11:00 host haproxy[1]: rotated
EOF
    cat >"$HAPROXY_FILE" <<'EOF'
2026-03-16T17:24:00+11:00 host haproxy[1]: current
EOF
    : >"$PG_DIR/postgresql-16-main.log"

    run_collect
    [ "$status" -eq 0 ]
    extract_tarball

    [ "$(wc -l < "$EXTRACT_DIR/haproxy.log")" -eq 2 ]
    source_path=$(manifest_query '.files[] | select(.filename == "haproxy.log") | .source_path')
    [[ "$source_path" == *"${HAPROXY_FILE}.1"* ]]
    [[ "$source_path" == *"$HAPROXY_FILE"* ]]
}

@test "JSONL collection merges rotated files in oldest-first order" {
    # .2 is oldest, .1 is middle, current is newest
    cat >"${JSONL_FILE}.2" <<'EOF'
{"timestamp":"2026-03-16T03:46:00Z","event":"from_dot2"}
EOF
    cat >"${JSONL_FILE}.1" <<'EOF'
{"timestamp":"2026-03-16T04:00:00Z","event":"from_dot1"}
EOF
    cat >"$JSONL_FILE" <<'EOF'
{"timestamp":"2026-03-16T06:00:00Z","event":"from_current"}
EOF
    : >"$HAPROXY_FILE"
    : >"$PG_DIR/postgresql-16-main.log"

    run_collect
    [ "$status" -eq 0 ]
    extract_tarball

    # All three in-window events should be present
    [ "$(grep -c '"timestamp"' "$EXTRACT_DIR/structlog.jsonl")" -eq 3 ]
    # Oldest event should appear first (from .2)
    head -1 "$EXTRACT_DIR/structlog.jsonl" | grep -q 'from_dot2'
    # Newest event should appear last (from current)
    tail -1 "$EXTRACT_DIR/structlog.jsonl" | grep -q 'from_current'
    # Provenance should list all source files
    source_path=$(manifest_query '.files[] | select(.filename == "structlog.jsonl") | .source_path')
    [[ "$source_path" == *".jsonl.2"* ]]
    [[ "$source_path" == *".jsonl.1"* ]]
    [[ "$source_path" == *"promptgrimoire.jsonl"* ]]
}

@test "PostgreSQL logs are copied to canonical ingest-compatible filenames" {
    : >"$JSONL_FILE"
    : >"$HAPROXY_FILE"
    printf '%s\n' 'text log' >"$PG_DIR/postgresql-16-main.log"
    printf '%s\n' '{"timestamp":"2026-03-16 04:32:52.000 UTC","message":"json log"}' >"$PG_DIR/postgresql-16-main.json"

    run_collect
    [ "$status" -eq 0 ]
    extract_tarball

    [ -f "$EXTRACT_DIR/postgresql.log" ]
    [ -f "$EXTRACT_DIR/postgresql.json" ]
    [ ! -f "$EXTRACT_DIR/postgresql-16-main.log" ]
    [ ! -f "$EXTRACT_DIR/postgresql-16-main.json" ]
    [ "$(manifest_query '[.files[] | select(.filename == "postgresql.log")] | length')" -eq 1 ]
    [ "$(manifest_query '[.files[] | select(.filename == "postgresql.json")] | length')" -eq 1 ]
}
