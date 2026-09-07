"""检查经验库状态。"""
import json
from pathlib import Path

lessons = json.loads((Path(__file__).parent.parent / "data" / "lessons.json").read_text(encoding="utf-8"))
print(f"Total lessons: {len(lessons)}")
print(f"\nLast 5 lessons:")
for l in lessons[-5:]:
    print(f"  trigger: {l.get('trigger','')[:80]}")
    print(f"  lesson: {l.get('lesson','')[:80]}")
    print(f"  effectiveness: {l.get('effectiveness', 'N/A')}")
    print()
