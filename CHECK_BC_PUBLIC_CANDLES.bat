@echo off
setlocal
cd /d "%~dp0"
echo ================================================
echo B+C Stage 4 - 4USDT public market preflight
echo This check uses Binance PUBLIC data only.
echo No OpenAI model calls and no real orders.
echo ================================================
if not exist "agent_stage_four_candle_preflight.py" (
  echo ERROR: Missing full release files.
  pause
  exit /b 2
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 agent_stage_four_candle_preflight.py --symbol 4USDT --interval 1h --count 1600
) else (
  python agent_stage_four_candle_preflight.py --symbol 4USDT --interval 1h --count 1600
)
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (
  echo Public candle preflight passed. This does NOT verify paid OpenAI research.
) else (
  echo Public data preflight did not pass. Do NOT authorize paid research yet.
)
pause
exit /b %RESULT%
