"""task_dispatcher 单元测试。

覆盖：入队/出队/防重入/卡住检测/原子写入/优先级排序/溢出处理。
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# 测试前清理队列文件
@pytest.fixture(autouse=True)
def clean_queue(tmp_path):
    """每个测试用临时目录替换队列文件路径。"""
    import task_dispatcher as td
    original_file = td._QUEUE_FILE
    original_data = td._DATA
    td._DATA = tmp_path
    td._QUEUE_FILE = tmp_path / "task_queue.json"
    yield
    td._QUEUE_FILE = original_file
    td._DATA = original_data


class TestEnqueue:
    """入队测试。"""

    def test_enqueue_basic(self):
        import task_dispatcher as td
        task = td.enqueue("测试任务", priority="P1", source="user")
        assert task["status"] == "ready"
        assert task["priority"] == "P1"
        assert task["source"] == "user"
        assert task["retries"] == 0

    def test_enqueue_teacher(self):
        import task_dispatcher as td
        task = td.enqueue_from_teacher("老师指令")
        assert task["priority"] == "P2"
        assert task["source"] == "teacher"

    def test_enqueue_user(self):
        import task_dispatcher as td
        task = td.enqueue_from_user("用户任务")
        assert task["priority"] == "P1"
        assert task["source"] == "user"

    def test_enqueue_self_check_fatal(self):
        import task_dispatcher as td
        task = td.enqueue_self_check_issue("LLM挂了", "fatal")
        assert task["priority"] == "P0"

    def test_enqueue_self_check_minor(self):
        import task_dispatcher as td
        task = td.enqueue_self_check_issue("小问题", "minor")
        assert task["priority"] == "P3"

    def test_enqueue_learning(self):
        import task_dispatcher as td
        task = td.enqueue_learning("学习内容", priority="L0", parent_id="abc")
        assert task["type"] == "learn"
        assert task["priority"] == "L0"
        assert task["parent_id"] == "abc"


class TestDequeue:
    """出队测试。"""

    def test_dequeue_empty(self):
        import task_dispatcher as td
        result = td.dequeue()
        assert result is None

    def test_dequeue_priority_order(self):
        """P0 > P1 > P2 > P3 > L0 > L1 > L2 > L3"""
        import task_dispatcher as td
        td.enqueue("低优先级", priority="P3")
        td.enqueue("高优先级", priority="P0")
        td.enqueue("中优先级", priority="P1")

        task = td.dequeue()
        assert task["priority"] == "P0"

    def test_task_before_learn(self):
        """任务队列永远优先于学习队列。"""
        import task_dispatcher as td
        td.enqueue_learning("学习", priority="L0")
        td.enqueue("任务P3", priority="P3")

        task = td.dequeue()
        assert task["priority"] == "P3"

    def test_dequeue_marks_running(self):
        import task_dispatcher as td
        td.enqueue("任务", priority="P1")
        task = td.dequeue()
        assert task["status"] == "running"
        assert task["running_at"] is not None

    def test_dequeue_skips_running(self):
        """已running的任务不会被再次出队。"""
        import task_dispatcher as td
        td.enqueue("任务1", priority="P1")
        td.enqueue("任务2", priority="P1")
        t1 = td.dequeue()
        t2 = td.dequeue()
        assert t1["id"] != t2["id"]


class TestStateTransition:
    """状态流转测试。"""

    def test_complete(self):
        import task_dispatcher as td
        task = td.enqueue("任务", priority="P1")
        td.dequeue()
        td.complete_task(task["id"])
        store = td._load_store()
        found = [t for t in store["tasks"] if t["id"] == task["id"]][0]
        assert found["status"] == "completed"
        assert found["running_at"] is None

    def test_fail_retry(self):
        import task_dispatcher as td
        task = td.enqueue("任务", priority="P1", max_retries=3)
        td.dequeue()
        td.fail_task(task["id"], "出错了")
        store = td._load_store()
        found = [t for t in store["tasks"] if t["id"] == task["id"]][0]
        assert found["status"] == "ready"
        assert found["retries"] == 1

    def test_fail_escalate(self):
        """重试超限后上报。"""
        import task_dispatcher as td
        task = td.enqueue("任务", priority="P1", max_retries=2)
        for i in range(3):
            td.dequeue()
            td.fail_task(task["id"], f"错误{i}")
        store = td._load_store()
        found = [t for t in store["tasks"] if t["id"] == task["id"]][0]
        assert found["status"] == "escalated"

    def test_block_and_resume(self):
        """阻塞+恢复父任务。"""
        import task_dispatcher as td
        parent = td.enqueue("父任务", priority="P1")
        td.dequeue()
        td.block_task(parent["id"], "需要学习")

        child = td.enqueue_learning("学习子任务", priority="L0", parent_id=parent["id"])
        td.dequeue()
        td.complete_task(child["id"])

        store = td._load_store()
        p = [t for t in store["tasks"] if t["id"] == parent["id"]][0]
        assert p["status"] == "ready"


class TestStuckDetection:
    """卡住检测测试。"""

    def test_release_stuck(self):
        import task_dispatcher as td
        task = td.enqueue("任务", priority="P1", timeout_s=1)
        td.dequeue()
        # 模拟超时
        store = td._load_store()
        for t in store["tasks"]:
            if t["id"] == task["id"]:
                t["running_at"] = (datetime.now() - timedelta(seconds=10)).isoformat()
        td._save_store(store)

        released = td.release_stuck_tasks()
        assert released == 1
        store = td._load_store()
        found = [t for t in store["tasks"] if t["id"] == task["id"]][0]
        assert found["status"] == "ready"
        assert found["retries"] == 1


class TestDynamicInterval:
    """动态间隔测试。"""

    def test_empty_queue(self):
        import task_dispatcher as td
        assert td.compute_interval() == 300

    def test_p0_interval(self):
        import task_dispatcher as td
        td.enqueue("紧急", priority="P0")
        assert td.compute_interval() == 10

    def test_p1_interval(self):
        import task_dispatcher as td
        td.enqueue("用户任务", priority="P1")
        assert td.compute_interval() == 30

    def test_learn_interval(self):
        import task_dispatcher as td
        td.enqueue_learning("学习", priority="L2")
        assert td.compute_interval() == 120


class TestDailyState:
    """每日状态持久化测试。"""

    def test_daily_check_persistence(self):
        import task_dispatcher as td
        assert not td.is_daily_check_done()
        td.set_daily_check_done()
        assert td.is_daily_check_done()

    def test_monthly_check_persistence(self):
        import task_dispatcher as td
        assert not td.is_monthly_check_done()
        td.set_monthly_check_done()
        assert td.is_monthly_check_done()


class TestAtomicWrite:
    """原子写入测试。"""

    def test_file_not_corrupted(self):
        import task_dispatcher as td
        td.enqueue("任务1")
        td.enqueue("任务2")
        td.enqueue("任务3")
        store = td._load_store()
        assert len(store["tasks"]) == 3
        # 验证JSON可解析
        raw = td._QUEUE_FILE.read_text("utf-8")
        parsed = json.loads(raw)
        assert parsed["version"] == 1
