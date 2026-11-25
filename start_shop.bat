@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment was not found.
  echo Run: python -m venv .venv
  echo Then: .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

set "ICHIGO_VOICEVOX_ENABLED=true"
set "ICHIGO_QUESTION_ENABLED=true"
set "ICHIGO_QUESTION_INPUT_MODE=touch"
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if /I "%%A"=="VOICEVOX_ENABLED" set "ICHIGO_VOICEVOX_ENABLED=%%B"
    if /I "%%A"=="QUESTION_ENABLED" set "ICHIGO_QUESTION_ENABLED=%%B"
    if /I "%%A"=="QUESTION_INPUT_MODE" set "ICHIGO_QUESTION_INPUT_MODE=%%B"
  )
)
if /I "!ICHIGO_QUESTION_ENABLED!"=="false" goto :skip_voicevox
if /I "!ICHIGO_QUESTION_INPUT_MODE!"=="touch" goto :skip_voicevox
if /I "!ICHIGO_VOICEVOX_ENABLED!"=="false" goto :skip_voicevox

powershell.exe -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:50021/version | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  if not defined VOICEVOX_ENGINE_EXE set "VOICEVOX_ENGINE_EXE=%LOCALAPPDATA%\Programs\VOICEVOX\vv-engine\run.exe"
  if exist "!VOICEVOX_ENGINE_EXE!" (
    echo Starting VOICEVOX engine for Shikoku Metan...
    powershell.exe -NoProfile -Command "$exe=$env:VOICEVOX_ENGINE_EXE; Start-Process -FilePath $exe -ArgumentList @('--host','127.0.0.1','--port','50021','--output_log_utf8') -WorkingDirectory (Split-Path -Parent $exe) -WindowStyle Hidden"
    powershell.exe -NoProfile -Command "$deadline=(Get-Date).AddSeconds(30); do { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:50021/version | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 500 } } while ((Get-Date) -lt $deadline); exit 1"
    if errorlevel 1 echo Warning: VOICEVOX did not become ready. Dynamic answers will use browser speech.
  ) else (
    echo Warning: VOICEVOX engine was not found at:
    echo   !VOICEVOX_ENGINE_EXE!
    echo Install VOICEVOX or set VOICEVOX_ENGINE_EXE before running this file.
    echo The face reception and subtitles will continue to work.
  )
)

:skip_voicevox

set "ICHIGO_SERVER_READY="
for /f "tokens=1" %%A in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do set "ICHIGO_SERVER_READY=1"
if not defined ICHIGO_SERVER_READY (
  echo Starting Ichigo Cafe server...
  start "Ichigo Cafe Server" /D "%~dp0" cmd.exe /k ""%~dp0.venv\Scripts\python.exe" -u -m app"
)

for /L %%S in (1,1,60) do (
  set "ICHIGO_SERVER_READY="
  for /f "tokens=1" %%A in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do set "ICHIGO_SERVER_READY=1"
  if defined ICHIGO_SERVER_READY goto :server_ready
  powershell.exe -NoProfile -Command "Start-Sleep -Milliseconds 500"
)

echo The server did not start. Check the Ichigo Cafe Server window for details.
pause
exit /b 1

:server_ready

if not defined ICHIGO_SKIP_BROWSER start "" "http://127.0.0.1:8000/?v=20261125-1"
exit /b 0
