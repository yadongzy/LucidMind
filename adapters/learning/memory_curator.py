"""经验管理器 — 基于论文 arXiv:2505.16067 的选择性删除策略。

核心发现（实证数据）：
1. 存储所有经验会导致性能持续下降（错误传播）
2. 选择性删除比选择性添加更重要
3. 组合删除（周期性+历史性）：准确率+4%，内存-75%

三种删除策略：
- 周期性删除: 定期清理过期+低效经验
- 历史性删除: 追踪检索效果，删除"错位经验"(misaligned experience replay)
- 组合删除: 两者同时运行（本模块采用）

经验分层（借鉴 OpenClaw temporal-decay.ts 的 evergreen 概念）：
- strategy: 策略级（方法论/平台规则）— 永不衰减
- fact: 事实级（任务成功/失败记录）— 正常衰减
- temp: 临时级（一次性上下文）— 快速衰减

独立模块，不修改 brain.py（规则06）。
"""

import time
import math
from datetime import datetime, timezone
from typing import Any

from logs import get_logger

logger = get_logger("curator")

# === 配置 ===

PERIODIC_INTERVAL_HOURS = 24
EFFECTIVENESS_THRESHOLD = 0.3
MAX_AGE_DAYS_TEMP = 7
MAX_AGE_DAYS_FACT = 90
MISALIGNED_STRIKE_LIMIT = 3
MIN_LESSONS_KEEP = 30
TARGET_LESSONS = 80

# === 经验分层 ===

_STRATEGY_KEYWORDS = frozenset([
    "方法论", "五步法", "原则", "策略", "规则", "铁律", "禁止",
    "windows", "linux", "平台", "python3", "python",
    "methodology", "principle", "strategy", "rule",
])

_TEMP_KEYWORDS = frozenset([
    "一次性", "临时", "当前", "刚才", "今天",
    "temporary", "current", "just now",
])


def classify_tier(lesson: dict[str, Any]) -> str:
    """自动分类经验层级。已有tier字段则保留。"""
    if lesson.get("tier"):
        return lesson["tier"]
    text = f"{lesson.get('trigger', '')} {lesson.get('lesson', '')}".lower()
    source = lesson.get("source", "")
    if source in ("teaching", "correction"):
        return "strategy"
    if any(kw in text for kw in _STRATEGY_KEYWORDS):
        return "strategy"
    if source in ("task_success",) or any(kw in text for kw in _TEMP_KEYWORDS):
        return "temp"
    return "fact"


def get_half_life_days(tier: str) -> float:
    """根据层级返回衰减半衰期。"""
    return {"strategy": 999999.0, "fact": 60.0, "temp": 7.0}.get(tier, 60.0)


# === 选择性添加：质量门控 ===

def should_add_lesson(lesson: dict[str, Any], existing: list[dict[str, Any]]) -> bool:
    """选择性添加门控。论文发现 add-all 比不添加更差。

    拒绝条件：
    1. 内容过短（无信息量）
    2. 与现有经验高度重复
    3. 纯"任务成功"记录但无具体方法
    """
    trigger = lesson.get("trigger", "")
    content = lesson.get("lesson", "")
    if len(trigger) < 5 or len(content) < 10:
        logger.debug(f"门控拒绝: 内容过短 trigger={len(trigger)} lesson={len(content)}")
        return False
    if "方法有效，可复用" in content and len(content) < 50:
        logger.debug(f"门控拒绝: 空洞的成功记录")
        return False
    # 检查重复：与现有经验的trigger相似度
    trigger_lower = trigger.lower()
    for ex in existing:
        ex_trigger = ex.get("trigger", "").lower()
        if ex_trigger and trigger_lower and _text_overlap(trigger_lower, ex_trigger) > 0.8:
            logger.debug(f"门控拒绝: 与现有经验重复 (overlap>0.8)")
            return False
    return True


def _text_overlap(a: str, b: str) -> float:
    """简单文本重叠度（字符级Jaccard）。"""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# === 周期性删除 ===

def periodic_cleanup(lessons: list[dict[str, Any]], now: float | None = None) -> list[dict[str, Any]]:
    """周期性删除：清理过期+低效经验。

    删除条件（AND）：
    - effectiveness < EFFECTIVENESS_THRESHOLD (0.3)
    - 超过层级对应的最大存活天数
    - 不是 strategy 层级
    """
    now = now or time.time()
    keep, removed = [], []
    for lesson in lessons:
        tier = classify_tier(lesson)
        lesson["tier"] = tier
        if tier == "strategy":
            keep.append(lesson)
            continue
        eff = lesson.get("effectiveness")
        age_days = _age_days(lesson, now)
        max_age = MAX_AGE_DAYS_TEMP if tier == "temp" else MAX_AGE_DAYS_FACT
        if eff is not None and eff < EFFECTIVENESS_THRESHOLD and age_days > max_age:
            removed.append(lesson)
        elif tier == "temp" and age_days > MAX_AGE_DAYS_TEMP * 2:
            removed.append(lesson)
        else:
            keep.append(lesson)
    if removed:
        logger.info(f"周期性删除: 移除 {len(removed)} 条低效/过期经验")
        for r in removed:
            logger.debug(f"  删除: {r.get('id')} tier={r.get('tier')} eff={r.get('effectiveness')} trigger={r.get('trigger','')[:40]}")
    return keep


