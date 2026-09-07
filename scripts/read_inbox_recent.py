"""只读取最近的inbox消息（从指定ID开始）。"""
import urllib.request
import json
import sys

start_id = int(sys.argv[1]) if len(sys.argv) > 1 else 35

r = urllib.request.urlopen("http://localhost:8765/api/brain/teaching/inbox")
d = json.loads(r.read())
msgs = d.get("messages", [])
recent = [m for m in msgs if m.get("id", 0) >= start_id]
print(f"=== Inbox: {len(msgs)} total, showing #{start_id}+ ({len(recent)} msgs) ===\n")
for m in recent:
    print(f"#{m['id']} [{m['type']}] urgency={m.get('urgency','?')}")
    print(f"  content: {m['content'][:200]}")
    print(f"  context: {m.get('context','')[:150]}")
    print()
