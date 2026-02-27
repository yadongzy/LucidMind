"""Tests for command_queue.py — OpenClaw 风格 Lane-based 异步任务队列。

对标 OpenClaw command-queue.test.ts，覆盖：
- 基本入队执行
- 多车道并发隔离
- Generation 防幽灵
- 并发上限控制
- 清空车道
- 优雅关闭（draining）
- 软失败内联重试（通过 brain_task_executor）
- update_task_progress 中间状态推送
"""
import asyncio
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from command_queue import (
    CommandQueue, CommandLane, LaneClearedError, GatewayDrainingError,
    get_command_queue, reset_command_queue,
)


@pytest.fixture(autouse=True)
def fresh_queue():
    """每个测试使用全新的命令队列。"""
    reset_command_queue()
    yield
    reset_command_queue()


# ═══════════════════════════════════════════════
# 基本功能
# ═══════════════════════════════════════════════

@pytest.mark.asyncio
async def test_basic_enqueue_and_execute():
    """基本入队执行：任务入队后被执行并返回结果。"""
    cq = CommandQueue()

    async def hello():
        return "hello"

    result = await cq.enqueue(
        lane=CommandLane.CHAT,
        task=hello,
        task_id="test_1",
    )
    assert result == "hello"


@pytest.mark.asyncio
async def test_async_task_execution():
    """异步任务正确执行。"""
    cq = CommandQueue()
    
    async def my_task():
        await asyncio.sleep(0.01)
        return 42
    
    result = await cq.enqueue(
        lane=CommandLane.DAEMON,
        task=my_task,
        task_id="async_1",
    )
    assert result == 42


@pytest.mark.asyncio
async def test_task_exception_propagated():
    """任务异常正确传播给调用者。"""
    cq = CommandQueue()
    
    async def failing_task():
        raise ValueError("boom")
    
    with pytest.raises(ValueError, match="boom"):
        await cq.enqueue(
            lane=CommandLane.CHAT,
            task=failing_task,
            task_id="fail_1",
        )


# ═══════════════════════════════════════════════
# 多车道并发隔离
# ═══════════════════════════════════════════════

@pytest.mark.asyncio
async def test_lanes_run_independently():
    """不同车道的任务互不阻塞，可以并行执行。"""
    cq = CommandQueue()
    order = []
    
    async def slow_task(name, delay):
        order.append(f"{name}_start")
        await asyncio.sleep(delay)
        order.append(f"{name}_end")
        return name
    
    # 同时在两个不同车道入队
    t1 = asyncio.create_task(cq.enqueue(
        lane=CommandLane.CHAT,
        task=lambda: slow_task("chat", 0.05),
        task_id="chat_1",
    ))
    t2 = asyncio.create_task(cq.enqueue(
        lane=CommandLane.DAEMON,
        task=lambda: slow_task("daemon", 0.05),
        task_id="daemon_1",
    ))
    
    r1, r2 = await asyncio.gather(t1, t2)
    assert r1 == "chat"
    assert r2 == "daemon"
    # 两个任务应该都已启动（并行）
    assert "chat_start" in order
    assert "daemon_start" in order


# ═══════════════════════════════════════════════
# 同车道串行（maxConcurrent=1 时）
# ═══════════════════════════════════════════════

@pytest.mark.asyncio
async def test_same_lane_sequential():
    """同一车道（maxConcurrent=1）任务按顺序执行。"""
    cq = CommandQueue()
    # CRON lane maxConcurrent=1
    order = []
    
    async def task(name):
        order.append(f"{name}_start")
        await asyncio.sleep(0.02)
        order.append(f"{name}_end")
        return name
    
    t1 = asyncio.create_task(cq.enqueue(
        lane=CommandLane.CRON,
        task=lambda: task("A"),
        task_id="cron_A",
    ))
    # 让 A 先被 pump 取走
    await asyncio.sleep(0.001)
    t2 = asyncio.create_task(cq.enqueue(
        lane=CommandLane.CRON,
        task=lambda: task("B"),
        task_id="cron_B",
    ))
    
    await asyncio.gather(t1, t2)
    # A 必须在 B 之前完成
    assert order.index("A_end") < order.index("B_start")


# ═══════════════════════════════════════════════
# 并发上限控制
# ═══════════════════════════════════════════════

