"""Growth Stage — 大脑的成长阶段系统。

不同阶段，大脑对老师的依赖和学习方法不同：

阶段1 (infant):  经验<20  → 高度依赖老师，频繁求助，老师主导教学
阶段2 (child):   经验20-80 → 开始自主探索，老师引导为主，鼓励自己尝试
阶段3 (teen):    经验80-200 → 自主学习为主，老师只在关键时刻介入
阶段4 (adult):   经验>200  → 完全自主，老师变为顾问角色，大脑可以教别人

阶段判定基于纯事实（经验数量、成功率、自检通过率），
不硬编码行为指令（规则03）。

不修改 brain.py（规则 06），作为独立模块被 Daemon 和工具调用。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("teaching")

_DATA_DIR = Path(__file__).parent / "data"
_STAGE_FILE = _DATA_DIR / "growth_stage.json"


def _load_stage() -> dict:
    if _STAGE_FILE.exists():
        try:
            return json.loads(_STAGE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "stage": "infant",
        "stage_num": 1,
        "history": [],
        "last_check": "",
    }


def _save_stage(data: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _STAGE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# 阶段定义 — 纯事实阈值，不含行为指令
STAGES = {
    1: {"name": "infant",  "label": "婴儿期", "min_lessons": 0,   "teacher_freq": 1},
    2: {"name": "child",   "label": "幼儿期", "min_lessons": 20,  "teacher_freq": 3},
    3: {"name": "teen",    "label": "少年期", "min_lessons": 80,  "teacher_freq": 6},
    4: {"name": "adult",   "label": "成年期", "min_lessons": 200, "teacher_freq": 12},
}


def evaluate_stage(lesson_count: int, success_rate: float = 0.0) -> dict:
    """根据纯事实评估当前成长阶段。

    Args:
        lesson_count: 经验库中的经验总数
        success_rate: 最近的成功率 (0.0-1.0)，可选

    Returns:
        {"stage_num": 1-4, "name": ..., "label": ..., "teacher_freq": ...}
    """
    current = STAGES[1]
    for num in sorted(STAGES.keys(), reverse=True):
        if lesson_count >= STAGES[num]["min_lessons"]:
            current = STAGES[num]
            current["stage_num"] = num
            break
    return current


async def check_and_update(learning_adapter) -> dict:
    """检查并更新成长阶段。

    由 Daemon 定期调用。阶段变化时记录到历史。
    """
    data = _load_stage()
    old_stage = data.get("stage_num", 1)

    # 获取经验数量
    lesson_count = 0
    if learning_adapter:
        try:
            lessons = await learning_adapter.get_lessons("", limit=500)
            lesson_count = len(lessons)
        except Exception:
            pass

    new = evaluate_stage(lesson_count)
    new_stage = new["stage_num"]

    data["stage"] = new["name"]
    data["stage_num"] = new_stage
    data["lesson_count"] = lesson_count
    data["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 阶段变化 → 记录里程碑
    if new_stage != old_stage:
        event = {
            "time": data["last_check"],
            "from": STAGES[old_stage]["label"],
            "to": new["label"],
            "lesson_count": lesson_count,
        }
        data.setdefault("history", []).append(event)
        logger.info(f"🌱 成长阶段变化: {event['from']} → {event['to']} (经验{lesson_count}条)")

    _save_stage(data)
    return data


def get_current_stage() -> dict:
    """获取当前成长阶段（不触发重新评估）。"""
    return _load_stage()


def get_teacher_ask_frequency() -> int:
    """获取当前阶段的老师提问频率（每N个Daemon周期提问一次）。

    婴儿期: 每1个周期 → 频繁求助
    幼儿期: 每3个周期 → 开始自主
    少年期: 每6个周期 → 主要自学
    成年期: 每12个周期 → 偶尔请教
    """
    data = _load_stage()
    stage_num = data.get("stage_num", 1)
    return STAGES.get(stage_num, STAGES[1])["teacher_freq"]


def get_stage_context() -> str:
    """生成阶段上下文，注入到大脑的自我感知中。

    只提供事实信息，不提供行为指令（规则03）。
    """
    data = _load_stage()
    stage_num = data.get("stage_num", 1)
    stage_info = STAGES.get(stage_num, STAGES[1])
    lesson_count = data.get("lesson_count", 0)

    # 纯事实描述
    ctx = f"成长阶段: {stage_info['label']} (经验{lesson_count}条)"

    # 下一阶段的事实
    next_num = stage_num + 1
    if next_num in STAGES:
        needed = STAGES[next_num]["min_lessons"] - lesson_count
        if needed > 0:
            ctx += f", 距下一阶段还需{needed}条经验"

    # 历史里程碑
    history = data.get("history", [])
    if history:
        latest = history[-1]
        ctx += f", 上次成长: {latest.get('time', '?')}"

    return ctx
