@echo off
REM ============================================================
REM   Synapse -- by The WhatIf Company
REM   Double-click this file (or run from cmd) to launch.
REM   The wrapper delegates to scripts\dev.ps1 so Synapse can own
REM   its daemon, Vite, and Electron child processes safely.
REM ============================================================

setlocal
cd /d "%~dp0"

title Synapse -- The WhatIf Company

echo.
echo ============================================================
echo   Synapse -- launching daemon + Vite + Electron
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev.ps1" -ShortcutMode %*
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Synapse exited with code %EXIT_CODE%.
)

endlocal & exit /b %EXIT_CODE%
