"""清理任务队列中的旧ready任务，只保留最近5个。"""
import json
from pathlib import Path

queue_file = Path(__file__).parent.parent / "data" / "task_queue.json"
store = json.loads(queue_file.read_text("utf-8"))
tasks = store.get("tasks", [])

ready = [t for t in tasks if t["status"] == "ready"]
completed = [t for t in tasks if t["status"] == "completed"]
other = [t for t in tasks if t["status"] not in ("ready", "completed")]

print(f"Before: {len(tasks)} total, {len(ready)} ready, {len(completed)} completed, {len(other)} other")

# Keep only last 5 ready tasks, mark rest as completed
if len(ready) > 5:
    # Sort by created_at, keep newest 5
    ready.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    keep = ready[:5]
    discard = ready[5:]
    for t in discard:
        t["status"] = "completed"
        t["last_error"] = "auto-expired: queue cleanup"
    print(f"Expired {len(discard)} old ready tasks")
else:
    print("No cleanup needed")

# Also clean completed tasks older than 1 day
from datetime import datetime, timedelta
cutoff = (datetime.now() - timedelta(days=1)).isoformat()
kept_tasks = []
removed = 0
for t in tasks:
    if t["status"] == "completed" and t.get("created_at", "") < cutoff:
        removed += 1
    else:
        kept_tasks.append(t)

store["tasks"] = kept_tasks
json.dump(store, open(str(queue_file), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"Removed {removed} old completed tasks")
print(f"After: {len(kept_tasks)} tasks remaining")
