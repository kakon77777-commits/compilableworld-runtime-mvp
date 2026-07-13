@echo off
setlocal
cd /d "%~dp0"

set WORLD=%1
if "%WORLD%"=="" set WORLD=mingyun_zhiyu_peace_city
set PYTHONPATH=src

echo 正在編譯世界: %WORLD%
python -m compilableworld compile examples\%WORLD% --out build\%WORLD%
if errorlevel 1 (
  echo.
  echo 編譯失敗，請檢查上方錯誤訊息。
  pause
  exit /b 1
)

start "" http://127.0.0.1:8765/
echo 網頁介面即將在瀏覽器開啟：http://127.0.0.1:8765/
echo 按 Ctrl+C 可停止伺服器。
python -m compilableworld serve build\%WORLD%\world.package.json --port 8765

pause