@pytest.mark.asyncio
async def test_max_concurrent_respected():
    """并发上限：CHAT lane maxConcurrent=3，不超过3个任务同时执行。"""
    cq = CommandQueue()
    peak_concurrent = 0
    current = 0
    lock = asyncio.Lock()
    
    async def tracked_task(i):
        nonlocal peak_concurrent, current
        async with lock:
            current += 1
            if current > peak_concurrent:
                peak_concurrent = current
        await asyncio.sleep(0.03)
        async with lock:
            current -= 1
        return i
    
    tasks = [
        asyncio.create_task(cq.enqueue(
            lane=CommandLane.CHAT,
            task=lambda idx=i: tracked_task(idx),
            task_id=f"chat_{i}",
        ))
        for i in range(6)
    ]
    
    results = await asyncio.gather(*tasks)
    assert set(results) == {0, 1, 2, 3, 4, 5}
    assert peak_concurrent <= 3


# ═══════════════════════════════════════════════
# Generation 防幽灵
# ═══════════════════════════════════════════════

@pytest.mark.asyncio
async def test_reset_all_lanes_bumps_generation():
    """resetAllLanes 后 generation 递增，排队任务被拒绝。"""
    cq = CommandQueue()
    
    async def slow():
        await asyncio.sleep(1)
        return "should_not_complete"
    
    # 入队一个慢任务
    t1 = asyncio.create_task(cq.enqueue(
        lane=CommandLane.CRON,
        task=slow,
        task_id="slow_1",
    ))
    await asyncio.sleep(0.01)
    
    # 再入队一个（此时第一个正在执行，第二个排队）
    t2 = asyncio.create_task(cq.enqueue(
        lane=CommandLane.CRON,
        task=slow,
        task_id="slow_2",
    ))
    await asyncio.sleep(0.01)
    
    # 重置所有车道
    await cq.reset_all_lanes()
    
    # 排队的任务应该收到 LaneClearedError
    with pytest.raises(LaneClearedError):
        await t2
    
    # 第一个正在执行的不受影响（但 pump 不会再驱动新任务）
    t1.cancel()
    try:
        await t1
    except (asyncio.CancelledError, Exception):
        pass


# ═══════════════════════════════════════════════
# 清空车道
# ═══════════════════════════════════════════════

@pytest.mark.asyncio
async def test_clear_lane():
    """clearLane 清空排队任务，不影响正在执行的。"""
    cq = CommandQueue()
    
    async def slow():
        await asyncio.sleep(1)
    
    t1 = asyncio.create_task(cq.enqueue(
        lane=CommandLane.CRON,
        task=slow,
        task_id="active",
    ))
    await asyncio.sleep(0.01)
    
    t2 = asyncio.create_task(cq.enqueue(
        lane=CommandLane.CRON,
        task=slow,
        task_id="queued",
    ))
    await asyncio.sleep(0.01)
    
    await cq.clear_lane(CommandLane.CRON)
    
    with pytest.raises(LaneClearedError):
        await t2
    
    t1.cancel()
    try:
        await t1
    except (asyncio.CancelledError, Exception):
        pass


# ═══════════════════════════════════════════════
# Gateway Draining（优雅关闭）
# ═══════════════════════════════════════════════

@pytest.mark.asyncio
async def test_gateway_draining_rejects_new_tasks():
    """markGatewayDraining 后新任务被拒绝。"""
    cq = CommandQueue()
    cq.mark_gateway_draining()
    
    async def task():
        return "nope"
    
    with pytest.raises(GatewayDrainingError):
        await cq.enqueue(
            lane=CommandLane.CHAT,
            task=task,
            task_id="rejected",
        )


@pytest.mark.asyncio
async def test_wait_for_idle():
    """waitForIdle 等待所有活跃任务完成。"""
    cq = CommandQueue()
    
    async def quick():
        await asyncio.sleep(0.02)
        return "done"
    
    t = asyncio.create_task(cq.enqueue(
        lane=CommandLane.DAEMON,
        task=quick,
        task_id="quick_1",
    ))
    
    await asyncio.sleep(0.005)
    assert cq.get_total_active() > 0
    
    idle = await cq.wait_for_idle(timeout=5.0)
    assert idle is True
    assert cq.get_total_active() == 0
    await t


# ═══════════════════════════════════════════════
# 状态查询
# ═══════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_all_status():
    """获取所有车道状态。"""
    cq = CommandQueue()
    status = cq.get_all_status()
    assert "lanes" in status
    assert "total_active" in status
    assert "total_queued" in status
    assert "gateway_draining" in status
    assert status["gateway_draining"] is False
    assert len(status["lanes"]) == len(CommandLane)


@pytest.mark.asyncio
async def test_get_lane_status():
    """获取指定车道状态。"""
    cq = CommandQueue()
    status = cq.get_lane_status(CommandLane.CHAT)
    assert status["lane"] == "chat"
    assert status["active"] == 0
    assert status["queued"] == 0
    assert status["max_concurrent"] == 3


