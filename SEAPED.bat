@echo off
rem ============================================================
rem  SEAPED - Professional Load Testing Suite
rem  Developer: @uf0rs   Telegram: @HSIIHprime
rem ============================================================
setlocal
cd /d "%~dp0"

if exist "dist\SEAPED.exe" (
    start "" "dist\SEAPED.exe"
) else (
    echo [SEAPED] dist\SEAPED.exe not found.
    echo         Build it first:  python build_exe.py
    echo         Or run from sources:  python run.py
    pause
)
endlocal
