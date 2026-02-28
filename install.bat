@echo off
chcp 65001 >nul 2>&1
:: ============================================
:: LucidMind 一键安装脚本 (Windows)
:: ============================================

setlocal EnableDelayedExpansion

echo.
echo   🧠  LucidMind 一键安装
echo   ════════════════════════════════
echo.

cd /d "%~dp0"

:: ── 1. 检查 Python ──
set "PYTHON="
set "PYVER="
where python >nul 2>&1
if !errorlevel!==0 (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
    set "PYTHON=python"
)
if not defined PYTHON (
    where python3 >nul 2>&1
    if !errorlevel!==0 (
        for /f "tokens=2 delims= " %%v in ('python3 --version 2^>^&1') do set "PYVER=%%v"
        set "PYTHON=python3"
    )
)

if not defined PYTHON (
    echo   ❌ 未找到 Python，请先安装 Python 3.10+
    echo      下载: https://www.python.org/downloads/
    echo      安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)
echo   ✅ Python: !PYVER!

:: ── 2. 创建虚拟环境 ──
if not exist "venv" (
    if not exist ".venv" (
        echo   📦 创建虚拟环境...
        !PYTHON! -m venv venv
        if !errorlevel! neq 0 (
            echo   ❌ 虚拟环境创建失败
            pause
            exit /b 1
        )
        echo   ✅ 虚拟环境已创建
    )
)

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

:: ── 3. 安装 Python 依赖 ──
echo   📦 安装 Python 依赖...
pip install --upgrade pip -q 2>nul
pip install -r requirements.txt -q
if !errorlevel! neq 0 (
    echo   ⚠️  部分依赖安装可能失败，请检查上方输出
) else (
    echo   ✅ Python 依赖已安装
)

:: ── 4. 创建数据目录 ──
if not exist "data" mkdir data
if not exist "logs" mkdir logs
if not exist "data\output" mkdir data\output
if not exist "data\memory" mkdir data\memory
if not exist "data\notes" mkdir data\notes
if not exist "skills" mkdir skills

:: ── 5. 创建 .env 模板 ──
if not exist ".env" (
    (
        echo # LucidMind Environment Configuration
        echo # 至少需要一个 LLM API Key 才能正常使用
        echo.
        echo # DeepSeek API (推荐^)
        echo DEEPSEEK_API_KEY=your_deepseek_api_key_here
        echo.
        echo # MiniMax API (备选^)
        echo MINIMAX_API_KEY=your_minimax_api_key_here
        echo.
        echo # 可选：本地 Ollama (需先安装 ollama 并拉取模型^)
        echo # OLLAMA_MODEL=qwen2.5:7b
    ) > .env
    echo   ⚠️  已创建 .env 模板，请编辑填入你的 API Key
) else (
    echo   ✅ .env 已存在
)

:: ── 6. 构建前端 ──
if exist "frontend-v2" (
    where npm >nul 2>&1
    if !errorlevel!==0 (
        if not exist "frontend\dist\index.html" (
            echo   🎨 构建前端...
            cd frontend-v2
            call npm install --silent 2>nul
            call npm run build 2>nul
            cd ..
            echo   ✅ 前端已构建
        ) else (
            echo   ✅ 前端已构建（跳过）
        )
    ) else (
        if exist "frontend\dist\index.html" (
            echo   ✅ 前端已预构建（无 npm 也可使用）
        ) else (
            echo   ⚠️  未安装 npm，前端未构建
            echo      安装 Node.js: https://nodejs.org/
            echo      然后运行: cd frontend-v2 ^&^& npm install ^&^& npm run build
        )
    )
)

echo.
echo   ════════════════════════════════
echo   ✅ 安装完成！
echo.
echo   下一步：
echo     1. 编辑 .env 填入 API Key
echo     2. 双击 start.bat 启动服务
echo   ════════════════════════════════
echo.
pause