# ═══════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════

def test_global_singleton():
    """全局单例正确工作。"""
    q1 = get_command_queue()
    q2 = get_command_queue()
    assert q1 is q2


def test_reset_global():
    """重置全局单例。"""
    q1 = get_command_queue()
    reset_command_queue()
    q2 = get_command_queue()
    assert q1 is not q2


# ═══════════════════════════════════════════════
# task_dispatcher update_task_progress
# ═══════════════════════════════════════════════

def test_update_task_progress():
    """update_task_progress 推送中间状态。"""
    import task_dispatcher as td
    from task_dispatcher_utils import load_store, save_store
    
    # 创建一个测试任务
    store = load_store()
    store["tasks"] = [{
        "id": "test_prog",
        "type": "task",
        "priority": "P2",
        "source": "test",
        "content": "test progress",
        "status": "ready",
        "created_at": "2026-01-01T00:00:00",
        "running_at": None,
        "completed_at": None,
        "retries": 0,
        "max_retries": 3,
        "last_error": None,
        "timeout_s": 120,
    }]
    save_store(store)
    
    # 更新进度
    td.update_task_progress("test_prog", "执行中(第1次尝试)")
    
    # 验证
    store = load_store()
    task = store["tasks"][0]
    assert task["status"] == "running"
    assert task["progress"] == "执行中(第1次尝试)"
    assert task["running_at"] is not None
    
    # 清理
    store["tasks"] = []
    save_store(store)


# ═══════════════════════════════════════════════
# brain_task_executor 内联重试
# ═══════════════════════════════════════════════

