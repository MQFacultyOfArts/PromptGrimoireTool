#!/bin/bash
# Setup script for Claude Code async development environment
# Run this when starting a new container

set -e

PROJECT_DIR="/home/user/PromptGrimoireTool"
cd "$PROJECT_DIR"

echo "=== Claude Code Async Dev Setup ==="

# -----------------------------------------------------------------------------
# 1. Fix SSL key permissions for PostgreSQL
# -----------------------------------------------------------------------------
echo "[1/6] Fixing SSL permissions..."
chmod 600 /etc/ssl/private/ssl-cert-snakeoil.key 2>/dev/null || true

# -----------------------------------------------------------------------------
# 2. Configure PostgreSQL for trust auth (local dev only)
# -----------------------------------------------------------------------------
echo "[2/6] Configuring PostgreSQL auth..."
sed -i 's/peer$/trust/' /etc/postgresql/16/main/pg_hba.conf 2>/dev/null || true

# -----------------------------------------------------------------------------
# 3. Start PostgreSQL
# -----------------------------------------------------------------------------
echo "[3/6] Starting PostgreSQL..."
pg_ctlcluster 16 main start 2>/dev/null || echo "PostgreSQL may already be running"

# Wait for PostgreSQL to be ready
for i in {1..10}; do
    if pg_isready -q; then
        break
    fi
    sleep 1
done

# -----------------------------------------------------------------------------
# 4. Create database user and databases
# -----------------------------------------------------------------------------
echo "[4/6] Creating databases..."
psql -U postgres -c "CREATE ROLE claude WITH LOGIN SUPERUSER;" 2>/dev/null || true
psql -U postgres -c "CREATE DATABASE promptgrimoire OWNER claude;" 2>/dev/null || true
psql -U postgres -c "CREATE DATABASE promptgrimoire_test OWNER claude;" 2>/dev/null || true

# -----------------------------------------------------------------------------
# 5. Create .env file from template
# -----------------------------------------------------------------------------
echo "[5/6] Setting up .env..."
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/scripts/env.claude-code-async" "$PROJECT_DIR/.env"
    echo "  Created .env from scripts/env.claude-code-async"
else
    echo "  .env already exists, skipping"
fi

# -----------------------------------------------------------------------------
# 6. Pin Python 3.13 (without committing)
# -----------------------------------------------------------------------------
echo "[6/6] Pinning Python 3.13 locally..."
git update-index --assume-unchanged pyproject.toml .python-version uv.lock 2>/dev/null || true
sed -i 's/requires-python = ">=3.14"/requires-python = ">=3.13"/' pyproject.toml
echo "3.13" > .python-version

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------
echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  uv sync              # Install dependencies"
echo "  uv run pytest        # Run tests"
echo ""
