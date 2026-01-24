#!/bin/bash
# Setup script for Claude Code async development environment
# Run this when starting a new container

set -e

PROJECT_DIR="/home/user/PromptGrimoireTool"
cd "$PROJECT_DIR"

echo "=== Claude Code Async Dev Setup ==="

# -----------------------------------------------------------------------------
# 1. Install LibreOffice for RTF parsing tests
# -----------------------------------------------------------------------------
echo "[1/7] Installing LibreOffice (for RTF tests)..."
if ! command -v libreoffice &> /dev/null; then
    apt-get install -y libreoffice-writer-nogui > /dev/null 2>&1 || echo "  Warning: Could not install libreoffice"
else
    echo "  LibreOffice already installed"
fi

# -----------------------------------------------------------------------------
# 2. Fix SSL key permissions for PostgreSQL
# -----------------------------------------------------------------------------
echo "[2/7] Fixing SSL permissions..."
chmod 600 /etc/ssl/private/ssl-cert-snakeoil.key 2>/dev/null || true

# -----------------------------------------------------------------------------
# 3. Configure PostgreSQL for trust auth (local dev only)
# -----------------------------------------------------------------------------
echo "[3/7] Configuring PostgreSQL auth..."
sed -i 's/peer$/trust/' /etc/postgresql/16/main/pg_hba.conf 2>/dev/null || true

# -----------------------------------------------------------------------------
# 4. Start PostgreSQL
# -----------------------------------------------------------------------------
echo "[4/7] Starting PostgreSQL..."
pg_ctlcluster 16 main start 2>/dev/null || echo "PostgreSQL may already be running"

# Wait for PostgreSQL to be ready
for i in {1..10}; do
    if pg_isready -q; then
        break
    fi
    sleep 1
done

# -----------------------------------------------------------------------------
# 5. Create database user and databases
# -----------------------------------------------------------------------------
echo "[5/7] Creating databases..."
psql -U postgres -c "CREATE ROLE claude WITH LOGIN SUPERUSER;" 2>/dev/null || true
psql -U postgres -c "CREATE DATABASE promptgrimoire OWNER claude;" 2>/dev/null || true
psql -U postgres -c "CREATE DATABASE promptgrimoire_test OWNER claude;" 2>/dev/null || true

# -----------------------------------------------------------------------------
# 6. Create .env file from template
# -----------------------------------------------------------------------------
echo "[6/7] Setting up .env..."
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/scripts/env.claude-code-async" "$PROJECT_DIR/.env"
    echo "  Created .env from scripts/env.claude-code-async"
else
    echo "  .env already exists, skipping"
fi

# -----------------------------------------------------------------------------
# 7. Install Python 3.14 from debs, or fall back to 3.13
# -----------------------------------------------------------------------------
echo "[7/7] Setting up Python..."
DEB_DIR="$PROJECT_DIR/scripts/deb"

if [ -f "$DEB_DIR/python3.14_"*".deb" ] 2>/dev/null; then
    echo "  Installing Python 3.14 from local debs..."
    dpkg -i "$DEB_DIR"/*.deb 2>/dev/null || apt-get install -f -y > /dev/null 2>&1
    if command -v python3.14 &> /dev/null; then
        echo "  Python 3.14 installed successfully"
    else
        echo "  Warning: Python 3.14 install failed, falling back to 3.13"
        git update-index --assume-unchanged pyproject.toml .python-version uv.lock 2>/dev/null || true
        sed -i 's/requires-python = ">=3.14"/requires-python = ">=3.13"/' pyproject.toml
        echo "3.13" > .python-version
    fi
elif command -v python3.14 &> /dev/null; then
    echo "  Python 3.14 already available"
else
    echo "  Python 3.14 not available, pinning to 3.13 locally..."
    git update-index --assume-unchanged pyproject.toml .python-version uv.lock 2>/dev/null || true
    sed -i 's/requires-python = ">=3.14"/requires-python = ">=3.13"/' pyproject.toml
    echo "3.13" > .python-version
fi

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
