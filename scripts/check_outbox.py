"""检查 outbox 和 inbox 状态。"""
import json
from pathlib import Path

data_dir = Path(__file__).parent.parent / "data"

outbox = json.loads((data_dir / "teacher_outbox.json").read_text(encoding="utf-8"))
inbox = json.loads((data_dir / "teacher_inbox.json").read_text(encoding="utf-8"))

print(f"=== Outbox: {len(outbox)} msgs ===")
for m in outbox[-3:]:
    print(f"  #{m.get('id')} answer: {m.get('answer','')[:120]}")

print(f"\n=== Inbox: {len(inbox)} msgs ===")
for m in inbox[-3:]:
    print(f"  #{m.get('id')} [{m.get('type')}] content: {m.get('content','')[:120]}")
