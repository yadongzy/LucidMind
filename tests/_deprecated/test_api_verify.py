"""验证 S12/S13/S14 API 模块。"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import requests
import json

BASE = "http://127.0.0.1:8765"
results = {}

# S13-1: 异步任务 API
print("=== S13-1: 异步任务队列 ===")
r = requests.get(f"{BASE}/api/tasks")
ok = r.status_code == 200 and "tasks" in r.json()
print(f"  GET /api/tasks: {r.status_code} -> {r.json()}")
results["S13-1_tasks_api"] = ok

# S13-2: 定时任务 API
print("\n=== S13-2: 定时任务 ===")
r = requests.get(f"{BASE}/api/cron")
ok1 = r.status_code == 200
print(f"  GET /api/cron: {r.status_code}")

r = requests.post(f"{BASE}/api/cron", json={
    "description": "test_job",
    "interval_seconds": 60,
    "command": "hello"
})
ok2 = r.status_code == 200 and "id" in r.json()
job_id = r.json().get("id", "")
print(f"  POST /api/cron: {r.status_code}, id={job_id}")

r = requests.get(f"{BASE}/api/cron")
count = r.json().get("count", 0)
ok3 = count >= 1
print(f"  GET /api/cron: count={count}")

if job_id:
    r = requests.delete(f"{BASE}/api/cron/{job_id}")
    ok4 = r.status_code == 200
    print(f"  DELETE /api/cron/{job_id}: {r.status_code}")
else:
    ok4 = False

results["S13-2_cron_crud"] = ok1 and ok2 and ok3 and ok4

# S12-1: 文件上传 API
print("\n=== S12-1: 文件上传 ===")
r = requests.get(f"{BASE}/api/uploads")
ok = r.status_code == 200
print(f"  GET /api/uploads: {r.status_code}, count={r.json().get('count', 0)}")
results["S12-1_upload_api"] = ok

# 工具注册检查
print("\n=== 工具注册检查 ===")
r = requests.get(f"{BASE}/api/status")
tools = r.json().get("tools", [])
print(f"  已注册工具 ({len(tools)}): {tools}")
results["S12-2_analyze_file"] = "analyze_file" in tools
results["S14-1_document_tools"] = "create_pptx" in tools and "create_excel" in tools
results["S14-2_browser_tool"] = "browse_url" in tools

# 汇总
print("\n" + "=" * 50)
print("API VERIFICATION RESULTS")
print("=" * 50)
all_ok = True
for name, ok in results.items():
    status = "PASS" if ok else "FAIL"
    if not ok:
        all_ok = False
    print(f"  {name}: {status}")

print(f"\nTotal: {len(results)} | Passed: {sum(results.values())} | Failed: {sum(1 for v in results.values() if not v)}")
