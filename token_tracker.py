"""Token Tracker — 实时 token 使用量追踪 + 阈值自动切换。

记录每次 LLM 调用的 token 消耗，提供统计 API，
支持设置 token 预算上限和剩余阈值自动切换模型。
"""

import time
import json
import threading
from pathlib import Path
from dataclasses import dataclass, asdict
from collections import defaultdict
from logs import get_logger

logger = get_logger("token_tracker")

_DATA_PATH = Path(__file__).parent / "data" / "token_usage.json"
_CONFIG_PATH = Path(__file__).parent / "data" / "token_config.json"


@dataclass
class TokenRecord:
    """单次 LLM 调用记录。"""
    timestamp: float
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    session_id: str = ""
    source: str = ""  # chat / daemon / task / metacog / learning


@dataclass
class ModelStats:
    """单个模型的累计统计。"""
    total_prompt: int = 0
    total_completion: int = 0
    total_tokens: int = 0
    call_count: int = 0
    avg_prompt: float = 0.0
    avg_completion: float = 0.0
    first_call: float = 0.0
    last_call: float = 0.0


@dataclass
class TokenConfig:
    """Token 预算配置。"""
    budget_enabled: bool = False
    max_tokens_per_day: int = 500_000
    max_tokens_per_hour: int = 100_000
    warn_threshold_pct: float = 80.0  # 使用 80% 时警告
    auto_switch_threshold_pct: float = 95.0  # 使用 95% 时自动切换
    auto_switch_target: str = ""  # 自动切换目标 provider/model
    pause_at_limit: bool = False  # 到达上限时暂停而非切换


