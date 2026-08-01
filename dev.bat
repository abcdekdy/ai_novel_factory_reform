@echo off
setlocal

title AI Novel Factory - Dev

set "PROJECT=%~dp0"
if "%PROJECT:~-1%"=="\" set "PROJECT=%PROJECT:~0,-1%"

echo ========================================
echo   AI Novel Factory v2.0 - Dev Mode
echo ========================================
echo.

echo [1/2] Starting Vite Frontend (port 5173)...
start "ViteFrontend" /B /D "%PROJECT%\frontend" cmd /c "npm run dev"

echo.
echo [WAIT] Vite starting (5s)...
timeout /t 5 /nobreak >nul

echo.
echo [2/2] Starting Electron (Python backend will be managed by Electron)...
echo.
cd /d "%PROJECT%"
set "NODE_ENV=development"
npx electron .

echo.
echo --- Electron closed, cleanup ---

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
    echo Killed process on port 5173 (PID: %%a)
)

echo Done. Press any key to exit.
timeout /t 2 /nobreak >nul
exit
