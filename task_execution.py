"""任务执行管线的无 I/O 控制原语。

集中管理重试预算、父任务截止时间和协作式取消，使执行器阶段可独立测试。
"""

from dataclasses import dataclass
import time
from typing import Callable

from task_model import FailureReason


class TaskCancelled(RuntimeError):
    """任务在安全点观察到协作式取消。"""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay_s: float = 2.0
    max_delay_s: float = 30.0
    jitter_ratio: float = 0.2

    def delay(self, attempt: int, random_value: float = 0.5) -> float:
        """返回有界指数退避；attempt 从 1 开始。"""

        if attempt < 1:
            raise ValueError("attempt 必须从 1 开始")
        raw = min(self.max_delay_s, self.base_delay_s * (2 ** (attempt - 1)))
        jitter = raw * self.jitter_ratio * ((random_value * 2) - 1)
        return max(0.0, raw + jitter)


@dataclass
class ExecutionControl:
    deadline_monotonic: float
    is_cancel_requested: Callable[[], bool] = lambda: False
    clock: Callable[[], float] = time.monotonic

    def remaining_timeout(self, requested_s: float) -> float:
        """子步骤不得突破父任务剩余截止时间。"""

        remaining = self.deadline_monotonic - self.clock()
        if remaining <= 0:
            raise TimeoutError("父任务截止时间已耗尽")
        return min(float(requested_s), remaining)

    def checkpoint(self) -> None:
        """无副作用安全点；取消只在这些边界生效。"""

        if self.is_cancel_requested():
            raise TaskCancelled("任务已请求取消")


def classify_failure(error: BaseException) -> FailureReason:
    """将执行异常映射为稳定的 FailureReason。"""

    if isinstance(error, TaskCancelled):
        return FailureReason.CANCELLED
    if isinstance(error, TimeoutError):
        return FailureReason.TIMEOUT
    if isinstance(error, PermissionError):
        return FailureReason.PERMISSION
    if isinstance(error, (ConnectionError, OSError)):
        return FailureReason.INFRASTRUCTURE
    if isinstance(error, ValueError):
        return FailureReason.VALIDATION
    return FailureReason.UNKNOWN
