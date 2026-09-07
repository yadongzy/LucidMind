"""检查大脑状态：队列、思考、inbox新消息。"""
import urllib.request
import json

r = urllib.request.urlopen("http://localhost:8765/api/brain/status")
d = json.loads(r.read())
daemon = d.get("daemon", {})
q = daemon.get("queue", {})

print(f"=== Brain Status ===")
print(f"  awake: {d.get('awake')}")
print(f"  paused: {daemon.get('paused')}")
print(f"  thought_count: {daemon.get('thought_count')}")
print(f"  queue total: {q.get('total')}")
print(f"  queue by_status: {q.get('by_status')}")
print()

thoughts = daemon.get("recent_thoughts", [])
print(f"=== Recent Thoughts ({len(thoughts)}) ===")
for t in thoughts[-3:]:
    print(f"  {t.get('time')}: {t.get('thoughts')}")
print()

teaching = daemon.get("teaching", {})
print(f"=== Teaching ===")
print(f"  inbox_total: {teaching.get('inbox_total')}")
print(f"  inbox_pending: {teaching.get('inbox_pending')}")
print(f"  outbox_total: {teaching.get('outbox_total')}")
print(f"  outbox_unread: {teaching.get('outbox_unread')}")
print(f"  lessons_learned: {teaching.get('lessons_learned')}")
