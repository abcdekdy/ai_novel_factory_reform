@echo off
setlocal EnableExtensions
chcp 65001 >nul
rem 某些终端/IDE 会设置 ELECTRON_RUN_AS_NODE=1，导致 Electron 以 Node 模式启动并退出
set "ELECTRON_RUN_AS_NODE="
title AI Novel Factory - Dev Mode (ASCII path)

rem ============================================================
rem  开发模式启动器（兼容中文项目路径）
rem  Electron 不能在含中文/全角字符的路径下启动，因此先把项目
rem  同步到纯英文目录，再从该目录运行 dev.bat。
rem  用户数据仍指向原项目 backend\（通过 NOVEL_DATA_DIR），不会分裂。
rem  首次同步较慢（会复制 node_modules），之后只同步改动。
rem ============================================================

set "SRC=%~dp0"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
set "DST=%USERPROFILE%\AI-Novel-Factory-Dev"

echo 正在同步项目到纯英文目录：
echo   %DST%
echo 首次运行需要复制依赖，请耐心等待...
robocopy "%SRC%" "%DST%" /MIR /XD "%SRC%\.git" "%SRC%\out" "%SRC%\backend\dist" "%SRC%\backend\build" /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo [错误] 同步失败，请检查磁盘空间或关闭正在占用的程序。
    pause
    exit /b 1
)

if not exist "%DST%\dev.bat" (
    echo [错误] 同步后未找到 dev.bat。
    pause
    exit /b 1
)

rem 让开发环境继续使用原项目的配置与作品数据
set "NOVEL_DATA_DIR=%SRC%\backend"

echo 启动开发模式（Vite + Electron，Python 后端由 Electron 管理）...
cd /d "%DST%"
call "%DST%\dev.bat"
exit /b 0
