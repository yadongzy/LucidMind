#!/bin/bash
# ============================================
# LucidMind 一键启动脚本
# ============================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

PORT=8765
URL="http://localhost:$PORT"

# 出错时暂停，防止双击闪退
trap 'echo ""; echo "❌ 启动异常，按回车键关闭..."; read' ERR

echo ""
echo "  🧠  LucidMind 一键启动"
echo "  ════════════════════════════════"
echo ""

# 1. 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "  ❌ 未找到 python3，请先安装 Python 3.11+"
    echo ""; read -p "  按回车键关闭..." ; exit 1
fi
echo "  ✅ Python3: $(python3 --version 2>&1)"

# 2. 检查虚拟环境
if [ -d "venv" ]; then
    echo "  📦 激活虚拟环境 (venv)..."
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "  📦 激活虚拟环境 (.venv)..."
    source .venv/bin/activate
else
    echo "  📦 创建虚拟环境..."
    python3 -m venv venv
    source venv/bin/activate
    echo "  📦 安装依赖..."
    pip install -r requirements.txt
fi

# 3. 检查 .env
if [ ! -f ".env" ]; then
    echo "  ⚠️  未找到 .env 文件，正在创建模板..."
    cat > .env << 'ENVEOF'
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
ENVEOF
    echo "  ⚠️  请编辑 .env 填入你的 API Key，然后重新运行此脚本"
    echo ""; read -p "  按回车键关闭..." ; exit 1
fi
echo "  ✅ .env 已加载"

# 4. 创建数据目录
mkdir -p data logs plugins

# 5. 构建前端
if [ -d "frontend-v2" ] && [ -x "$(command -v npm 2>/dev/null)" ]; then
    if [ ! -f "frontend/dist/index.html" ]; then
        echo "  🎨 构建前端（首次，稍等）..."
        (cd frontend-v2 && npm install --silent 2>/dev/null && npm run build 2>/dev/null) | tail -3
    else
        echo "  ✅ 前端已构建"
    fi
else
    if [ ! -f "frontend/dist/index.html" ]; then
        echo "  ⚠️  未安装 npm 且前端未构建，页面可能无法访问"
    else
        echo "  ✅ 前端已构建（跳过npm）"
    fi
fi

# 6. 检查端口
if lsof -ti:$PORT &>/dev/null 2>&1; then
    echo "  ⚠️  端口 $PORT 已被占用，正在关闭旧进程..."
    lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# 7. 延迟自动打开浏览器（后台等待服务启动）
(
    sleep 3
    # 等待服务真正就绪
    for i in $(seq 1 20); do
        if curl -s -o /dev/null -w "" "http://localhost:$PORT/api/health" 2>/dev/null; then
            if [ "$(uname)" = "Darwin" ]; then
                open "$URL"
            elif command -v xdg-open &>/dev/null; then
                xdg-open "$URL"
            fi
            break
        fi
        sleep 1
    done
) &

# 8. 启动服务
echo ""
echo "  ════════════════════════════════"
echo "  🚀 启动 LucidMind (端口 $PORT)"
echo "  📎 $URL"
echo "  🛑 按 Ctrl+C 停止"
echo "  ════════════════════════════════"
echo ""

python3 -m uvicorn api.main:app --host 0.0.0.0 --port $PORT

# 正常退出也暂停（双击运行时防止窗口消失）
echo ""
echo "  服务已停止。按回车键关闭..."
read
