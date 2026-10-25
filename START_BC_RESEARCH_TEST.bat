@echo off
setlocal
title BTC Navigator B+C - Independent Research Test
cd /d "%~dp0"
echo =====================================================
echo BTC Navigator B+C - independent research test
echo Data: %~dp0.agent-test-state
echo Website: http://127.0.0.1:8591
echo No real orders. Existing BTC Navigator 1.1 untouched.
echo =====================================================
echo.
if not exist "bootstrap.py" (
  echo ERROR: Please extract the full B+C package first.
  pause
  exit /b 1
)
set "BTC_NAVIGATOR_STATE_DIR=%~dp0.agent-test-state"
if not exist "%BTC_NAVIGATOR_STATE_DIR%" mkdir "%BTC_NAVIGATOR_STATE_DIR%"
call "%~dp0START.bat" --port 8591 --agent-research %*
exit /b %ERRORLEVEL%
