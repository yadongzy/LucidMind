"""验证 _is_temporal 时效性判断逻辑。"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")
from adapters.learning.special_kb import _is_temporal

# 动态问题 — 应该返回 True（不缓存）
dynamic = [
    ("今天天气怎么样？", "今天北京气温25℃，晴天"),
    ("现在比特币价格多少？", "截至目前，比特币价格约$67,000"),
    ("最新的新闻有哪些？", "据最新报道，今天发生了..."),
    ("今天股票涨了吗？", "上证指数今日收盘3200点"),
    ("current weather in Tokyo", "As of now, Tokyo is 18°C"),
    ("最近有什么热搜？", "目前微博热搜第一是..."),
]

# 静态问题 — 应该返回 False（可缓存）
static = [
    ("Python和Java的区别是什么？", "Python是动态类型语言，Java是静态类型语言..."),
    ("什么是递归？", "递归是函数调用自身的编程技术..."),
    ("如何使用FastAPI创建REST API？", "首先安装FastAPI: pip install fastapi..."),
    ("explain the difference between TCP and UDP", "TCP is connection-oriented..."),
    ("怎么做红烧肉？", "准备五花肉500克，先焯水去腥..."),
    ("Git rebase和merge的区别", "rebase会重写提交历史，merge会创建合并提交..."),
    # 关键：长文本中偶然提到"最新新闻"但核心意图是架构讨论
    ("我有一个架构问题：外部大模型费token，本地大模型慢。方案是缓存优质回答。但动态问题如今天天气、最新新闻不能缓存。请分析优缺点和改进建议。",
     "这个方案的优点是节省token，缺点是需要判断时效性..."),
    # 讨论"如何判断"而非"查询实时数据"
    ("如何设计一个系统来判断问题是否具有时效性？比如今天天气vs什么是递归",
     "可以从问题语义和回答内容两个维度分析..."),
]

print("=== DYNAMIC (should be True = no cache) ===")
ok = 0
for q, a in dynamic:
    r = _is_temporal(q, a)
    status = "OK" if r else "FAIL"
    if r:
        ok += 1
    print(f"  [{status}] {q[:45]} -> temporal={r}")

print(f"\n=== STATIC (should be False = cacheable) ===")
for q, a in static:
    r = _is_temporal(q, a)
    status = "OK" if not r else "FAIL"
    if not r:
        ok += 1
    print(f"  [{status}] {q[:45]} -> temporal={r}")

total = len(dynamic) + len(static)
print(f"\nResult: {ok}/{total} correct")
