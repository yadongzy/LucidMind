#!/bin/bash
# ============================================
# LucidMind 一键启动脚本
# ============================================

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "🧠 LucidMind 启动中..."
echo "=================================="

# 1. 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "❌ 未找到 python3，请先安装 Python 3.11+"
    exit 1
fi

# 2. 检查虚拟环境
if [ -d "venv" ]; then
    echo "📦 激活虚拟环境..."
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "📦 激活虚拟环境..."
    source .venv/bin/activate
else
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
    source venv/bin/activate
    echo "📦 安装依赖..."
    pip install -r requirements.txt
fi

# 3. 检查 .env
if [ ! -f ".env" ]; then
    echo "⚠️  未找到 .env 文件，创建模板..."
    cat > .env << 'EOF'
# LucidMind Environment
DEEPSEEK_API_KEY=your_deepseek_api_key_here
MINIMAX_API_KEY=your_minimax_api_key_here

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
EOF
    echo "⚠️  请编辑 .env 填入你的 API Key，然后重新运行此脚本"
    exit 1
fi

# 4. 创建数据目录
mkdir -p data logs plugins

# 5. 构建前端（如果有 node）
if [ -d "frontend-v2" ] && command -v npm &>/dev/null; then
    if [ ! -d "frontend/dist" ] || [ "frontend-v2/src" -nt "frontend/dist/index.html" ]; then
        echo "🎨 构建前端..."
        (cd frontend-v2 && npm install --silent && npm run build) 2>&1 | tail -3
    else
        echo "🎨 前端已是最新"
    fi
else
    echo "⚠️  跳过前端构建（未安装 npm 或无 frontend-v2 目录）"
fi

# 6. 检查端口
PORT=8765
if lsof -ti:$PORT &>/dev/null; then
    echo "⚠️  端口 $PORT 已被占用，正在关闭旧进程..."
    lsof -ti:$PORT | xargs kill -9 2>/dev/null
    sleep 1
fi

# 7. 启动服务
echo "=================================="
echo "🚀 启动 LucidMind 服务 (端口 $PORT)..."
echo "   访问地址: http://localhost:$PORT"
echo "   按 Ctrl+C 停止"
echo "=================================="

python3 -m uvicorn api.main:app --host 0.0.0.0 --port $PORT
