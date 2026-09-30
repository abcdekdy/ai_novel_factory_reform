@echo off
setlocal
chcp 65001 >nul

title AI Novel Factory - Build Portable

set "PROJECT=%~dp0"
if "%PROJECT:~-1%"=="\" set "PROJECT=%PROJECT:~0,-1%"

echo ========================================
echo   AI 小说工厂 - 免安装绿色版构建
echo ========================================
echo.
echo 产物：out\make\zip\win32\x64\ 下的 zip
echo 解压后双击 ai-novel-factory.exe 即可运行，无需安装 Python。
echo.

echo [1/3] 构建前端...
cd /d "%PROJECT%\frontend"
call npm run build
if errorlevel 1 goto error

echo.
echo [2/3] 冻结后端（PyInstaller）...
cd /d "%PROJECT%\backend"
python build_backend.py
if errorlevel 1 goto error

echo.
echo [3/3] 组装绿色版并压缩...
cd /d "%PROJECT%"
python package_portable.py
if errorlevel 1 goto error

echo.
echo ========================================
echo   构建完成！
echo   产物目录：%PROJECT%\out\
echo ========================================
dir /b "%PROJECT%\out\*.zip"
goto end

:error
echo.
echo !!! 构建失败，请检查上方错误信息 !!!

:end
echo.
pause
