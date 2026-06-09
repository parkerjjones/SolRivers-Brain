#!/bin/bash

# setup.sh — Automated setup for SolRiver monitoring system
# Installs dependencies, checks environment, and validates configuration

set -e

echo "================================"
echo "SolRiver Setup Script"
echo "================================"
echo ""

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Python & pip
echo "[1/5] Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python3 not found${NC}"
    echo "Install Python 3.8+ and try again"
    exit 1
fi
PY_VERSION=$(python3 --version | cut -d' ' -f2)
echo -e "${GREEN}✓ Python ${PY_VERSION}${NC}"

# Step 2: Install dependencies
echo ""
echo "[2/5] Installing Python packages..."
python3 -m pip install --quiet psycopg2-binary requests openpyxl pandas scikit-learn --break-system-packages 2>/dev/null || \
python3 -m pip install --quiet psycopg2-binary requests openpyxl pandas scikit-learn 2>/dev/null || {
    echo -e "${YELLOW}⚠ Could not use --break-system-packages; trying without...${NC}"
    python3 -m pip install psycopg2-binary requests openpyxl pandas scikit-learn
}
echo -e "${GREEN}✓ Dependencies installed${NC}"

# Step 3: Verify imports
echo ""
echo "[3/5] Verifying imports..."
python3 -c "import psycopg2, requests, openpyxl, pandas, sklearn; print('OK')" > /dev/null 2>&1 || {
    echo -e "${RED}✗ Import verification failed${NC}"
    exit 1
}
echo -e "${GREEN}✓ All imports OK${NC}"

# Step 4: Check auth file
echo ""
echo "[4/5] Checking authentication..."
if [ ! -f "alsoenergy_curl.txt" ]; then
    echo -e "${YELLOW}⚠ alsoenergy_curl.txt not found${NC}"
    echo ""
    echo "To set up authentication:"
    echo "  1. Open browser → https://apps.alsoenergy.com"
    echo "  2. Log in and go to PowerTrack dashboard"
    echo "  3. Open Network tab (F12 → Network)"
    echo "  4. Look for 'alerthistory' request"
    echo "  5. Right-click → Copy as cURL (bash)"
    echo "  6. Save to: alsoenergy_curl.txt"
    echo ""
    echo "See CLAUDE.md for detailed setup instructions"
    echo ""
    read -p "Continue without auth? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}✓ Auth file found${NC}"
fi

# Step 5: Check PostgreSQL (optional)
echo ""
echo "[5/5] Checking PostgreSQL (optional)..."
if command -v psql &> /dev/null; then
    if psql -h localhost -U postgres -d solriver -c "SELECT 1;" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PostgreSQL connected${NC}"
    else
        echo -e "${YELLOW}⚠ PostgreSQL not accessible (will use API-only mode)${NC}"
        echo "  To set up database: createdb -h localhost -U postgres solriver"
    fi
else
    echo -e "${YELLOW}⚠ PostgreSQL client not installed${NC}"
    echo "  Will use API-only scripts (no database needed)"
fi

echo ""
echo "================================"
echo "Setup Complete!"
echo "================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Quick test (no auth/DB needed):"
echo "   python3 ae_sites_loader.py --output ae_sites.xlsx"
echo ""
echo "2. Full pipeline (requires auth + DB):"
echo "   python3 ae_alert_loader.py --from 2025-01-01 --to 2026-06-08"
echo "   python3 ae_ml_analysis.py"
echo ""
echo "3. View documentation:"
echo "   cat CLAUDE.md"
echo ""
