#!/usr/bin/env python3
"""经验库深度清洗 v2 — 去噪+去重+补trigger+有效性重置"""
import json
import shutil
from pathlib import Path
from collections import defaultdict

F = Path(__file__).parent.parent / "data" / "lessons.json"
lessons = json.loads(F.read_text("utf-8"))
orig = len(lessons)
print(f"原始: {orig}条")

# 备份
shutil.copy2(F, F.parent / "lessons_backup_20260301.json")
print("备份: lessons_backup_20260301.json")

# 1. 去噪
clean = []
n_noise = 0
for l in lessons:
    c = (l.get("lesson", "") or "").strip()
    if c.startswith("[Tool]") or c.startswith("[tool]"):
        n_noise += 1; continue
    if any(p in c for p in ("我无法访问", "I cannot", "I can't")):
        n_noise += 1; continue
    if len(c) < 10:
        n_noise += 1; continue
    clean.append(l)
print(f"去噪: 删除{n_noise}条")

# 2. 去重 (lesson前60字相同只保留最新)
seen = {}
deduped = []
n_dup = 0
for l in reversed(clean):
    key = (l.get("lesson", "") or "")[:60]
    if key in seen:
        n_dup += 1; continue
    seen[key] = True
    deduped.append(l)
deduped.reverse()
print(f"去重: 删除{n_dup}条")

# 3. 补trigger
n_fix = 0
for l in deduped:
    if not (l.get("trigger", "") or "").strip():
        text = l.get("lesson", "")
        line1 = text.split("\n")[0][:80]
        if "触发:" in line1:
            l["trigger"] = line1.split("触发:")[1].strip()[:60]
            n_fix += 1
        elif len(line1) > 10:
            l["trigger"] = line1[:60]
            n_fix += 1
print(f"补trigger: {n_fix}条")

# 4. 有效性重置 (未被应用过的不应为1.00)
n_eff = 0
for l in deduped:
    if l.get("effectiveness") == 1.0 and l.get("applied_count", 0) == 0:
        l["effectiveness"] = None
        n_eff += 1
print(f"有效性重置: {n_eff}条")

# 保存
with open(F, "w", encoding="utf-8") as f:
    json.dump(deduped, f, ensure_ascii=False, indent=2)

# 统计
tiers = defaultdict(int)
srcs = defaultdict(int)
for l in deduped:
    tiers[l.get("tier", "?")] += 1
    srcs[l.get("source", "?")] += 1

print("\n=== 结果 ===")
print(f"原始: {orig} → 清洗后: {len(deduped)}")
print(f"删除: {orig - len(deduped)} (噪音{n_noise} + 重复{n_dup})")
print(f"分层: {dict(tiers)}")
print(f"来源: {dict(srcs)}")
