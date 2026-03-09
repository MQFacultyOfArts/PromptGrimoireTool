#!/usr/bin/env bash
# Extract a workspace and its documents from the production database.
#
# Usage:
#   ./scripts/extract_workspace.sh <workspace-uuid>
#
# Outputs to /tmp/:
#   workspace_<uuid>.json       — workspace metadata as JSON
#   workspace_<uuid>_crdt.bin   — CRDT state (binary, with pg header)
#   workspace_<uuid>_docs.json  — workspace_document rows as JSON lines
#
# Designed for the production server (peer auth, promptgrimoire role).
# For local use, override: PGUSER=youruser PGDATABASE=yourdb ./scripts/extract_workspace.sh <uuid>

set -euo pipefail

if [ $# -ne 1 ]; then
    echo "Usage: $0 <workspace-uuid>" >&2
    exit 1
fi

WORKSPACE_ID="$1"
PGUSER="${PGUSER:-promptgrimoire}"
PGDATABASE="${PGDATABASE:-promptgrimoire}"
PREFIX="/tmp/workspace_${WORKSPACE_ID}"

echo "Extracting workspace ${WORKSPACE_ID}..."

# 1. Workspace metadata (JSON)
sudo -u "${PGUSER}" psql -d "${PGDATABASE}" -c "\copy (SELECT row_to_json(w) FROM (SELECT * FROM workspace WHERE id = '${WORKSPACE_ID}') w) TO '${PREFIX}.json'"
echo "  -> ${PREFIX}.json"

# 2. CRDT state (binary)
sudo -u "${PGUSER}" psql -d "${PGDATABASE}" -c "\copy (SELECT crdt_state FROM workspace WHERE id = '${WORKSPACE_ID}') TO '${PREFIX}_crdt.bin' WITH (FORMAT binary)"
echo "  -> ${PREFIX}_crdt.bin"

# 3. Workspace documents (JSON lines — one per document)
sudo -u "${PGUSER}" psql -d "${PGDATABASE}" -c "\copy (SELECT row_to_json(d) FROM (SELECT * FROM workspace_document WHERE workspace_id = '${WORKSPACE_ID}' ORDER BY order_index) d) TO '${PREFIX}_docs.json'"
echo "  -> ${PREFIX}_docs.json"

echo "Done. scp from server:"
echo "  scp grimoire.drbbs.org:${PREFIX}.json ${PREFIX}_crdt.bin ${PREFIX}_docs.json /tmp/"
