#!/bin/bash
# ============================================
# LucidMind 一键安装脚本 (Linux / macOS)
# ============================================

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo ""
echo "  🧠  LucidMind 一键安装"
echo "  ════════════════════════════════"
echo ""

# ── 1. 检查 Python ──
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  ❌ 未找到 Python 3.10+，请先安装"
    echo "     Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "     macOS: brew install python3"
    echo "     或从 https://www.python.org/downloads/ 下载"
    exit 1
fi
echo "  ✅ Python: $($PYTHON --version 2>&1)"

# ── 2. 创建虚拟环境 ──
if [ ! -d "venv" ] && [ ! -d ".venv" ]; then
    echo "  📦 创建虚拟环境..."
    $PYTHON -m venv venv
    echo "  ✅ 虚拟环境已创建"
fi

if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# ── 3. 安装 Python 依赖 ──
echo "  📦 安装 Python 依赖..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  ✅ Python 依赖已安装"

# ── 4. 创建数据目录 ──
mkdir -p data logs data/output data/memory data/notes skills

# ── 5. 创建 .env 模板（如不存在） ──
if [ ! -f ".env" ]; then
    cat > .env << 'ENVEOF'
# LucidMind Environment Configuration
# 至少需要一个 LLM API Key 才能正常使用

# DeepSeek API (推荐)
DEEPSEEK_API_KEY=your_deepseek_api_key_here

# MiniMax API (备选)
MINIMAX_API_KEY=your_minimax_api_key_here

# 可选：本地 Ollama (需先安装 ollama 并拉取模型)
# OLLAMA_MODEL=qwen2.5:7b

# 可选：Telegram 推送
# TELEGRAM_BOT_TOKEN=your_bot_token
# TELEGRAM_ALLOWED_USERS=your_user_id

# 可选：飞书
# FEISHU_APP_ID=
# FEISHU_APP_SECRET=
# FEISHU_VERIFICATION_TOKEN=

# 可选：企业微信
# WECOM_CORP_ID=
# WECOM_AGENT_ID=
# WECOM_SECRET=
# WECOM_TOKEN=
ENVEOF
    echo "  ⚠️  已创建 .env 模板，请编辑填入你的 API Key"
else
    echo "  ✅ .env 已存在"
fi

# ── 6. 构建前端（如果有 npm） ──
if [ -d "frontend-v2" ]; then
    if command -v npm &>/dev/null; then
        if [ ! -f "frontend/dist/index.html" ]; then
            echo "  🎨 构建前端..."
            (cd frontend-v2 && npm install --silent 2>/dev/null && npm run build 2>/dev/null)
            echo "  ✅ 前端已构建"
        else
            echo "  ✅ 前端已构建（跳过）"
        fi
    else
        if [ -f "frontend/dist/index.html" ]; then
            echo "  ✅ 前端已预构建（无 npm 也可使用）"
        else
            echo "  ⚠️  未安装 npm，前端未构建"
            echo "     安装 Node.js: https://nodejs.org/"
            echo "     然后运行: cd frontend-v2 && npm install && npm run build"
        fi
    fi
fi

echo ""
echo "  ════════════════════════════════"
echo "  ✅ 安装完成！"
echo ""
echo "  下一步："
echo "    1. 编辑 .env 填入 API Key"
echo "    2. 运行 ./start.sh 启动服务"
echo "  ════════════════════════════════"
echo ""
