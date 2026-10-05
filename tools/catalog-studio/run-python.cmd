@echo off
setlocal
set "ROOT=%~dp0..\.."
if exist "%ROOT%\.venv\Scripts\python.exe" (
  "%ROOT%\.venv\Scripts\python.exe" %*
  exit /b %errorlevel%
)
python %*
exit /b %errorlevel%
