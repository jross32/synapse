@echo off
REM ============================================================
REM   Synapse -- desktop shortcut installer
REM
REM   Creates "%USERPROFILE%\Desktop\Synapse.lnk" pointing at the
REM   synapse.cmd next to this file. Uses cscript + a temp VBS so
REM   we don't depend on PowerShell.
REM
REM   Run once: double-click this file, or `cmd /c install-shortcut.cmd`.
REM ============================================================

setlocal
set REPO=%~dp0
if "%REPO:~-1%"=="\" set REPO=%REPO:~0,-1%

set TARGET=%REPO%\synapse.cmd
set ICON=%REPO%\electron\icons\synapse.ico
set SHORTCUT=%USERPROFILE%\Desktop\Synapse.lnk

if not exist "%TARGET%" (
  echo Cannot find synapse.cmd next to this installer.
  echo Expected: %TARGET%
  pause
  exit /b 1
)

REM Fall back to the PNG if the ICO has not been generated yet.
if not exist "%ICON%" (
  set ICON=%REPO%\electron\icons\synapse-256.png
)

set VBS=%TEMP%\synapse-shortcut.vbs
> "%VBS%" echo Set oWS = WScript.CreateObject("WScript.Shell")
>> "%VBS%" echo Set oLink = oWS.CreateShortcut("%SHORTCUT%")
>> "%VBS%" echo oLink.TargetPath = "%TARGET%"
>> "%VBS%" echo oLink.WorkingDirectory = "%REPO%"
>> "%VBS%" echo oLink.IconLocation = "%ICON%"
>> "%VBS%" echo oLink.Description = "Synapse - by The WhatIf Company"
>> "%VBS%" echo oLink.WindowStyle = 7
>> "%VBS%" echo oLink.Save

cscript //nologo "%VBS%"
set vbsExit=%ERRORLEVEL%
del "%VBS%" >nul 2>nul

if exist "%SHORTCUT%" (
  echo.
  echo Created desktop shortcut: %SHORTCUT%
  echo Target:     %TARGET%
  echo Working in: %REPO%
  echo Icon:       %ICON%
) else (
  echo.
  echo [ERROR] Shortcut was not created. cscript exit code: %vbsExit%
)

echo.
pause
endlocal
