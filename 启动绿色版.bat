@echo off
setlocal EnableExtensions
chcp 65001 >nul
rem 某些终端/IDE 会设置 ELECTRON_RUN_AS_NODE=1，导致 Electron 以 Node 模式启动并退出
set "ELECTRON_RUN_AS_NODE="
title AI Novel Factory - Portable Launcher

rem ============================================================
rem  绿色版启动器
rem  Electron 不能在含中文/全角字符的路径下启动（会直接崩溃），
rem  因此这里把 out 下的绿色版同步到纯英文目录再启动。
rem  数据目录 data\ 会保留，不会被覆盖。
rem ============================================================

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "SRC=%ROOT%\out\AI-Novel-Factory-win32-x64"
if not exist "%SRC%\ai-novel-factory.exe" set "SRC=%ROOT%\out\AI小说工厂-win32-x64"

if not exist "%SRC%\ai-novel-factory.exe" (
    echo [错误] 未找到绿色版构建产物：
    echo        %ROOT%\out\AI-Novel-Factory-win32-x64
    echo 请先双击 build-portable.bat，或执行 npm run build。
    echo.
    pause
    exit /b 1
)

rem 安装到桌面上容易找到的英文目录：<桌面>\AI-Novel-Factory
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP_DIR=%%D"
if not defined DESKTOP_DIR set "DESKTOP_DIR=%USERPROFILE%\Desktop"
set "DST=%DESKTOP_DIR%\AI-Novel-Factory"
if not exist "%DST%" mkdir "%DST%" >nul 2>&1

rem 应用运行时文件被占用，先提示关闭
tasklist /FI "IMAGENAME eq ai-novel-factory.exe" 2>nul | find /I "ai-novel-factory.exe" >nul
if not errorlevel 1 (
    echo [提示] 应用正在运行，正在尝试关闭...
    taskkill /IM ai-novel-factory.exe /F >nul 2>&1
    timeout /t 2 /nobreak >nul
)

echo 安装位置：%DST%
echo 正在同步程序文件到纯英文目录...
robocopy "%SRC%" "%DST%" /E /XO /XD "%SRC%\data" /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo [错误] 复制失败，请确认应用已关闭且磁盘可写。
    pause
    exit /b 1
)

rem 确保数据目录存在（程序首次启动也会自动创建）
if not exist "%DST%\data" mkdir "%DST%\data" >nul 2>&1

echo 启动 AI 小说工厂...
start "" "%DST%\ai-novel-factory.exe"
exit /b 0
