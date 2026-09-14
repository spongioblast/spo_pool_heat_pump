@echo off
setlocal
set "SCRIPT=%~dp0dr164_event_off.py"
py -3 "%SCRIPT%" %*
if not errorlevel 9009 exit /b %ERRORLEVEL%
python "%SCRIPT%" %*
if not errorlevel 9009 exit /b %ERRORLEVEL%
echo Python 3 is required. Install from https://www.python.org/ and add it to PATH.
exit /b 1
