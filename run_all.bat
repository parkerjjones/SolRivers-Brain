@echo off
REM ============================================================
REM  SolRiver / AlsoEnergy pipeline - double-click to run.
REM  Runs the full data pull on THIS machine (live network +
REM  your browser session), then leaves fresh .xlsx in this folder.
REM ============================================================
cd /d "%~dp0"

REM Find a usable Python (py launcher preferred, then python).
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PY=py"
) else (
    where python >nul 2>&1
    if %ERRORLEVEL%==0 (
        set "PY=python"
    ) else (
        echo.
        echo Python was not found on this machine.
        echo Install it from https://www.python.org/downloads/ ^(check "Add to PATH"^),
        echo then double-click this file again.
        echo.
        pause
        exit /b 1
    )
)

echo Using interpreter: %PY%
%PY% run_all.py %*

echo.
echo Done. This window will stay open so you can read the summary above.
pause
