"""Brain 配置中心 — 集中管理所有大脑相关的常量、阈值、模板路径。

对标行业最佳实践（Claude Code / Codex CLI / OpenCode）：
- 数值常量：命名化，集中管理
- 提示模板：外部化到 prompts/ 目录
- 关键词/模式：外部化到 data/ 目录 JSON 文件
- 模型能力：标签化，不硬编码模型名
"""

import json
import re
from pathlib import Path

_BASE_DIR = Path(__file__).parent

# ═══════════════════════════════════════════════════════════
# 第一层：数值常量（命名化，集中管理）
# ═══════════════════════════════════════════════════════════

# — 工具循环 —
TOOL_LOOP_TIMEOUT_SEC = 60
MIN_TOOL_ROUNDS = 2
DEFAULT_TOOL_ROUNDS = 4
MAX_TOOL_ROUNDS = 8

# — System Prompt Token 预算 —
MAX_SYSTEM_PROMPT_TOKENS = 4000

# — 历史管理 —
MAX_HISTORY_HARD_LIMIT = 60
LOCAL_MODEL_HISTORY_LIMIT = 6
REMOTE_MODEL_HISTORY_LIMIT = 20
LOCAL_SOUL_MAX_LINES = 80

# — 上下文压缩阈值（v1.7 验证值）—
COMPACT_SKIP_TOKENS = 4000
COMPACT_SKIP_MSGS = 15
COMPACT_PRUNE_TOKENS = 6000
COMPACT_PRUNE_TOOL_CHARS = 2000
COMPACT_PRUNE_HEAD_CHARS = 1000
COMPACT_PRUNE_TAIL_CHARS = 500
COMPACT_FULL_TOKENS = 8000
COMPACT_FULL_MSGS = 30
COMPACT_KEEP_RECENT = 8
COMPACT_INLINE_TOOL_CHARS = 3000
COMPACT_INLINE_HEAD_CHARS = 1200
COMPACT_INLINE_TAIL_CHARS = 600

# — 摘要 —
SUMMARY_TIMEOUT_SEC = 10.0

# — LLM 重试 —
LLM_MAX_RETRIES = 3
LLM_BASE_DELAY_SEC = 2.0

# — 学习 —
LESSON_CACHE_TTL_SEC = 60
MIN_LEARNING_INPUT_LEN = 6
CORRECTION_PROMOTE_MIN = 2

# — 资源监控 —
MEM_ALERT_PERCENT = 90
DISK_ALERT_GB = 1

# — 伪流式 —
PSEUDO_STREAM_CHUNK_SIZE = 8
PSEUDO_STREAM_DELAY_SEC = 0.02

# — 工具结果压缩 —
TOOL_RESULT_MAX_CHARS = 3000

# — 空承诺检测 —
EMPTY_PROMISE_MAX_LEN = 500

# — 上下文窗口默认值 —
DEFAULT_CONTEXT_WINDOW = 16000

# ═══════════════════════════════════════════════════════════
# 第二层：提示模板（外部化到 prompts/ 目录，带内联 fallback）
# ═══════════════════════════════════════════════════════════

_PROMPTS_DIR = _BASE_DIR / "prompts"


def _load_prompt(filename: str, fallback: str) -> str:
    """加载提示模板文件，文件不存在时使用内联 fallback。"""
    path = _PROMPTS_DIR / filename
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return fallback.strip()


# 循环检测提示
LOOP_HINT = _load_prompt("loop_hint.md", """
你正在重复同样的失败操作。请停下来思考：
1.分析失败原因 2.用web_search搜索解决方案
3.换一种完全不同的策略 4.实在不行就诚实告诉用户并建议替代方案。不要再重复同样的命令。
""")

# 工具失败提示
FAIL_HINT = _load_prompt("fail_hint.md",
    "[提示] 操作失败。请分析错误原因，考虑：搜索解决方案(web_search)、换方法、或告知用户。")

# 工具使用原则
TOOL_USAGE_HINTS = _load_prompt("tool_usage.md", """
工具使用原则:
1. 需要事实/数据→先用工具获取，不要凭记忆回答
2. 文件操作→用read_file/write_file，不要用run_command cat/echo
3. 搜索信息→web_search；搜索本地文件→grep/find_files
4. 需要执行代码→run_python(安全沙盒)；系统命令→run_command
5. 复杂任务→先用decompose_task拆分，再逐步执行
6. 不确定能否完成→先尝试，失败后换方法，不要直接说不会
7. 多个工具可用时，选最直接的那个（如查天气用get_weather而非web_search）
""")

