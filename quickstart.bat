@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "NO_SERVE=0"
if "%~1"=="" goto :arguments_ready
if /I "%~1"=="--no-serve" (
    set "NO_SERVE=1"
    goto :arguments_ready
)

echo Usage: quickstart.bat [--no-serve]
echo.
echo --no-serve completes setup, tests, and database initialization without starting Flask.
exit /b 2

:arguments_ready
echo.
echo === Roman Coin Atlas quickstart ===

if exist ".venv\Scripts\python.exe" goto :venv_ready
if exist ".venv" (
    echo ERROR: .venv exists but does not contain Scripts\python.exe.
    echo Remove or repair that virtual environment, then run this script again.
    exit /b 1
)

where py >nul 2>nul
if errorlevel 1 goto :create_venv_with_python

echo Creating virtual environment with the Windows Python launcher...
py -3 -m venv .venv
if errorlevel 1 goto :failed
goto :venv_ready

:create_venv_with_python
echo Creating virtual environment with python from PATH...
python -m venv .venv
if errorlevel 1 goto :failed

:venv_ready
set "VENV_PYTHON=.venv\Scripts\python.exe"
%VENV_PYTHON% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
if errorlevel 1 (
    echo ERROR: Roman Coin Atlas requires Python 3.12 or later.
    exit /b 1
)

echo Installing project dependencies...
%VENV_PYTHON% -m pip install --upgrade pip
if errorlevel 1 goto :failed
%VENV_PYTHON% -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo Running tests...
%VENV_PYTHON% -m pytest
if errorlevel 1 goto :failed

echo Initializing the local SQLite database...
%VENV_PYTHON% project.py init-db
if errorlevel 1 goto :failed

if "%NO_SERVE%"=="1" (
    echo Quickstart verification completed without starting Flask.
    exit /b 0
)

echo.
echo Starting Roman Coin Atlas at http://127.0.0.1:5000
echo Press Ctrl+C to stop the local server.
%VENV_PYTHON% project.py serve
exit /b %errorlevel%

:failed
echo.
echo Quickstart stopped because a command failed. Read the message above and run it again after fixing the issue.
exit /b 1
