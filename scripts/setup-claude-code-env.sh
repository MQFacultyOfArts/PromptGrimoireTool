#!/bin/bash
# Setup script for Claude Code async development environment
# Run this when starting a new container
#
# Prerequisites:
#   - Python 3.14 .deb files in scripts/deb/ (from deadsnakes PPA)
#   - PostgreSQL 16 installed
#   - LibreOffice available in apt repos

set -e

PROJECT_DIR="/home/user/PromptGrimoireTool"
cd "$PROJECT_DIR"

echo "=== Claude Code Async Dev Setup ==="

# -----------------------------------------------------------------------------
# 1. Install LibreOffice for RTF parsing tests
# -----------------------------------------------------------------------------
echo "[1/7] Installing LibreOffice (for RTF tests)..."
if ! command -v libreoffice &> /dev/null; then
    apt-get update -qq
    apt-get install -y libreoffice-writer-nogui > /dev/null 2>&1 || echo "  Warning: Could not install libreoffice"
else
    echo "  LibreOffice already installed"
fi

# -----------------------------------------------------------------------------
# 2. Install Python 3.14 from local .deb files
# -----------------------------------------------------------------------------
echo "[2/7] Installing Python 3.14..."
DEB_DIR="$PROJECT_DIR/scripts/deb"

if [ ! -d "$DEB_DIR" ] || ! ls "$DEB_DIR"/*.deb &> /dev/null; then
    echo "  ERROR: Python 3.14 .deb files not found in $DEB_DIR"
    echo "  See scripts/deb/README.md for download instructions"
    exit 1
fi

if command -v python3.14 &> /dev/null; then
    echo "  Python 3.14 already installed"
else
    dpkg -i "$DEB_DIR"/*.deb 2>/dev/null || apt-get install -f -y > /dev/null 2>&1
    if ! command -v python3.14 &> /dev/null; then
        echo "  ERROR: Python 3.14 installation failed"
        exit 1
    fi
    echo "  Python 3.14 installed successfully"
fi

# -----------------------------------------------------------------------------
# 3. Fix SSL key permissions for PostgreSQL
# -----------------------------------------------------------------------------
echo "[3/7] Fixing SSL permissions..."
chmod 600 /etc/ssl/private/ssl-cert-snakeoil.key 2>/dev/null || true

# -----------------------------------------------------------------------------
# 4. Configure PostgreSQL for trust auth (local dev only)
# -----------------------------------------------------------------------------
echo "[4/7] Configuring PostgreSQL auth..."
sed -i 's/peer$/trust/' /etc/postgresql/16/main/pg_hba.conf 2>/dev/null || true

# -----------------------------------------------------------------------------
# 5. Start PostgreSQL
# -----------------------------------------------------------------------------
echo "[5/7] Starting PostgreSQL..."
pg_ctlcluster 16 main start 2>/dev/null || echo "  PostgreSQL may already be running"

# Wait for PostgreSQL to be ready
for i in {1..10}; do
    if pg_isready -q; then
        break
    fi
    sleep 1
done

# -----------------------------------------------------------------------------
# 6. Create database user and databases
# -----------------------------------------------------------------------------
echo "[6/7] Creating databases..."
psql -U postgres -c "CREATE ROLE claude WITH LOGIN SUPERUSER;" 2>/dev/null || true
psql -U postgres -c "CREATE DATABASE promptgrimoire OWNER claude;" 2>/dev/null || true
psql -U postgres -c "CREATE DATABASE promptgrimoire_test OWNER claude;" 2>/dev/null || true

# -----------------------------------------------------------------------------
# 7. Create .env file from template
# -----------------------------------------------------------------------------
echo "[7/7] Setting up .env..."
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/scripts/env.claude-code-async" "$PROJECT_DIR/.env"
    echo "  Created .env from scripts/env.claude-code-async"
else
    echo "  .env already exists, skipping"
fi

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------
echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  uv sync                                # Install dependencies"
echo "  uv run pytest -m 'not e2e'             # Run unit + integration tests"
echo "  uv run pytest -m 'not e2e and not slow'  # Fast tests only (~4s)"
echo ""
echo "Note: E2E tests require Playwright browsers (cdn.playwright.dev)"
echo "      Run E2E tests locally before merging PRs."
echo ""
