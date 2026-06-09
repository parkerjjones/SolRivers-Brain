@echo off
REM setup.bat - Automated setup for SolRiver monitoring system (Windows)

setlocal enabledelayedexpansion

echo.
echo ================================
echo SolRiver Setup Script (Windows)
echo ================================
echo.

REM Step 1: Check Python
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found
    echo Install Python 3.8+ from https://www.python.org
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PY_VERSION=%%i
echo [OK] Python %PY_VERSION%

REM Step 2: Install dependencies
echo.
echo [2/5] Installing Python packages...
python -m pip install --quiet psycopg2-binary requests openpyxl pandas scikit-learn
if errorlevel 1 (
    echo Error: Failed to install dependencies
    exit /b 1
)
echo [OK] Dependencies installed

REM Step 3: Verify imports
echo.
echo [3/5] Verifying imports...
python -c "import psycopg2, requests, openpyxl, pandas, sklearn; print('OK')" >nul 2>&1
if errorlevel 1 (
    echo Error: Import verification failed
    exit /b 1
)
echo [OK] All imports OK

REM Step 4: Check auth file
echo.
echo [4/5] Checking authentication...
if not exist "alsoenergy_curl.txt" (
    echo Warning: alsoenergy_curl.txt not found
    echo.
    echo To set up authentication:
    echo   1. Open browser and go to https://apps.alsoenergy.com
    echo   2. Log in and open PowerTrack dashboard
    echo   3. Press F12 to open Developer Tools
    echo   4. Go to Network tab
    echo   5. Look for a request to 'alerthistory' or '/api/view/'
    echo   6. Right-click and select "Copy as cURL (bash)"
    echo   7. Create a file named "alsoenergy_curl.txt"
    echo   8. Paste the cURL command into it (remove "curl" prefix if present)
    echo.
    echo See CLAUDE.md for detailed setup instructions
    echo.
    set /p continue="Continue without auth? (y/n) "
    if /i not "!continue!"=="y" (
        exit /b 1
    )
) else (
    echo [OK] Auth file found
)

REM Step 5: Check PostgreSQL (optional)
echo.
echo [5/5] Checking PostgreSQL ^(optional^)...
psql --version >nul 2>&1
if errorlevel 1 (
    echo Warning: PostgreSQL client not installed
    echo Will use API-only scripts ^(no database needed^)
) else (
    psql -h localhost -U postgres -d solriver -c "SELECT 1;" >nul 2>&1
    if errorlevel 1 (
        echo Warning: PostgreSQL not accessible
        echo Run: createdb -h localhost -U postgres solriver
    ) else (
        echo [OK] PostgreSQL connected
    )
)

echo.
echo ================================
echo Setup Complete!
echo ================================
echo.
echo Next steps:
echo.
echo 1. Quick test ^(no auth/DB needed^):
echo    python ae_sites_loader.py --output ae_sites.xlsx
echo.
echo 2. Full pipeline ^(requires auth + DB^):
echo    python ae_alert_loader.py --from 2025-01-01 --to 2026-06-08
echo    python ae_ml_analysis.py
echo.
echo 3. View documentation:
echo    type CLAUDE.md
echo.
pause
