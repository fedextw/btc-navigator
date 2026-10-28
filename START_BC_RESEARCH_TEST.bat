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
if not exist "PACKAGE_SHA256.json" (
  echo ERROR: Missing package integrity manifest. Extract the full ZIP again.
  pause
  exit /b 2
)
if not exist "agent_package_integrity.py" (
  echo ERROR: Missing integrity verifier. Extract the full ZIP again.
  pause
  exit /b 2
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 agent_package_integrity.py
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo ERROR: Python 3.11+ is required.
    pause
    exit /b 1
  )
  python agent_package_integrity.py
)
if errorlevel 1 (
  echo ERROR: Package integrity failed. Please extract a fresh ZIP.
  pause
  exit /b 2
)
set "BTC_NAVIGATOR_STATE_DIR=%~dp0.agent-test-state"
if not exist "%BTC_NAVIGATOR_STATE_DIR%" mkdir "%BTC_NAVIGATOR_STATE_DIR%"
set "BC_OPENAI_ARGS="
if defined OPENAI_API_KEY (
  echo.
  echo OpenAI paid research is available. Maximum 10 model calls for this session.
  echo Paper research only. No live orders.
  choice /C YN /N /M "Authorize up to 10 paid OpenAI calls now? [Y/N]: "
  if errorlevel 2 (
    echo OpenAI paid research not authorized; normal paper research continues.
  ) else (
    set "BC_OPENAI_ARGS=--openai-batches 1 --openai-ack-calls 10"
  )
)
call "%~dp0START.bat" --port 8591 --agent-research %BC_OPENAI_ARGS% %*
exit /b %ERRORLEVEL%
