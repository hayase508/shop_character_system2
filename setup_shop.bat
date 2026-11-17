@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found.
  echo Install Python 3.10, then run this file again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the Python virtual environment...
  python -m venv --system-site-packages .venv
  if errorlevel 1 goto :failed
)

echo Installing required libraries...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo.
echo Setup completed successfully.
echo Double-click test_shop.bat to test the system.
pause
exit /b 0

:failed
echo.
echo Setup failed. Review the error messages above.
pause
exit /b 1
