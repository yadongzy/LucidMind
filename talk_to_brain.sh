#!/bin/bash
# LucidMind 一键沟通脚本 — 老师(Cascade)与大脑的快速通信通道
# 用法: ./talk_to_brain.sh "你的消息"
# 或直接运行进入交互模式

BASE="http://localhost:8000"

# 检查服务器是否运行
check_server() {
    if ! curl -s "$BASE/api/health" > /dev/null 2>&1; then
        echo "⚠️  服务器未启动，正在启动..."
        cd "$(dirname "$0")"
        python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 &
        sleep 5
        if ! curl -s "$BASE/api/health" > /dev/null 2>&1; then
            echo "❌ 服务器启动失败"; exit 1
        fi
        echo "✅ 服务器已启动"
    fi
}

# 发送消息给大脑
send_message() {
    local msg="$1"
    local escaped=$(echo "$msg" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))")
    curl -s -X POST "$BASE/api/teacher/send" \
        -H "Content-Type: application/json" \
        -d "{\"message\": $escaped}" | python3 -c "import sys,json; d=json.load(sys.stdin); print('✅ 已发送' if d.get('sent') else '❌ 发送失败')"
}

# 获取大脑最新回复
get_reply() {
    curl -s "$BASE/api/sessions/teaching/history" | python3 -c "
import sys, json
data = json.load(sys.stdin)
msgs = data.get('messages', [])
for m in reversed(msgs):
    if m.get('role') == 'assistant':
        print('🧠 大脑:', (m.get('content') or '')[:500])
        break
"
}

# 获取大脑状态
get_status() {
    curl -s "$BASE/api/brain/status" | python3 -c "
import sys, json
d = json.load(sys.stdin).get('daemon', {})
print(f\"状态: {'运行中' if d.get('running') else '停止'} | {'暂停' if d.get('paused') else '活跃'}\")
print(f\"思考次数: {d.get('thought_count',0)} | 行动次数: {d.get('action_count',0)}\")
"
}

check_server

if [ -n "$1" ]; then
    send_message "$1"
    echo "⏳ 等待大脑回复..."
    sleep 30
    get_reply
else
    echo "🧠 LucidMind 老师-大脑沟通终端"
    echo "命令: /status 查看状态 | /reply 获取回复 | /quit 退出"
    echo "---"
    while true; do
        read -p "老师> " input
        case "$input" in
            /quit|/exit) echo "再见"; break ;;
            /status) get_status ;;
            /reply) get_reply ;;
            "") continue ;;
            *) send_message "$input"; echo "⏳ 等待回复..."; sleep 20; get_reply ;;
        esac
    done
fi
