@echo off
REM ============================================================
REM   Synapse -- by The WhatIf Company
REM   Double-click this file (or run from cmd) to launch.
REM   No PowerShell required. No prerequisites beyond:
REM     - Python 3.11+ on PATH with synapse_daemon installed editable
REM     - Node.js 20+ on PATH (npm + npx)
REM   Use install-shortcut.cmd to put a clickable shortcut on your Desktop.
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

title Synapse -- The WhatIf Company

set DATA_DIR=%CD%\data
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

set DAEMON_LOG=%DATA_DIR%\daemon-runtime.log
set VITE_LOG=%DATA_DIR%\vite-runtime.log

echo.
echo ============================================================
echo   Synapse -- launching daemon + Vite + Electron
echo ============================================================
echo.
echo Daemon log: %DAEMON_LOG%
echo Vite log:   %VITE_LOG%
echo.

REM --- 1) Start the Python daemon as a detached, windowless process.
echo [1/4] Starting daemon on http://127.0.0.1:7878 ...
start "Synapse daemon" /B cmd /c "python -m synapse_daemon --port 7878 --data-dir data > "%DAEMON_LOG%" 2>&1"

REM --- 2) Wait for /api/v1/health.
set tries=0
:wait_daemon
timeout /t 1 /nobreak >nul
curl --silent --max-time 1 http://127.0.0.1:7878/api/v1/health >nul 2>nul
if not errorlevel 1 goto daemon_ready
set /a tries+=1
if !tries! GEQ 30 (
  echo [ERROR] Daemon did not respond within 30s.
  echo         Tail of "%DAEMON_LOG%":
  echo --------------------------------------------------------------
  more +0 "%DAEMON_LOG%" 2>nul
  echo --------------------------------------------------------------
  pause
  goto end
)
goto wait_daemon

:daemon_ready
echo       Daemon ready.

REM --- 3) Build Electron main + start Vite.
echo [2/4] Compiling Electron main ...
call npm run build:electron >nul
if errorlevel 1 (
  echo [ERROR] "npm run build:electron" failed. Run it manually to see the output.
  pause
  goto cleanup
)

echo [3/4] Starting Vite dev server on http://127.0.0.1:5173 ...
start "Synapse Vite" /B cmd /c "npx vite > "%VITE_LOG%" 2>&1"

set tries=0
:wait_vite
timeout /t 1 /nobreak >nul
curl --silent --max-time 1 http://127.0.0.1:5173 >nul 2>nul
if not errorlevel 1 goto vite_ready
set /a tries+=1
if !tries! GEQ 30 (
  echo [ERROR] Vite did not respond within 30s.
  echo         Tail of "%VITE_LOG%":
  echo --------------------------------------------------------------
  more +0 "%VITE_LOG%" 2>nul
  echo --------------------------------------------------------------
  pause
  goto cleanup
)
goto wait_vite

:vite_ready
echo       Vite ready.

REM --- 4) Launch Electron in the foreground. Closes when window quits / tray Quit.
echo [4/4] Opening Synapse window ...
echo.
call npx electron .

:cleanup
echo.
echo Shutting down background services ...
REM Kill anything still bound to our ports.
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :7878 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5173 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>nul
echo Done.

:end
endlocal