# 压缩摘要提示
COMPACT_SUMMARY_PROMPT = _load_prompt("compact_summary.md",
    "请用3-5句话概括以下对话的要点（包括完成了什么、讨论了什么、关键结论）：\n\n{summary_text}")

# 学习信号检测提示
LEARNING_DETECT_SYSTEM = _load_prompt("learning_detect_system.md",
    "你是一个意图分类器。只回复 correction、teaching 或 none 中的一个词。")

LEARNING_DETECT_PROMPT = _load_prompt("learning_detect.md", """
判断用户这句话的意图（只回复一个词）:
- correction: 用户在纠正AI之前的错误回答
- teaching: 用户在教AI一个新规则或偏好
- none: 普通对话，既不是纠正也不是教学
""")

# 空回复兜底
EMPTY_REPLY_FALLBACK = _load_prompt("empty_reply_fallback.md",
    "抱歉，我没有生成有效的回复。")

# 错误回复模板
ERROR_RESPONSE_BAD_REQUEST = _load_prompt("error_bad_request.md",
    "抱歉，我遇到了一个技术问题，已自动修复。请再说一次你的问题？")
ERROR_RESPONSE_COOLDOWN = _load_prompt("error_cooldown.md",
    "抱歉，AI服务暂时不可用，正在自动恢复中。请稍后再试。")
ERROR_RESPONSE_TIMEOUT = _load_prompt("error_timeout.md",
    "抱歉，请求超时了。请稍后再试，或者换一种方式提问？")
ERROR_RESPONSE_GENERIC = _load_prompt("error_generic.md",
    "抱歉，处理时遇到问题。我已记录这次失败，下次会避免。请再试一次？")

# 防伪造纠正提示
ANTI_FAKE_CORRECTION = _load_prompt("anti_fake_correction.md", """
[系统] 你刚才声称已完成操作，但实际上没有调用任何工具。
你必须使用真实的工具来执行操作，不能假装已完成。
请使用可用的工具来执行用户的请求。如果没有合适的工具，请如实告知。
""")

# ═══════════════════════════════════════════════════════════
# 第三层：关键词/模式（外部化到 config/ JSON 文件，带内联 fallback）
# ═══════════════════════════════════════════════════════════

_DATA_DIR = _BASE_DIR / "config"


def _load_json(filename: str, fallback):
    """加载 JSON 配置文件，文件不存在时使用内联 fallback。"""
    path = _DATA_DIR / filename
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return fallback


# 快速路径关键词
_fast_path_data = _load_json("fast_path.json", {
    "greeting_patterns": [
        "你好", "您好", "嗨", "hi", "hello", "hey", "嘿", "早", "晚安",
        "早上好", "下午好", "晚上好", "good morning", "good afternoon",
        "good evening", "good night", "在吗", "在不在",
    ],
    "trivial_patterns": [
        "好", "好的", "嗯", "行", "可以", "谢谢", "感谢", "明白", "收到",
        "ok", "okay", "yes", "no", "thanks", "got it", "sure", "继续",
        "下一步", "对", "是的", "没错", "嗯嗯", "哦", "知道了",
        "thank you", "thx", "拜拜", "再见", "bye", "see you",
    ],
    "tool_trigger_keywords": [
        "搜索", "查找", "search", "文件", "读取", "写入", "运行", "执行",
        "命令", "创建", "浏览", "打开网页", "截图", "下载", "删除",
        "安装", "部署", "编译", "grep", "find", "curl", "wget",
        "天气", "weather", "新闻", "news", "股票", "stock",
        "发送", "邮件", "通知", "提醒", "定时", "监控",
        "分析", "http", "链接", "网页", "工具", "url", "打开",
    ],
    "correction_keywords": [
        "不对", "错了", "应该是", "不是这样", "纠正", "修正",
        "wrong", "incorrect", "actually", "有问题", "不准确",
        "记住", "以后", "学会", "你应该", "下次", "别再", "不要再",
        "remember", "from now on", "注意",
    ],
    "complex_keywords": [
        "步骤", "首先", "然后", "接着", "并且", "同时",
    ],
})

GREETING_PATTERNS = set(_fast_path_data["greeting_patterns"])
TRIVIAL_PATTERNS = set(_fast_path_data["trivial_patterns"])
TOOL_TRIGGER_KEYWORDS = _fast_path_data["tool_trigger_keywords"]
CORRECTION_KEYWORDS = _fast_path_data["correction_keywords"]
COMPLEX_KEYWORDS = _fast_path_data.get("complex_keywords", [
    "步骤", "首先", "然后", "接着", "并且", "同时",
])

