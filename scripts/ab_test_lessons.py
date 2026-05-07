"""A/B测试脚本 — 对比经验注入开/关的回答质量。

用法: python scripts/ab_test_lessons.py
要求: 服务器已在 :8765 运行
"""

import requests
import time

BASE = "http://127.0.0.1:8765"

# 测试问题集：覆盖不同场景
TEST_QUESTIONS = [
    "帮我查看当前磁盘使用情况",
    "帮我删除/tmp下超过30天的文件",
    "用Python写一个简单的HTTP服务器",
    "当前时间是几点？",
    "帮我看看这个项目有多少个Python文件",
]


def run_test(label: str, lessons_enabled: bool) -> list[dict]:
    """用指定模式跑全部测试问题。"""
    # 设置模式
    r = requests.put(f"{BASE}/api/ab-test", json={"lessons_enabled": lessons_enabled, "reset": False})
    mode = r.json()
    print(f"\n{'='*60}")
    print(f"模式: {label} (lessons_enabled={mode['lessons_enabled']})")
    print(f"{'='*60}")

    results = []
    for i, q in enumerate(TEST_QUESTIONS, 1):
        print(f"\n  [{i}/{len(TEST_QUESTIONS)}] {q}")
        t0 = time.time()
        try:
            resp = requests.post(f"{BASE}/api/teacher/direct", json={
                "message": q,
                "session_id": f"ab_test_{label}_{i}",
            }, timeout=120)
            data = resp.json()
            elapsed = time.time() - t0
            response = data.get("response", "")
            results.append({
                "question": q,
                "response_len": len(response),
                "elapsed": round(elapsed, 2),
                "response_preview": response[:100],
            })
            print(f"    回复: {response[:80]}...")
            print(f"    耗时: {elapsed:.1f}s | 字数: {len(response)}")
        except Exception as e:
            print(f"    ❌ 错误: {e}")
            results.append({"question": q, "error": str(e)})
    return results


def main():
    print("🧪 LucidMind 经验系统 A/B 测试")
    print(f"测试问题: {len(TEST_QUESTIONS)} 个")

    # 重置统计
    requests.put(f"{BASE}/api/ab-test", json={"reset": True})

    # A组：有经验注入
    results_with = run_test("WITH", lessons_enabled=True)

    # B组：无经验注入
    results_without = run_test("WITHOUT", lessons_enabled=False)

    # 恢复为开启状态
    requests.put(f"{BASE}/api/ab-test", json={"lessons_enabled": True})

    # 获取服务端统计
    ab_stats = requests.get(f"{BASE}/api/ab-test").json()

    # 汇总
    print(f"\n{'='*60}")
    print("📊 A/B 测试结果汇总")
    print(f"{'='*60}")

    w = ab_stats.get("with_lessons", {})
    wo = ab_stats.get("without_lessons", {})

    headers = f"{'指标':<20} {'有经验':>12} {'无经验':>12} {'差异':>10}"
    print(headers)
    print("-" * 56)

    def _row(name, v1, v2, unit=""):
        diff = v1 - v2 if v1 and v2 else 0
        sign = "+" if diff > 0 else ""
        print(f"{name:<20} {v1:>10}{unit}  {v2:>10}{unit}  {sign}{diff:.1f}{unit}")

    _row("样本数", w.get("count", 0), wo.get("count", 0))
    _row("平均耗时", w.get("avg_elapsed", 0), wo.get("avg_elapsed", 0), "s")
    _row("平均tokens", w.get("avg_tokens", 0), wo.get("avg_tokens", 0))
    _row("平均回复长度", w.get("avg_response_len", 0), wo.get("avg_response_len", 0))

    # 逐题对比
    print("\n📝 逐题对比:")
    for i, (rw, rwo) in enumerate(zip(results_with, results_without)):
        q = rw["question"]
        ew = rw.get("elapsed", 0)
        ewo = rwo.get("elapsed", 0)
        lw = rw.get("response_len", 0)
        lwo = rwo.get("response_len", 0)
        faster = "← 更快" if ew < ewo else ("→ 更快" if ewo < ew else "")
        print(f"  Q{i+1}: {q[:30]}")
        print(f"    有经验: {ew:.1f}s, {lw}字  |  无经验: {ewo:.1f}s, {lwo}字  {faster}")

    print("\n✅ 测试完成。经验注入已恢复为开启状态。")


if __name__ == "__main__":
    main()
