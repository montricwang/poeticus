@echo off
setlocal
set "APP=%~dp0server.py"
set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if not exist "%PYTHON%" set "PYTHON=pythonw.exe"
powershell.exe -NoProfile -Command "$ErrorActionPreference='Stop'; try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/services' -TimeoutSec 1; if ($r.services) {exit 0} } catch {}; exit 1" >nul 2>&1
if errorlevel 1 (
  start "" "%PYTHON%" "%APP%" --no-browser
  timeout /t 1 /nobreak >nul
)
start "" "http://127.0.0.1:8765"
endlocal
