import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brain_daemon import BrainDaemon
from task_execution import ExecutionPlan


def make_daemon():
    brain = MagicMock()
    brain._awake = False
    daemon = BrainDaemon(brain, interval=0)
    daemon._observe = AsyncMock()
    daemon._run_engines = AsyncMock()
    daemon._teaching_cycle = AsyncMock()
    daemon._execute_task = AsyncMock()
    daemon._check_vitals = MagicMock(return_value=True)
    return daemon


@pytest.mark.asyncio
async def test_start_scans_orphans_without_mutation_by_default():
    daemon = make_daemon()
    daemon._orphan_recovery_enabled = False
    daemon._think_loop = AsyncMock()
    daemon._boot_goal_check = AsyncMock()
    with patch("brain_daemon.td.recover_orphaned_tasks", return_value=[{"task_id": "t1"}]) as scan:
        await daemon.start()
        scan.assert_called_once_with(enable_recovery=False)
        assert daemon.get_status()["safe_control"]["orphan_findings"] == [{"task_id": "t1"}]
        await daemon.stop()


@pytest.mark.asyncio
async def test_paused_loop_does_not_dequeue_new_work():
    daemon = make_daemon()
    daemon._paused = True
    daemon._running = True
    daemon._safe_pipeline_enabled = True

    async def end_after_observe():
        daemon._running = False

    daemon._observe.side_effect = end_after_observe
    with patch("brain_daemon.asyncio.sleep", new=AsyncMock()), \
         patch("brain_daemon.td.dequeue") as dequeue, \
         patch("brain_daemon.td.compute_interval", return_value=0):
        await daemon._think_loop()
    dequeue.assert_not_called()


def test_status_exposes_fail_safe_control_state():
    daemon = make_daemon()
    control = daemon.get_status()["safe_control"]
    assert set(control) == {
        "pipeline_enabled", "shadow",
        "orphan_recovery_enabled", "orphan_findings", "shadow_reports",
    }
    assert "metrics" in daemon.get_status()
    assert "queue_depth" in daemon.get_status()["metrics"]


@pytest.mark.asyncio
async def test_pipeline_flag_routes_to_legacy_by_default():
    daemon = make_daemon()
    daemon._safe_pipeline_enabled = False
    daemon._safe_pipeline_shadow = False
    daemon._execute_task_legacy = AsyncMock()
    daemon._execute_task_safe = AsyncMock()
    task = {"id": "t1", "content": "task"}
    await daemon._execute_task_inner(task)
    daemon._execute_task_legacy.assert_awaited_once()
    daemon._execute_task_safe.assert_not_awaited()


@pytest.mark.asyncio
async def test_enabled_pipeline_routes_to_safe_path():
    daemon = make_daemon()
    daemon._safe_pipeline_enabled = True
    daemon._safe_pipeline_shadow = False
    daemon._execute_task_legacy = AsyncMock()
    daemon._execute_task_safe = AsyncMock()
    task = {"id": "t1", "content": "task"}
    await daemon._execute_task_inner(task)
    daemon._execute_task_safe.assert_awaited_once()
    daemon._execute_task_legacy.assert_not_awaited()


@pytest.mark.asyncio
async def test_shadow_compares_pure_plans_and_executes_only_selected_path():
    daemon = make_daemon()
    daemon._safe_pipeline_enabled = False
    daemon._safe_pipeline_shadow = True
    daemon._build_legacy_execution_plan = MagicMock(
        return_value=ExecutionPlan("t1", 60, 4, "task", False)
    )
    daemon._build_execution_plan = MagicMock(
        return_value=ExecutionPlan("t1", 30, 4, "task", False)
    )
    daemon._execute_task_legacy = AsyncMock()
    daemon._execute_task_safe = AsyncMock()
    await daemon._execute_task_inner({"id": "t1", "content": "task"})
    daemon._execute_task_legacy.assert_awaited_once()
    daemon._execute_task_safe.assert_not_awaited()
    assert daemon._pipeline_shadow_reports == [{
        "task_id": "t1",
        "differences": {"timeout_s": {"legacy": 60, "safe": 30}},
    }]
