"""Cron 统一 + 心跳增强 — 单元测试。

覆盖：
- api/cron.py: _parse_interval, add_job, remove_job_by_name, get_jobs
- adapters/tools/scheduler.py: SchedulerAdapter 委托调用
- adapters/channel/websocket_channel.py: 心跳数据结构
"""

import pytest
import time
import json
from unittest.mock import AsyncMock, MagicMock, patch


# === Cron 统一测试 ===

class TestParseInterval:
    """_parse_interval 将多种格式统一为秒数。"""

    def test_interval_seconds_priority(self):
        from api.cron import _parse_interval
        assert _parse_interval("daily", 120) == 120

    def test_schedule_keywords(self):
        from api.cron import _parse_interval
        assert _parse_interval("hourly", None) == 3600
        assert _parse_interval("daily", None) == 86400
        assert _parse_interval("weekly", None) == 604800
        assert _parse_interval("monthly", None) == 2592000

    def test_schedule_every_format(self):
        from api.cron import _parse_interval
        assert _parse_interval("every 5 minutes", None) == 300
        assert _parse_interval("every 2 hours", None) == 7200
        assert _parse_interval("every 10 seconds", None) == 10

    def test_invalid_returns_zero(self):
        from api.cron import _parse_interval
        assert _parse_interval(None, None) == 0
        assert _parse_interval("", 0) == 0
        assert _parse_interval("nonsense", None) == 0


class TestAddJob:
    """add_job 创建符合统一格式的任务。"""

    def test_add_job_with_interval(self, tmp_path, monkeypatch):
        import api.cron as cron_mod
        monkeypatch.setattr(cron_mod, "_CRON_FILE", tmp_path / "cron.json")
        monkeypatch.setattr(cron_mod, "_jobs", [])
        job = cron_mod.add_job("测试任务", "hello", interval_seconds=120)
        assert job["interval_seconds"] == 120
        assert job["name"] == "测试任务"
        assert job["command"] == "hello"
        assert "id" in job
        assert job["enabled"] is True

    def test_add_job_with_schedule(self, tmp_path, monkeypatch):
        import api.cron as cron_mod
        monkeypatch.setattr(cron_mod, "_CRON_FILE", tmp_path / "cron.json")
        monkeypatch.setattr(cron_mod, "_jobs", [])
        job = cron_mod.add_job("日常汇报", "report", schedule="daily")
        assert job["interval_seconds"] == 86400
        assert job["schedule"] == "daily"

    def test_add_job_min_interval_error(self, tmp_path, monkeypatch):
        import api.cron as cron_mod
        monkeypatch.setattr(cron_mod, "_CRON_FILE", tmp_path / "cron.json")
        monkeypatch.setattr(cron_mod, "_jobs", [])
        with pytest.raises(ValueError, match="最小间隔"):
            cron_mod.add_job("太快了", "cmd", interval_seconds=30)

    def test_add_job_no_command_error(self, tmp_path, monkeypatch):
        import api.cron as cron_mod
        monkeypatch.setattr(cron_mod, "_CRON_FILE", tmp_path / "cron.json")
        monkeypatch.setattr(cron_mod, "_jobs", [])
        with pytest.raises(ValueError, match="command"):
            cron_mod.add_job("无命令", "", interval_seconds=120)


class TestRemoveJobByName:
    """remove_job_by_name 按 name 删除。"""

    def test_remove_existing(self, tmp_path, monkeypatch):
        import api.cron as cron_mod
        monkeypatch.setattr(cron_mod, "_CRON_FILE", tmp_path / "cron.json")
        monkeypatch.setattr(cron_mod, "_jobs", [
            {"id": "a1", "name": "task1", "command": "cmd1"},
            {"id": "b2", "name": "task2", "command": "cmd2"},
        ])
        removed = cron_mod.remove_job_by_name("task1")
        assert removed == 1
        assert len(cron_mod._jobs) == 1
        assert cron_mod._jobs[0]["name"] == "task2"

    def test_remove_nonexistent(self, tmp_path, monkeypatch):
        import api.cron as cron_mod
        monkeypatch.setattr(cron_mod, "_CRON_FILE", tmp_path / "cron.json")
        monkeypatch.setattr(cron_mod, "_jobs", [])
        removed = cron_mod.remove_job_by_name("ghost")
        assert removed == 0