class TokenTracker:
    """全局 token 使用量追踪器。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._records: list[TokenRecord] = []
        self._model_stats: dict[str, ModelStats] = defaultdict(ModelStats)
        self._hourly: dict[str, int] = defaultdict(int)  # "YYYY-MM-DD-HH" → tokens
        self._daily: dict[str, int] = defaultdict(int)   # "YYYY-MM-DD" → tokens
        self._session_total: int = 0  # 本次启动以来的总 token
        self._config = TokenConfig()
        self._start_time = time.time()
        self._callbacks: list = []  # threshold callbacks
        self._load_config()
        self._load_history()

    def _load_config(self):
        """加载 token 配置。"""
        if _CONFIG_PATH.exists():
            try:
                with open(_CONFIG_PATH, encoding="utf-8") as f:
                    d = json.load(f)
                self._config = TokenConfig(**{k: v for k, v in d.items() if hasattr(self._config, k)})
                logger.info(f"Token 配置已加载: budget={self._config.max_tokens_per_day}/day")
            except Exception as e:
                logger.warning(f"Token 配置加载失败: {e}")

    def save_config(self, config_dict: dict):
        """保存 token 配置。"""
        for k, v in config_dict.items():
            if hasattr(self._config, k):
                setattr(self._config, k, v)
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self._config), f, ensure_ascii=False, indent=2)
        logger.info("Token 配置已保存")

    def _load_history(self):
        """加载历史 token 使用数据。"""
        if _DATA_PATH.exists():
            try:
                with open(_DATA_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                self._daily = defaultdict(int, data.get("daily", {}))
                self._hourly = defaultdict(int, data.get("hourly", {}))
                for model, stats in data.get("model_stats", {}).items():
                    self._model_stats[model] = ModelStats(**stats)
                self._session_total = data.get("session_total", 0)
                logger.info(f"Token 历史已加载: {sum(self._daily.values())} total tokens")
            except Exception as e:
                logger.warning(f"Token 历史加载失败: {e}")

    def _save_history(self):
        """保存 token 使用数据（每 50 次调用保存一次）。"""
        _DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "daily": dict(self._daily),
            "hourly": dict(self._hourly),
            "model_stats": {k: asdict(v) for k, v in self._model_stats.items()},
            "session_total": self._session_total,
            "last_save": time.time(),
        }
        with open(_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def record(self, model: str, provider: str, prompt_tokens: int,
               completion_tokens: int, total_tokens: int,
               session_id: str = "", source: str = ""):
        """记录一次 LLM 调用的 token 使用量。"""
        now = time.time()
        total = total_tokens or (prompt_tokens + completion_tokens)

        with self._lock:
            # 累计统计
            stats = self._model_stats[model]
            stats.total_prompt += prompt_tokens
            stats.total_completion += completion_tokens
            stats.total_tokens += total
            stats.call_count += 1
            stats.avg_prompt = stats.total_prompt / stats.call_count
            stats.avg_completion = stats.total_completion / stats.call_count
            if not stats.first_call:
                stats.first_call = now
            stats.last_call = now

            # 时间维度统计
            from datetime import datetime
            dt = datetime.fromtimestamp(now)
            day_key = dt.strftime("%Y-%m-%d")
            hour_key = dt.strftime("%Y-%m-%d-%H")
            self._daily[day_key] += total
            self._hourly[hour_key] += total
            self._session_total += total

            # 保留最近记录（内存中最多 500 条）
            rec = TokenRecord(
                timestamp=now, model=model, provider=provider,
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                total_tokens=total, session_id=session_id, source=source,
            )
            self._records.append(rec)
            if len(self._records) > 500:
                self._records = self._records[-300:]

            # 定期保存
            if stats.call_count % 50 == 0:
                self._save_history()

        # 阈值检查（异步，不阻塞调用）
        self._check_thresholds(day_key, total)

    def _check_thresholds(self, day_key: str, added_tokens: int):
        """检查是否超过 token 预算阈值。"""
        if not self._config.budget_enabled:
            return
        daily_used = self._daily.get(day_key, 0)
        budget = self._config.max_tokens_per_day
        if budget <= 0:
            return
        pct = (daily_used / budget) * 100

        if pct >= self._config.auto_switch_threshold_pct:
            logger.warning(f"🚨 Token 预算已用 {pct:.1f}%! ({daily_used:,}/{budget:,})")
            for cb in self._callbacks:
                try:
                    cb("auto_switch", pct, daily_used, budget)
                except Exception:
                    pass
        elif pct >= self._config.warn_threshold_pct:
            logger.warning(f"⚠️ Token 预算已用 {pct:.1f}% ({daily_used:,}/{budget:,})")

    def on_threshold(self, callback):
        """注册阈值触发回调。callback(event, pct, used, budget)"""
        self._callbacks.append(callback)

    def get_stats(self) -> dict:
        """获取完整的 token 使用统计。"""
        from datetime import datetime
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        this_hour = now.strftime("%Y-%m-%d-%H")

        with self._lock:
            # 今日统计
            today_tokens = self._daily.get(today, 0)
            this_hour_tokens = self._hourly.get(this_hour, 0)

            # 最近 24 小时趋势（每小时）
            hourly_trend = []
            for h in range(24):
                from datetime import timedelta
                dt = now - timedelta(hours=23 - h)
                key = dt.strftime("%Y-%m-%d-%H")
                hourly_trend.append({
                    "hour": dt.strftime("%H:00"),
                    "tokens": self._hourly.get(key, 0),
                })

            # 最近 7 天趋势
            daily_trend = []
            for d in range(7):
                from datetime import timedelta
                dt = now - timedelta(days=6 - d)
                key = dt.strftime("%Y-%m-%d")
                daily_trend.append({
                    "date": key,
                    "tokens": self._daily.get(key, 0),
                })

            # 模型分布
            model_breakdown = []
            for model, stats in sorted(self._model_stats.items(),
                                       key=lambda x: x[1].total_tokens, reverse=True):
                model_breakdown.append({
                    "model": model,
                    "total_tokens": stats.total_tokens,
                    "prompt_tokens": stats.total_prompt,
                    "completion_tokens": stats.total_completion,
                    "call_count": stats.call_count,
                    "avg_prompt": int(stats.avg_prompt),
                    "avg_completion": int(stats.avg_completion),
                })

            # 最近 20 条调用
            recent = [asdict(r) for r in self._records[-20:]]
            recent.reverse()

            # 预算状态
            budget = self._config.max_tokens_per_day
            budget_pct = (today_tokens / budget * 100) if budget > 0 else 0

            return {
                "session_total": self._session_total,
                "today_tokens": today_tokens,
                "this_hour_tokens": this_hour_tokens,
                "total_calls": sum(s.call_count for s in self._model_stats.values()),
                "avg_tokens_per_call": int(self._session_total / max(1, sum(s.call_count for s in self._model_stats.values()))),
                "uptime_minutes": int((time.time() - self._start_time) / 60),
                "hourly_trend": hourly_trend,
                "daily_trend": daily_trend,
                "model_breakdown": model_breakdown,
                "recent_calls": recent,
                "config": asdict(self._config),
                "budget_used_pct": round(budget_pct, 1),
            }

    def flush(self):
        """强制保存。"""
        with self._lock:
            self._save_history()


# 全局单例
_tracker: TokenTracker | None = None


def get_tracker() -> TokenTracker:
    global _tracker
    if _tracker is None:
        _tracker = TokenTracker()
    return _tracker
