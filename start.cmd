@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv || goto :failed
)
".venv\Scripts\python.exe" -c "import aiohttp,aiohttp_socks,psutil,yt_dlp,httpx,h2" 2>nul || ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :failed
if not exist dist\index.html (
  call npm.cmd ci || goto :failed
  call npm.cmd run build || goto :failed
)
".venv\Scripts\python.exe" launch.py %*
if errorlevel 1 goto :failed
exit /b 0
:failed
pause
exit /b 1

