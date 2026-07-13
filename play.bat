@echo off
setlocal
cd /d "%~dp0"

set WORLD=%1
if "%WORLD%"=="" set WORLD=mingyun_zhiyu_peace_city
set PYTHONPATH=src

echo Compiling world: %WORLD%
python -m compilableworld compile examples\%WORLD% --out build\%WORLD%
if errorlevel 1 (
  echo.
  echo Build failed - see the error above.
  pause
  exit /b 1
)

start "" http://127.0.0.1:8765/
echo Web UI will open in your browser: http://127.0.0.1:8765/
echo Press Ctrl+C to stop the server.
python -m compilableworld serve build\%WORLD%\world.package.json --port 8765

pause