# === 历史性删除（Misaligned Experience Replay） ===

def track_retrieval_outcome(lesson: dict[str, Any], was_helpful: bool) -> None:
    """追踪经验被检索后的效果。连续N次无效→标记为misaligned。

    论文发现：输入相似度高但输出相似度低的经验最有害。
    这类经验"看起来相关但实际误导"。
    """
    strikes = lesson.get("_misaligned_strikes", 0)
    if was_helpful:
        lesson["_misaligned_strikes"] = max(0, strikes - 1)
    else:
        lesson["_misaligned_strikes"] = strikes + 1
    lesson["_last_retrieved"] = time.time()


def history_cleanup(lessons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """历史性删除：移除被标记为 misaligned 的经验。"""
    keep, removed = [], []
    for lesson in lessons:
        strikes = lesson.get("_misaligned_strikes", 0)
        tier = lesson.get("tier") or classify_tier(lesson)
        if tier != "strategy" and strikes >= MISALIGNED_STRIKE_LIMIT:
            removed.append(lesson)
        else:
            keep.append(lesson)
    if removed:
        logger.info(f"历史性删除: 移除 {len(removed)} 条错位经验(misaligned)")
        for r in removed:
            logger.debug(f"  删除: {r.get('id')} strikes={r.get('_misaligned_strikes')} trigger={r.get('trigger','')[:40]}")
    return keep


# === 组合删除（主入口） ===

def curate(lessons: list[dict[str, Any]], now: float | None = None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """组合删除：周期性 + 历史性。返回 (清理后的经验列表, 统计信息)。

    论文数据：组合删除准确率+4%，内存-75%。
    """
    original_count = len(lessons)
    # 1. 分层标注
    for lesson in lessons:
        lesson["tier"] = classify_tier(lesson)
    # 2. 周期性删除
    lessons = periodic_cleanup(lessons, now)
    # 3. 历史性删除
    lessons = history_cleanup(lessons)
    # 4. 保底：至少保留 MIN_LESSONS_KEEP 条
    if len(lessons) < MIN_LESSONS_KEEP:
        logger.warning(f"经验库过小({len(lessons)}条)，跳过进一步清理")
    # 5. 如果仍然超过目标，按质量排序淘汰
    elif len(lessons) > TARGET_LESSONS:
        lessons.sort(key=lambda x: _quality_score(x), reverse=True)
        overflow = lessons[TARGET_LESSONS:]
        lessons = lessons[:TARGET_LESSONS]
        if overflow:
            logger.info(f"质量淘汰: 移除 {len(overflow)} 条最低质量经验")
    removed_count = original_count - len(lessons)
    stats = {
        "original": original_count,
        "remaining": len(lessons),
        "removed": removed_count,
        "strategy": sum(1 for l in lessons if l.get("tier") == "strategy"),
        "fact": sum(1 for l in lessons if l.get("tier") == "fact"),
        "temp": sum(1 for l in lessons if l.get("tier") == "temp"),
    }
    if removed_count > 0:
        logger.info(f"经验管理完成: {original_count}→{len(lessons)} (删除{removed_count}条) "
                     f"[strategy={stats['strategy']}, fact={stats['fact']}, temp={stats['temp']}]")
    return lessons, stats


def _quality_score(lesson: dict[str, Any]) -> float:
    """综合质量评分：有效性 × 时间衰减 × 层级权重。"""
    eff = lesson.get("effectiveness")
    if eff is None:
        eff = 0.4  # 未验证的默认分数（略低于中等）
    tier = lesson.get("tier", "fact")
    tier_weight = {"strategy": 2.0, "fact": 1.0, "temp": 0.5}.get(tier, 1.0)
    half_life = get_half_life_days(tier)
    age = _age_days(lesson, time.time())
    if half_life > 0 and half_life < 100000:
        decay = math.exp(-math.log(2) / half_life * age)
    else:
        decay = 1.0
    applied = lesson.get("applied_count", 0)
    usage_bonus = min(applied * 0.05, 0.3)
    return (eff + usage_bonus) * decay * tier_weight


def _age_days(lesson: dict[str, Any], now: float) -> float:
    """计算经验的年龄（天）。"""
    ts = lesson.get("created_at", "")
    if isinstance(ts, str) and ts:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return max(0, (now - dt.timestamp())) / 86400
        except (ValueError, TypeError):
            pass
    return 0.0