@pytest.mark.asyncio
async def test_task_executor_inline_retry_on_soft_failure():
    """软失败（空承诺+工具未执行）触发内联重试。"""
    from unittest.mock import AsyncMock, MagicMock, patch
    from brain_task_executor import TaskExecutorMixin, MAX_INLINE_RETRIES
    
    call_count = 0
    
    async def mock_process(sid, content, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            # 前两次返回空承诺
            return {"tool_calls_happened": False, "empty_promise_detected": True, "reply": "请稍等"}
        # 第三次成功
        return {"tool_calls_happened": True, "empty_promise_detected": False, "reply": "done"}
    
    brain = MagicMock()
    brain.process = AsyncMock(side_effect=mock_process)
    brain.llm = MagicMock()
    brain._sessions = {}
    
    executor = TaskExecutorMixin()
    executor._brain = brain
    
    task = {
        "id": "retry_test",
        "type": "task",
        "content": "搜索测试",
        "source": "user",
        "priority": "P2",
        "timeout_s": 30,
        "retries": 0,
        "max_retries": 3,
    }
    
    with patch("task_dispatcher.complete_task") as mock_complete, \
         patch("task_dispatcher.update_task_progress"):
        await executor._execute_task_inner(task)
        mock_complete.assert_called_once_with("retry_test")
    
    assert call_count == 3  # 两次软失败 + 一次成功


@pytest.mark.asyncio
async def test_task_executor_hard_failure_no_inline_retry():
    """硬异常不内联重试，直接交给 fail_task。"""
    from unittest.mock import AsyncMock, MagicMock, patch
    from brain_task_executor import TaskExecutorMixin
    
    async def mock_process(sid, content, **kwargs):
        raise RuntimeError("API key invalid")
    
    brain = MagicMock()
    brain.process = AsyncMock(side_effect=mock_process)
    brain.llm = MagicMock()
    brain._sessions = {}
    
    executor = TaskExecutorMixin()
    executor._brain = brain
    
    task = {
        "id": "hard_fail",
        "type": "task",
        "content": "测试",
        "source": "user",
        "priority": "P2",
        "timeout_s": 30,
        "retries": 0,
        "max_retries": 3,
    }
    
    with patch("task_dispatcher.fail_task") as mock_fail, \
         patch("task_dispatcher.update_task_progress"):
        await executor._execute_task_inner(task)
        mock_fail.assert_called_once()
        args = mock_fail.call_args[0]
        assert args[0] == "hard_fail"
        assert "API key invalid" in args[1]


# ═══════════════════════════════════════════════
# task_decomposer 任务分解器
# ═══════════════════════════════════════════════

def test_should_decompose_complex_task():
    """复杂任务（长文本+搜索关键词+多步骤）应触发分解。"""
    from task_decomposer import should_decompose
    task = {
        "id": "t1",
        "type": "task",
        "source": "user",
        "content": "请搜索最新的AI论文，然后对比分析GPT-4和Claude的性能差异，之后总结成一份报告发给老师，最后把报告存档到知识库中",
    }
    assert should_decompose(task) is True


def test_should_not_decompose_simple_task():
    """简单任务不触发分解。"""
    from task_decomposer import should_decompose
    task = {
        "id": "t2",
        "type": "task",
        "source": "user",
        "content": "查一下天气",
    }
    assert should_decompose(task) is False


def test_should_not_decompose_learning_task():
    """学习任务不分解。"""
    from task_decomposer import should_decompose
    task = {
        "id": "t3",
        "type": "learn",
        "source": "engine",
        "content": "分析并学习如何搜索论文，然后总结搜索策略，之后记录到经验库，最后验证学习效果",
    }
    assert should_decompose(task) is False


def test_should_not_decompose_already_decomposed():
    """已分解的子任务不再分解（防递归）。"""
    from task_decomposer import should_decompose
    task = {
        "id": "t4",
        "type": "task",
        "source": "user",
        "content": "请搜索最新的AI论文，然后对比分析GPT-4和Claude的性能差异，之后总结成一份报告",
        "decomposed": True,
    }
    assert should_decompose(task) is False


def test_parse_subtasks_numbered():
    """解析数字编号的子任务列表。"""
    from task_decomposer import _parse_subtasks
    text = "1. 搜索最新AI论文\n2. 对比GPT-4和Claude\n3. 撰写报告\n4. 发送给老师"
    result = _parse_subtasks(text)
    assert len(result) == 4
    assert result[0] == "搜索最新AI论文"
    assert result[3] == "发送给老师"


def test_parse_subtasks_bullet():
    """解析bullet格式的子任务列表。"""
    from task_decomposer import _parse_subtasks
    text = "- 第一步搜索论文\n- 第二步分析对比\n- 第三步撰写报告"
    result = _parse_subtasks(text)
    assert len(result) == 3


def test_parse_subtasks_filters_short():
    """过短的行不算有效子任务（<3字符）。"""
    from task_decomposer import _parse_subtasks
    text = "1. 搜索论文并分析\n2. ok\n3. 撰写报告并发送"
    result = _parse_subtasks(text)
    assert len(result) == 2  # "ok"(2字符) 被过滤


@pytest.mark.asyncio
async def test_decompose_task_with_mock_llm():
    """用 Mock LLM 测试完整分解流程。"""
    from unittest.mock import AsyncMock, MagicMock, patch
    from task_decomposer import decompose_task
    from task_dispatcher_utils import load_store, save_store

    # 准备干净的 task store
    store = load_store()
    original_tasks = store.get("tasks", [])

    brain = MagicMock()
    brain.llm = MagicMock()
    brain.llm.chat = AsyncMock(return_value={
        "content": "1. 搜索最新AI论文\n2. 对比分析GPT-4和Claude\n3. 撰写总结报告"
    })

    task = {
        "id": "decomp_test",
        "type": "task",
        "source": "user",
        "priority": "P2",
        "content": "搜索最新AI论文并对比分析",
        "timeout_s": 120,
    }

    # 先将父任务入队
    import task_dispatcher as td
    parent = td.enqueue(task["content"], priority="P2", source="user")
    task["id"] = parent["id"]

    result = await decompose_task(brain, task)
    assert len(result) == 3
    assert all("子任务" in r["content"] for r in result)

    # 验证父任务被阻塞
    store = load_store()
    parent_in_store = next((t for t in store["tasks"] if t["id"] == task["id"]), None)
    assert parent_in_store is not None
    assert parent_in_store["status"] == "blocked"

    # 验证子任务标记 decomposed
    for sub in result:
        sub_in_store = next((t for t in store["tasks"] if t["id"] == sub["id"]), None)
        assert sub_in_store is not None
        assert sub_in_store.get("decomposed") is True

    # 清理
    store["tasks"] = original_tasks
    save_store(store)


# ═══════════════════════════════════════════════
# ENH-1: CRON lane 集成
# ═══════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cron_lane_exists_and_serial():
    """CRON lane 存在且最大并发为1（串行）。"""
    from command_queue import get_command_queue, CommandLane, reset_command_queue
    reset_command_queue()
    cq = get_command_queue()
    status = cq.get_lane_status(CommandLane.CRON)
    assert status["lane"] == "cron"
    assert status["max_concurrent"] == 1
    reset_command_queue()


# ═══════════════════════════════════════════════
# ENH-2: SUBAGENT lane 用于子任务
# ═══════════════════════════════════════════════

def test_subtask_routed_to_subagent_lane():
    """子任务（有 parent_id）应路由到 SUBAGENT lane。"""
    from brain_task_executor import TaskExecutorMixin
    from command_queue import CommandLane

    # 有 parent_id 的任务
    sub_task = {"id": "sub1", "parent_id": "parent1", "type": "task", "source": "user", "content": "子任务"}
    # 无 parent_id 的任务
    normal_task = {"id": "norm1", "type": "task", "source": "user", "content": "普通任务"}

    # 验证 lane 选择逻辑
    sub_lane = CommandLane.SUBAGENT if sub_task.get("parent_id") else CommandLane.DAEMON
    norm_lane = CommandLane.SUBAGENT if normal_task.get("parent_id") else CommandLane.DAEMON
    assert sub_lane == CommandLane.SUBAGENT
    assert norm_lane == CommandLane.DAEMON


@pytest.mark.asyncio
async def test_subagent_lane_concurrent():
    """SUBAGENT lane 最大并发为2。"""
    from command_queue import get_command_queue, CommandLane, reset_command_queue
    reset_command_queue()
    cq = get_command_queue()
    status = cq.get_lane_status(CommandLane.SUBAGENT)
    assert status["max_concurrent"] == 2
    reset_command_queue()


# ═══════════════════════════════════════════════
# ENH-3: 父任务聚合闭环
# ═══════════════════════════════════════════════

def test_resume_parent_waits_for_all_siblings():
    """父任务仅在所有子任务完成后才恢复。"""
    import task_dispatcher as td
    from task_dispatcher_utils import load_store, save_store

    # 准备
    store = load_store()
    original_tasks = store.get("tasks", [])

    # 创建父任务并阻塞
    parent = td.enqueue("父任务测试", priority="P2", source="user")
    td.block_task(parent["id"], "已分解为2个子任务")

    # 创建2个子任务
    sub1 = td.enqueue("[子任务1/2] 第一步", parent_id=parent["id"])
    sub2 = td.enqueue("[子任务2/2] 第二步", parent_id=parent["id"])

    # 完成第一个子任务 — 父任务应该还是 blocked
    td.complete_task(sub1["id"])
    store = load_store()
    parent_state = next(t for t in store["tasks"] if t["id"] == parent["id"])
    assert parent_state["status"] == "blocked"

    # 完成第二个子任务 — 父任务应该变为 completed
    td.complete_task(sub2["id"])
    store = load_store()
    parent_state = next(t for t in store["tasks"] if t["id"] == parent["id"])
    assert parent_state["status"] == "completed"
    assert "子任务完成" in parent_state.get("progress", "")

    # 清理
    store["tasks"] = original_tasks
    save_store(store)


def test_resume_parent_partial_failure():
    """部分子任务失败时，父任务恢复为 ready（可重试）。"""
    import task_dispatcher as td
    from task_dispatcher_utils import load_store, save_store

    store = load_store()
    original_tasks = store.get("tasks", [])

    parent = td.enqueue("父任务部分失败", priority="P2", source="user")
    td.block_task(parent["id"], "已分解为2个子任务")

    sub1 = td.enqueue("[子任务1/2] 成功步骤", parent_id=parent["id"], max_retries=0)
    sub2 = td.enqueue("[子任务2/2] 失败步骤", parent_id=parent["id"], max_retries=0)

    td.complete_task(sub1["id"])
    # 让 sub2 失败并 escalate（retries >= max_retries）
    td.fail_task(sub2["id"], "模拟失败")

    store = load_store()
    parent_state = next(t for t in store["tasks"] if t["id"] == parent["id"])
    # 部分失败 → ready（可重试），不是全部失败
    assert parent_state["status"] == "ready"
    assert "失败" in parent_state.get("progress", "")

    # 清理
    store["tasks"] = original_tasks
    save_store(store)


# ═══════════════════════════════════════════════
# ENH-4: notify hook 包含 progress/parent_id
# ═══════════════════════════════════════════════

def test_notify_hook_includes_progress():
    """task_dispatcher 的 notify 事件包含 progress 字段。"""
    import task_dispatcher as td
    from task_dispatcher_utils import load_store, save_store

    store = load_store()
    original_tasks = store.get("tasks", [])

    captured = []
    def hook(event, task):
        captured.append({"event": event, "task": task})

    td.register_notify_hook(hook)
    try:
        t = td.enqueue("notify测试", priority="P2")
        td.update_task_progress(t["id"], "执行中...")
        # 检查 task_progress 事件中有 progress
        progress_events = [c for c in captured if c["event"] == "task_progress"]
        assert len(progress_events) >= 1
        assert progress_events[0]["task"].get("progress") == "执行中..."
    finally:
        td._notify_hooks.remove(hook)
        store = load_store()
        store["tasks"] = original_tasks
        save_store(store)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
