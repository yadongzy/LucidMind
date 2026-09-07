"""检查 outbox 消息的 read_by_brain 状态。"""
import json
from pathlib import Path

outbox = json.loads((Path(__file__).parent.parent / "data" / "teacher_outbox.json").read_text(encoding="utf-8"))
print(f"Outbox: {len(outbox)} messages\n")
for m in outbox:
    print(f"  #{m['id']} reply_to={m.get('reply_to',0)} read={m.get('read_by_brain',False)} status={m.get('status','?')}")
    print(f"    answer: {m.get('answer','')[:80]}")
    print()
