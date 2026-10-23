@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 launch.py %*
) else (
    python launch.py %*
)
if errorlevel 1 (
    echo.
    echo 啟動失敗。請確認已安裝 Python 3.11 以上版本並勾選 Add Python to PATH。
    pause
)
