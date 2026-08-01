@echo off
chcp 65001 >nul
echo ========================================
echo   AI 小说工厂（新版）— 一键安装
echo ========================================
echo.

echo [1/3] 安装根目录依赖（Electron）...
call npm install
if errorlevel 1 goto error

echo.
echo [2/3] 安装前端依赖...
cd frontend
call npm install
cd ..
if errorlevel 1 goto error

echo.
echo [3/3] 安装 Python 后端依赖...
cd backend
call pip install -r requirements.txt
cd ..
if errorlevel 1 goto error

echo.
echo ========================================
echo   安装完成！
echo   运行 dev.bat 启动开发模式
echo ========================================
goto end

:error
echo.
echo !!! 安装失败，请检查网络连接 !!!

:end
pause
