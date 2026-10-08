@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment was not found.
  echo Run: python -m venv .venv
  echo Then: .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

powershell.exe -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8000/health ^| Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  echo Starting Ichigo Cafe server...
  start "Ichigo Cafe Server" /D "%~dp0" "%~dp0.venv\Scripts\python.exe" -m app
)

powershell.exe -NoProfile -Command "$deadline=(Get-Date).AddSeconds(20); do { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8000/health ^| Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 500 } } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 (
  echo The server did not start. Check the Ichigo Cafe Server window for details.
  pause
  exit /b 1
)

start "" "http://127.0.0.1:8000/?v=20261008-6"
exit /b 0
