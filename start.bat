@echo off
chcp 65001 >nul 2>&1
:: ============================================
:: LucidMind 一键启动脚本 (Windows)
:: ============================================

setlocal EnableDelayedExpansion

set "PORT=8765"
set "URL=http://localhost:%PORT%"

echo.
echo   🧠  LucidMind 一键启动
echo   ════════════════════════════════
echo.

cd /d "%~dp0"

:: ── 1. 检查 Python ──
set "PYTHON="
where python >nul 2>&1
if %errorlevel%==0 set "PYTHON=python"
if not defined PYTHON (
    where python3 >nul 2>&1
    if %errorlevel%==0 set "PYTHON=python3"
)
if not defined PYTHON (
    echo   ❌ 未找到 Python，请先运行 install.bat
    pause
    exit /b 1
)
echo   ✅ Python: %PYTHON%

:: ── 2. 激活虚拟环境 ──
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo   📦 虚拟环境已激活 (venv^)
) else if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo   📦 虚拟环境已激活 (.venv^)
) else (
    echo   ⚠️  未找到虚拟环境，请先运行 install.bat
    echo   或手动执行: %PYTHON% -m venv venv
    pause
    exit /b 1
)

:: ── 3. 检查 .env ──
if not exist ".env" (
    echo   ⚠️  未找到 .env 文件，请先运行 install.bat 并编辑 .env
    pause
    exit /b 1
)
echo   ✅ .env 已加载

:: ── 4. 创建数据目录 ──
if not exist "data" mkdir data
if not exist "logs" mkdir logs
if not exist "skills" mkdir skills

:: ── 5. 构建前端（如果需要） ──
if not exist "frontend\dist\index.html" (
    where npm >nul 2>&1
    if %errorlevel%==0 (
        echo   🎨 构建前端...
        cd frontend-v2
        call npm install --silent 2>nul
        call npm run build 2>nul
        cd ..
    ) else (
        echo   ⚠️  前端未构建且无 npm，页面可能无法访问
    )
) else (
    echo   ✅ 前端已构建
)

:: ── 6. 延迟打开浏览器 ──
start /b cmd /c "timeout /t 5 /nobreak >nul & start %URL%"

:: ── 7. 启动服务 ──
echo.
echo   ════════════════════════════════
echo   🚀 启动 LucidMind (端口 %PORT%^)
echo   📎 %URL%
echo   🛑 按 Ctrl+C 停止
echo   ════════════════════════════════
echo.

%PYTHON% -m uvicorn api.main:app --host 0.0.0.0 --port %PORT%

echo.
echo   服务已停止。
pause
