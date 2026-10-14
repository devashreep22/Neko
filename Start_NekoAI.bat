@echo off
setlocal
title NekoAI
set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "NEKO_PYTHON="

for %%E in (.venv venv desktop-runtime-venv) do call :check_env "%%E"
if defined NEKO_PYTHON goto python_ready

echo No working NekoAI Python environment was found. Creating one...
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv "%BACKEND%\desktop-runtime-venv"
) else (
    where python >nul 2>nul
    if errorlevel 1 goto nopython
    python -m venv "%BACKEND%\desktop-runtime-venv"
)
if errorlevel 1 goto nopython
set "NEKO_PYTHON=%BACKEND%\desktop-runtime-venv\Scripts\python.exe"
"%NEKO_PYTHON%" -m pip install --disable-pip-version-check -r "%BACKEND%\requirements.txt"
if errorlevel 1 goto setupfailed

:python_ready
set "NEKO_PYTHON=%NEKO_PYTHON%"
cd /d "%ROOT%desktop"
if not exist "node_modules\electron\dist\electron.exe" (
    echo Setting up NekoAI desktop dependencies...
    call npm.cmd install --no-audit --no-fund
    if errorlevel 1 goto setupfailed
)
call npm.cmd run build
if errorlevel 1 goto setupfailed
call npm.cmd start
if errorlevel 1 pause
endlocal
exit /b 0

:check_env
if not exist "%BACKEND%\%~1\Scripts\python.exe" exit /b 0
echo Checking Python environment: %BACKEND%\%~1
"%BACKEND%\%~1\Scripts\python.exe" -c "import sys, fastapi, uvicorn; print('Python', sys.version.split()[0], 'with FastAPI and Uvicorn is ready.')"
if errorlevel 1 (
    echo This environment cannot start or is missing backend dependencies.
    if exist "%BACKEND%\%~1\pyvenv.cfg" type "%BACKEND%\%~1\pyvenv.cfg"
    exit /b 0
)
set "NEKO_PYTHON=%BACKEND%\%~1\Scripts\python.exe"
exit /b 0

:nopython
echo.
echo No usable Python 3.10+ installation was found. Existing virtual environments
echo could not start with their configured base interpreter (details above).
echo Install a supported Python 3.10+ runtime and enable its launcher,
echo then run this file again. NekoAI will create a fresh environment without removing
echo the existing venv or .venv folders.
pause
exit /b 1

:setupfailed
echo.
echo NekoAI setup or startup failed. Review the error above and try again.
pause
exit /b 1