class TestGetJobs:
    """get_jobs 返回当前任务列表副本。"""

    def test_returns_copy(self, tmp_path, monkeypatch):
        import api.cron as cron_mod
        monkeypatch.setattr(cron_mod, "_CRON_FILE", tmp_path / "cron.json")
        (tmp_path / "cron.json").write_text('[{"id":"x","name":"t"}]')
        jobs = cron_mod.get_jobs()
        assert len(jobs) == 1
        jobs.append({"id": "y"})
        assert len(cron_mod.get_jobs()) == 1  # 原列表不受影响


# === SchedulerAdapter 委托测试 ===

@pytest.mark.asyncio
class TestSchedulerAdapter:
    """SchedulerAdapter 委托 api/cron.py 函数。"""

    async def test_list_empty(self, tmp_path, monkeypatch):
        import api.cron as cron_mod
        monkeypatch.setattr(cron_mod, "_CRON_FILE", tmp_path / "cron.json")
        monkeypatch.setattr(cron_mod, "_jobs", [])
        (tmp_path / "cron.json").write_text("[]")
        from adapters.tools.scheduler import SchedulerAdapter
        adapter = SchedulerAdapter()
        result = await adapter.execute("scheduler", {"action": "list"})
        assert result["success"] is True
        assert "没有" in result["result"]

    async def test_add_and_list(self, tmp_path, monkeypatch):
        import api.cron as cron_mod
        monkeypatch.setattr(cron_mod, "_CRON_FILE", tmp_path / "cron.json")
        monkeypatch.setattr(cron_mod, "_jobs", [])
        from adapters.tools.scheduler import SchedulerAdapter
        adapter = SchedulerAdapter()
        r = await adapter.execute("scheduler", {
            "action": "add", "name": "greet", "schedule": "hourly", "command": "say hi"})
        assert r["success"] is True
        assert "greet" in r["result"]
        r2 = await adapter.execute("scheduler", {"action": "list"})
        assert "greet" in r2["result"]

    async def test_remove(self, tmp_path, monkeypatch):
        import api.cron as cron_mod
        monkeypatch.setattr(cron_mod, "_CRON_FILE", tmp_path / "cron.json")
        monkeypatch.setattr(cron_mod, "_jobs", [
            {"id": "z1", "name": "bye", "command": "farewell", "schedule": "daily",
             "interval_seconds": 86400, "enabled": True}])
        from adapters.tools.scheduler import SchedulerAdapter
        adapter = SchedulerAdapter()
        r = await adapter.execute("scheduler", {"action": "remove", "name": "bye"})
        assert r["success"] is True
        assert "1" in r["result"]

    async def test_unknown_tool(self):
        from adapters.tools.scheduler import SchedulerAdapter
        adapter = SchedulerAdapter()
        r = await adapter.execute("unknown_tool", {"action": "list"})
        assert r["success"] is False


# === 心跳数据结构测试 ===

class TestHeartbeatStructure:
    """验证 WebSocketChannelAdapter 心跳相关属性。"""

    def test_channel_has_heartbeat_fields(self):
        from adapters.channel.websocket_channel import WebSocketChannelAdapter
        ch = WebSocketChannelAdapter()
        assert hasattr(ch, "_last_pong")
        assert hasattr(ch, "_server_hb_task")
        assert isinstance(ch._last_pong, dict)

    def test_server_ping_constants(self):
        from adapters.channel.websocket_channel import _SERVER_PING_INTERVAL, _SERVER_PONG_TIMEOUT
        assert _SERVER_PING_INTERVAL > 0
        assert _SERVER_PONG_TIMEOUT > _SERVER_PING_INTERVAL


# === brain_daemon 重连通知测试 ===

class TestCheckVitals:
    """_check_vitals 连接恢复时触发通知。"""

    def test_disconnect_detection(self):
        from brain_daemon import BrainDaemon
        brain = MagicMock()
        brain._awake = True
        brain._sessions = {}
        brain.learning = None
        daemon = BrainDaemon.__new__(BrainDaemon)
        daemon._brain = brain
        daemon._ws_channel = MagicMock()
        daemon._ws_channel._connections = {}
        daemon._was_disconnected = False
        daemon._check_vitals()
        assert daemon._was_disconnected is True

    def test_reconnect_detection(self):
        from brain_daemon import BrainDaemon
        brain = MagicMock()
        brain._awake = True
        daemon = BrainDaemon.__new__(BrainDaemon)
        daemon._brain = brain
        daemon._ws_channel = MagicMock()
        daemon._ws_channel._connections = {"c1": MagicMock()}
        daemon._ws_channel.broadcast = AsyncMock()
        daemon._was_disconnected = True
        with patch("brain_daemon.asyncio.create_task"):
            daemon._check_vitals()
        assert daemon._was_disconnected is False
