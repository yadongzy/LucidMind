#!/usr/bin/env python3
"""清洗 SQLite 经验库 — 去噪+去重+有效性重置"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory.store import MemoryStore
from pathlib import Path
import json, re, shutil

DB = Path(__file__).parent.parent / "data" / "memory" / "main.sqlite"

# 备份
BAK = DB.parent / "main.sqlite.bak_20260301"
if not BAK.exists():
    shutil.copy2(DB, BAK)
    print(f"备份: {BAK.name}")

store = MemoryStore(DB)
rows = store.get_all(limit=500)
print(f"总条目: {len(rows)}")

# 分析
noise_ids = []
for r in rows:
    c = (r.content or "").strip()
    # 工具日志
    if c.startswith("[Tool]") or c.startswith("[tool]"):
        noise_ids.append(r.id)
        continue
    # agent 拒绝
    if any(p in c for p in ("我无法访问", "I cannot", "I can't")):
        noise_ids.append(r.id)
        continue
    # 过短
    if len(c) < 10:
        noise_ids.append(r.id)
        continue

print(f"噪音条目: {len(noise_ids)}")

# 去重 (content前60字相同)
seen = {}
dup_ids = []
for r in rows:
    if r.id in noise_ids:
        continue
    key = (r.content or "")[:60]
    if key in seen:
        dup_ids.append(r.id)
    else:
        seen[key] = r.id

print(f"重复条目: {len(dup_ids)}")

# 删除噪音+重复
to_delete = set(noise_ids + dup_ids)
deleted = 0
for rid in to_delete:
    try:
        store.delete(rid)
        deleted += 1
    except Exception as e:
        print(f"  删除失败 {rid}: {e}")

print(f"已删除: {deleted}")

# 有效性重置
reset = 0
remaining = store.get_all(limit=500)
for r in remaining:
    meta = r.metadata or {}
    eff = meta.get("effectiveness")
    applied = meta.get("applied_count", 0)
    if eff == 1.0 and applied == 0:
        meta["effectiveness"] = None
        store.update(r.id, metadata=meta)
        reset += 1

print(f"有效性重置: {reset}条")
print(f"\n=== 结果 ===")
final = store.get_all(limit=500)
print(f"清洗后: {len(final)}条")

# 分类统计
tiers = {}
srcs = {}
for r in final:
    m = r.metadata or {}
    t = m.get("tier", "?")
    s = m.get("source", "?")
    tiers[t] = tiers.get(t, 0) + 1
    srcs[s] = srcs.get(s, 0) + 1
print(f"分层: {tiers}")
print(f"来源: {srcs}")

store.close()
