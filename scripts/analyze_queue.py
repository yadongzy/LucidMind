"""深度分析任务队列积压的根本原因。"""
import json
from pathlib import Path
from collections import Counter
from datetime import datetime

queue_file = Path(__file__).parent.parent / "data" / "task_queue.json"
store = json.loads(queue_file.read_text("utf-8"))
tasks = store.get("tasks", [])

print(f"=== 队列深度分析 ===\n")
print(f"总任务数: {len(tasks)}")

# 1. 按状态分布
status_counts = Counter(t["status"] for t in tasks)
print(f"\n--- 状态分布 ---")
for s, c in status_counts.most_common():
    print(f"  {s}: {c}")

# 2. 按来源分布
source_counts = Counter(t.get("source", "?") for t in tasks)
print(f"\n--- 来源分布 ---")
for s, c in source_counts.most_common():
    print(f"  {s}: {c}")

# 3. 按来源+状态交叉分析
print(f"\n--- 来源×状态 ---")
cross = Counter((t.get("source", "?"), t["status"]) for t in tasks)
for (src, st), c in cross.most_common():
    print(f"  {src}/{st}: {c}")

# 4. ready任务的来源分布
ready = [t for t in tasks if t["status"] == "ready"]
print(f"\n--- Ready任务来源 ({len(ready)}个) ---")
ready_src = Counter(t.get("source", "?") for t in ready)
for s, c in ready_src.most_common():
    print(f"  {s}: {c}")

# 5. 入队速率分析
print(f"\n--- 入队时间分析 ---")
if tasks:
    times = []
    for t in tasks:
        try:
            times.append(datetime.fromisoformat(t["created_at"]))
        except: pass
    if len(times) >= 2:
        times.sort()
        span = (times[-1] - times[0]).total_seconds()
        rate = len(times) / (span / 60) if span > 0 else 0
        print(f"  时间跨度: {span/60:.1f}分钟")
        print(f"  入队速率: {rate:.1f}个/分钟")
        print(f"  最早: {times[0].strftime('%H:%M:%S')}")
        print(f"  最晚: {times[-1].strftime('%H:%M:%S')}")

# 6. 出队速率分析（completed任务）
completed = [t for t in tasks if t["status"] == "completed"]
print(f"\n--- 出队(完成)速率 ---")
if completed:
    comp_times = []
    for t in completed:
        try:
            if t.get("completed_at"):
                comp_times.append(datetime.fromisoformat(t["completed_at"]))
        except: pass
    if len(comp_times) >= 2:
        comp_times.sort()
        span = (comp_times[-1] - comp_times[0]).total_seconds()
        rate = len(comp_times) / (span / 60) if span > 0 else 0
        print(f"  完成数: {len(comp_times)}")
        print(f"  时间跨度: {span/60:.1f}分钟")
        print(f"  完成速率: {rate:.1f}个/分钟")

# 7. 每个任务的执行耗时
print(f"\n--- 任务执行耗时 ---")
durations = []
for t in completed:
    try:
        if t.get("running_at") and t.get("completed_at"):
            start = datetime.fromisoformat(t["running_at"])
            end = datetime.fromisoformat(t["completed_at"])
            dur = (end - start).total_seconds()
            durations.append(dur)
    except: pass
if durations:
    print(f"  样本数: {len(durations)}")
    print(f"  平均耗时: {sum(durations)/len(durations):.1f}s")
    print(f"  最短: {min(durations):.1f}s")
    print(f"  最长: {max(durations):.1f}s")
    print(f"  中位数: {sorted(durations)[len(durations)//2]:.1f}s")
else:
    print("  无完整耗时数据")

# 8. 关键问题：入队 vs 出队速率对比
print(f"\n=== 根因分析 ===")
print(f"  active(ready+running+blocked): {sum(1 for t in tasks if t['status'] in ('ready','running','blocked'))}")
print(f"  completed: {status_counts.get('completed', 0)}")
print(f"  escalated: {status_counts.get('escalated', 0)}")

# 9. 老师消息入队的详细分析
teacher_tasks = [t for t in tasks if t.get("source") == "teacher"]
print(f"\n--- 老师消息任务 ({len(teacher_tasks)}个) ---")
teacher_ready = [t for t in teacher_tasks if t["status"] == "ready"]
teacher_completed = [t for t in teacher_tasks if t["status"] == "completed"]
print(f"  ready: {len(teacher_ready)}")
print(f"  completed: {len(teacher_completed)}")
# 看看老师消息的内容重复度
teacher_contents = [t["content"][:100] for t in teacher_tasks]
unique = len(set(teacher_contents))
print(f"  内容去重: {unique}/{len(teacher_contents)} 唯一")

# 10. 查看ready任务的内容（前10个）
print(f"\n--- Ready任务内容(前10) ---")
for t in ready[:10]:
    age = ""
    try:
        created = datetime.fromisoformat(t["created_at"])
        age = f" ({(datetime.now()-created).total_seconds()/60:.0f}min ago)"
    except: pass
    print(f"  [{t.get('source','?')}/{t.get('priority','?')}]{age}: {t['content'][:80]}")
