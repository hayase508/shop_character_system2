@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo The first-time setup has not been completed.
  echo Run setup_shop.bat first.
  pause
  exit /b 1
)

set "ICHIGO_SKIP_BROWSER=1"
call start_shop.bat
set "ICHIGO_START_RESULT=%ERRORLEVEL%"
set "ICHIGO_SKIP_BROWSER="
if not "%ICHIGO_START_RESULT%"=="0" exit /b %ICHIGO_START_RESULT%

powershell.exe -NoProfile -Command "Start-Sleep -Seconds 2"

set "ICHIGO_BROWSER_EXE="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "ICHIGO_BROWSER_EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined ICHIGO_BROWSER_EXE if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "ICHIGO_BROWSER_EXE=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined ICHIGO_BROWSER_EXE if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "ICHIGO_BROWSER_EXE=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not defined ICHIGO_BROWSER_EXE if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "ICHIGO_BROWSER_EXE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not defined ICHIGO_BROWSER_EXE if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "ICHIGO_BROWSER_EXE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"

if defined ICHIGO_BROWSER_EXE (
  start "" "!ICHIGO_BROWSER_EXE!" --new-window "http://127.0.0.1:8000/" "http://127.0.0.1:8000/touch" "http://127.0.0.1:8000/debug"
) else (
  start "" "http://127.0.0.1:8000/"
  start "" "http://127.0.0.1:8000/touch"
  start "" "http://127.0.0.1:8000/debug"
)
exit /b 0
