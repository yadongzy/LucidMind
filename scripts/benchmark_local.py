"""本地模型性能基准测试 — 测试所有可用Ollama模型的响应时间。"""
import json
import urllib.request
import time

OLLAMA_URL = "http://localhost:11434"
MODELS_TO_TEST = []

# 1. 获取可用模型列表
print("=" * 60)
print("本地模型性能基准测试")
print("=" * 60)

try:
    resp = urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5)
    data = json.loads(resp.read())
    MODELS_TO_TEST = [m["name"] for m in data.get("models", [])]
    print(f"\n可用模型: {MODELS_TO_TEST}")
except Exception as e:
    print(f"无法连接Ollama: {e}")
    exit(1)

# 2. 测试每个模型
PROMPT = "用一句话回答：1+1等于几？"
results = []

for model in MODELS_TO_TEST:
    print(f"\n--- 测试模型: {model} ---")
    
    # 简单问答测试
    payload = json.dumps({
        "model": model,
        "prompt": PROMPT,
        "stream": False,
    }).encode("utf-8")
    
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    
    try:
        t0 = time.time()
        resp = urllib.request.urlopen(req, timeout=120)
        t1 = time.time()
        
        result = json.loads(resp.read())
        elapsed = t1 - t0
        response_text = result.get("response", "")[:200]
        total_duration = result.get("total_duration", 0) / 1e9  # 纳秒→秒
        eval_count = result.get("eval_count", 0)
        eval_duration = result.get("eval_duration", 0) / 1e9
        prompt_eval_duration = result.get("prompt_eval_duration", 0) / 1e9
        
        tokens_per_sec = eval_count / eval_duration if eval_duration > 0 else 0
        
        print(f"  响应时间: {elapsed:.1f}s (Ollama报告: {total_duration:.1f}s)")
        print(f"  生成token: {eval_count}个, 速度: {tokens_per_sec:.1f} tokens/s")
        print(f"  prompt处理: {prompt_eval_duration:.1f}s, 生成: {eval_duration:.1f}s")
        print(f"  回复: {response_text[:100]}")
        
        results.append({
            "model": model,
            "elapsed_s": round(elapsed, 1),
            "tokens": eval_count,
            "tokens_per_sec": round(tokens_per_sec, 1),
            "prompt_eval_s": round(prompt_eval_duration, 1),
            "eval_s": round(eval_duration, 1),
        })
    except Exception as e:
        print(f"  失败: {e}")
        results.append({"model": model, "elapsed_s": -1, "error": str(e)[:100]})

# 3. 汇总
print("\n" + "=" * 60)
print("性能汇总")
print("=" * 60)
print(f"{'模型':<25} {'响应时间':>8} {'速度(t/s)':>10} {'生成token':>10}")
print("-" * 55)
for r in sorted(results, key=lambda x: x.get("elapsed_s", 999)):
    if r.get("elapsed_s", -1) > 0:
        print(f"{r['model']:<25} {r['elapsed_s']:>7.1f}s {r.get('tokens_per_sec',0):>9.1f} {r.get('tokens',0):>10}")
    else:
        print(f"{r['model']:<25} {'失败':>8}")

# 4. 推荐
print("\n" + "=" * 60)
print("推荐")
print("=" * 60)
ok = [r for r in results if r.get("elapsed_s", -1) > 0 and r.get("elapsed_s", 999) < 30]
if ok:
    best = min(ok, key=lambda x: x["elapsed_s"])
    print(f"最佳模型: {best['model']} ({best['elapsed_s']}s, {best.get('tokens_per_sec',0)} t/s)")
else:
    print("所有模型响应时间都超过30秒，建议使用更小的模型。")
