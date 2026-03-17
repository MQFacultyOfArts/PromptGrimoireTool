#!/usr/bin/env bash
# batch_validate_exports.sh — Rehydrate + export all workspace JSONs overnight.
#
# Usage:
#   ./scripts/batch_validate_exports.sh [json_dir] [output_dir]
#
# Defaults:
#   json_dir:   /tmp (looks for workspace_*.json)
#   output_dir: /tmp/export_validation
#
# What it does:
#   1. Rehydrates every workspace_*.json into the local dev DB
#   2. Exports each workspace through the full PDF pipeline
#   3. Keeps only failures (--only-errors) with .tex + .log artifacts
#   4. Writes a summary report to output_dir/report.txt
#
# Workspaces without content or annotations are silently skipped.
# Output dir is cleared at start to prevent stale artifacts from prior runs.
#
# Run from the project root:
#   cd /path/to/PromptGrimoireTool && ./scripts/batch_validate_exports.sh

set -euo pipefail

JSON_DIR="${1:-/tmp}"
OUTPUT_DIR="${2:-/tmp/export_validation}"
REPORT="$OUTPUT_DIR/report.txt"
REHYDRATE_LOG="$OUTPUT_DIR/rehydrate.log"
DB_NAME="${PGDATABASE:-promptgrimoire}"

# Clear output dir to prevent stale artifacts from prior runs
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# ── Phase 1: Rehydrate ───────────────────────────────────────────────────

echo "=== Phase 1: Rehydrating workspaces ==="
echo "Source: $JSON_DIR/workspace_*.json"
echo "Database: $DB_NAME"
echo ""

# Enable nullglob so the glob expands to empty array when no matches
shopt -s nullglob
json_files=("$JSON_DIR"/workspace_*.json)
shopt -u nullglob

if [ ${#json_files[@]} -eq 0 ]; then
    echo "ERROR: No workspace_*.json files found in $JSON_DIR"
    exit 1
fi

echo "Found ${#json_files[@]} workspace JSON files"

rehydrated=0
rehydrate_failed=0
uuids=()

for json_file in "${json_files[@]}"; do
    basename=$(basename "$json_file" .json)
    uuid="${basename#workspace_}"

    if uv run scripts/rehydrate_workspace.py "$json_file" >> "$REHYDRATE_LOG" 2>&1; then
        rehydrated=$((rehydrated + 1))
        uuids+=("$uuid")
    else
        echo "  FAIL rehydrate: $uuid (see $REHYDRATE_LOG)"
        rehydrate_failed=$((rehydrate_failed + 1))
    fi
done

echo ""
echo "Rehydrated: $rehydrated  Failed: $rehydrate_failed"
echo ""

if [ ${#uuids[@]} -eq 0 ]; then
    echo "ERROR: No workspaces rehydrated successfully"
    exit 1
fi

# ── Phase 2: Export with --only-errors ────────────────────────────────────

echo "=== Phase 2: Exporting ${#uuids[@]} workspaces ==="
echo "Output: $OUTPUT_DIR"
echo "Mode: --only-errors (successes purged, skips ignored, failures kept)"
echo ""

uv run grimoire export run "${uuids[@]}" \
    --only-errors \
    -o "$OUTPUT_DIR" \
    2>&1 | tee "$OUTPUT_DIR/export.log"

# ── Phase 3: Summary report ──────────────────────────────────────────────

echo ""
echo "=== Phase 3: Writing report ==="

{
    echo "Export Validation Report"
    echo "======================="
    echo "Date: $(date -Iseconds)"
    echo "Source: $JSON_DIR"
    echo "Database: $DB_NAME"
    echo "Workspaces rehydrated: $rehydrated"
    echo "Rehydration failures: $rehydrate_failed"
    echo "Total UUIDs passed to export: ${#uuids[@]}"
    echo ""
    echo "--- Failure artifacts in $OUTPUT_DIR ---"

    failure_count=0

    shopt -s nullglob
    tex_files=("$OUTPUT_DIR"/*.tex)
    shopt -u nullglob

    for tex_file in "${tex_files[@]}"; do
        failure_count=$((failure_count + 1))
        stem=$(basename "$tex_file" .tex)
        uuid="${stem%%_*}"
        log_file="$OUTPUT_DIR/${stem}.log"

        echo ""
        echo "FAIL: $uuid"
        echo "  TeX: $tex_file"
        if [ -f "$log_file" ]; then
            echo "  Log: $log_file"
            grep '^!' "$log_file" 2>/dev/null | head -3 | while read -r line; do
                echo "  Error: $line"
            done
        fi
    done

    if [ "$failure_count" -eq 0 ]; then
        echo ""
        echo "ALL EXPORTS SUCCEEDED — no failure artifacts."
    else
        echo ""
        echo "Total compilation failures: $failure_count"
    fi
} | tee "$REPORT"

echo ""
echo "Report written to: $REPORT"
echo "Done."
