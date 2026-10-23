@echo off
setlocal
title BTC Navigator
cd /d "%~dp0"
echo BTC Navigator - keep this window open.
echo First startup requires Python 3.11+ and Internet access.
echo.
if not exist "bootstrap.py" goto incomplete
where py >nul 2>nul
if errorlevel 1 goto plain_python
py -3.11 -c "import sys" >nul 2>nul
if errorlevel 1 goto default_py
py -3.11 bootstrap.py %*
goto finished
:default_py
py -3 bootstrap.py %*
goto finished
:plain_python
where python >nul 2>nul
if errorlevel 1 goto no_python
python bootstrap.py %*
goto finished
:incomplete
echo ERROR: bootstrap.py is missing.
echo Extract the ENTIRE ZIP first, then run START.bat from that folder.
goto failed
:no_python
echo ERROR: Python was not found.
echo Install Python 3.11+ from https://www.python.org/downloads/
echo Enable "Add Python to PATH" during installation, then try again.
goto failed
:finished
set "BTC_EXIT_CODE=%ERRORLEVEL%"
echo.
echo Startup log: "%~dp0startup.log"
echo If startup failed, the actual error is shown above and in startup.log.
echo.
pause
exit /b %BTC_EXIT_CODE%
:failed
echo.
pause
exit /b 1