# 守卫模式（空承诺 + 防伪造）
_guard_data = _load_json("guard_patterns.json", {
    "promise_patterns": [
        "正在尝试", "我来试试", "我去试", "让我试", "我试试",
        "正在利用工具", "正在使用工具", "我来用工具", "让我用",
        "正在执行", "正在处理", "马上", "立刻", "我来帮你",
        "好的，让我", "好的，我来", "好的老大", "好的，老大",
        "正在调用", "正在搜索", "正在查找", "正在查询",
        "请稍等", "稍等", "正在努力", "我正在",
        "I'll try", "Let me try", "I'm working on", "I'm searching",
    ],
    "inability_keywords": [
        "不会", "无法", "不能", "做不到", "没有能力",
        "cannot", "unable", "can't",
    ],
    "learning_trivial": [
        "好", "好的", "嘶", "嗯", "行", "可以", "谢谢", "明白", "收到",
        "ok", "yes", "no", "thanks", "got it", "sure", "继续", "下一步",
    ],
    "correction_fallback_keywords": [
        "不对", "错了", "应该是", "不是这样", "纠正", "修正",
        "wrong", "incorrect", "actually", "有问题", "不准确",
    ],
    "teaching_fallback_keywords": [
        "记住", "以后", "学会", "你应该", "下次", "别再", "不要再",
        "remember", "from now on", "注意",
    ],
    "complexity_search_keywords": [
        "搜索", "查找", "研究", "分析", "对比", "总结", "深度",
        "search", "research", "analyze", "compare", "investigate",
    ],
    "complexity_multi_step_keywords": [
        "然后", "接着", "之后", "步骤", "第一", "第二",
        "and then", "step", "first", "second",
    ],
})

PROMISE_PATTERNS = _guard_data["promise_patterns"]
INABILITY_KEYWORDS = _guard_data["inability_keywords"]
LEARNING_TRIVIAL = set(_guard_data["learning_trivial"])
CORRECTION_FALLBACK_KEYWORDS = _guard_data["correction_fallback_keywords"]
TEACHING_FALLBACK_KEYWORDS = _guard_data["teaching_fallback_keywords"]
COMPLEXITY_SEARCH_KEYWORDS = _guard_data["complexity_search_keywords"]
COMPLEXITY_MULTI_STEP_KEYWORDS = _guard_data["complexity_multi_step_keywords"]

# 工具推断映射
_tool_inference_data = _load_json("tool_inference.json", [
    {"pattern": "删除|移除|清除.*文件", "tool": "delete_file"},
    {"pattern": "创建|新建|写入.*文件", "tool": "write_file"},
    {"pattern": "读取|打开|查看.*文件", "tool": "read_file"},
    {"pattern": "搜索|查询|查找|搜一下|帮我搜", "tool": "web_search"},
    {"pattern": "运行|执行.*命令|脚本", "tool": "run_command"},
    {"pattern": "发送.*邮件|发邮件", "tool": "send_email"},
    {"pattern": "下载|拉取", "tool": "download_file"},
    {"pattern": "截图|屏幕", "tool": "screenshot"},
    {"pattern": "翻译", "tool": "translate"},
])

TOOL_INFERENCE_MAP = [
    (re.compile(item["pattern"], re.I), item["tool"])
    for item in _tool_inference_data
]

# ═══════════════════════════════════════════════════════════
# 第四层：模型能力标签（替代硬编码模型名）
# ═══════════════════════════════════════════════════════════

_model_data = _load_json("model_capabilities.json", {
    "context_windows": {
        "deepseek": 64000,
        "gpt-4o": 128000,
        "gpt-4-turbo": 128000,
        "gpt-4o-mini": 128000,
        "qwen": 32000,
        "llama": 8192,
        "gemma": 8192,
    },
    "strong_fc_models": ["deepseek", "gpt-4"],
})

MODEL_CONTEXT_WINDOWS = _model_data["context_windows"]
STRONG_FC_MODEL_TAGS = _model_data["strong_fc_models"]


def get_context_window(model_name: str) -> int:
    """获取模型的上下文窗口大小（tokens）。"""
    for key, val in MODEL_CONTEXT_WINDOWS.items():
        if key.lower() in model_name.lower():
            return val
    return DEFAULT_CONTEXT_WINDOW


def is_strong_fc_model(model_name: str) -> bool:
    """检查模型是否具有强 function calling 能力。"""
    return any(tag in model_name.lower() for tag in STRONG_FC_MODEL_TAGS)
