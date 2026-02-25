"""Tool Safety Layer — 工具安全审批系统。

危险工具执行前需要用户确认。通过 WebSocket 推送审批请求，等待用户批准/拒绝。
安全工具直接执行，无需确认。

分类策略:
- DANGEROUS: 执行前必须用户确认（文件删除、Shell、代码执行、系统操作等）
- SENSITIVE: 首次执行需确认，同 session 内后续同名工具自动放行
- SAFE: 直接执行，无需确认（查询类、只读操作）
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("security")

# ─────────────────── 工具安全分类 ───────────────────

DANGEROUS_TOOLS = {
    # Shell / 代码执行
    "run_shell", "run_python", "run_script", "run_node",
    # 文件删除
    "delete_file", "move_file",
    # Git 写操作
    "git_commit", "git_push",
    # Docker 操作
    "docker_restart", "docker_stop", "docker_rm",
    # 系统操作
    "send_email",
    # 剪贴板写
    "clipboard_write",
}

SENSITIVE_TOOLS = {
    # 首次确认，同 session 内后续自动放行
    "write_file",
    "web_search", "browser_navigate", "browser_click",
    "github_create_issue",
    "add_bookmark",
    "monitor_add",
    "set_reminder",
}

# SAFE: 不在 DANGEROUS 和 SENSITIVE 中的工具默认为安全

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "security_config.json"


class ToolSafetyGuard:
    """工具安全守卫 — 拦截危险工具调用，等待用户确认。"""

    def __init__(self):
        self._enabled: bool = True
        self._pending: dict[str, asyncio.Future] = {}  # request_id -> Future
        self._session_approved: dict[str, set[str]] = {}  # session_id -> {tool_names}
        self._ws_channel = None
        self._custom_dangerous: set[str] = set()
        self._custom_safe: set[str] = set()
        self._load_config()

    def set_ws_channel(self, ws_channel) -> None:
        """注入 WebSocket 通道引用，用于推送审批请求。"""
        self._ws_channel = ws_channel

    def _load_config(self) -> None:
        """加载自定义安全配置。"""
        if _CONFIG_PATH.exists():
            try:
                cfg = json.loads(_CONFIG_PATH.read_text())
                self._enabled = cfg.get("enabled", True)
                self._custom_dangerous = set(cfg.get("dangerous_tools", []))
                self._custom_safe = set(cfg.get("safe_tools", []))
                logger.info(f"安全配置已加载: enabled={self._enabled}, "
                            f"+dangerous={len(self._custom_dangerous)}, +safe={len(self._custom_safe)}")
            except Exception as e:
                logger.warning(f"安全配置加载失败: {e}")

    def _save_config(self) -> None:
        """保存安全配置。"""
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        cfg = {
            "enabled": self._enabled,
            "dangerous_tools": sorted(self._custom_dangerous),
            "safe_tools": sorted(self._custom_safe),
        }
        _CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))

    def classify(self, tool_name: str) -> str:
        """分类工具安全等级: 'dangerous' | 'sensitive' | 'safe'."""
        if tool_name in self._custom_safe:
            return "safe"
        if tool_name in self._custom_dangerous or tool_name in DANGEROUS_TOOLS:
            return "dangerous"
        if tool_name in SENSITIVE_TOOLS:
            return "sensitive"
        return "safe"

    def is_dangerous(self, tool_name: str) -> bool:
        return self.classify(tool_name) == "dangerous"

    def get_all_dangerous(self) -> list[str]:
        return sorted(DANGEROUS_TOOLS | self._custom_dangerous - self._custom_safe)

    async def check(self, session_id: str, tool_name: str, params: dict[str, Any]) -> dict:
        """检查工具是否需要审批。

        Returns:
            {"approved": True} — 可以执行
            {"approved": False, "reason": "..."} — 被拒绝或超时
        """
        if not self._enabled:
            return {"approved": True}

        level = self.classify(tool_name)

        # E2: /workspace 外文件操作自动升级为 DANGEROUS
        if level != "dangerous":
            outside = self._check_outside_workspace(tool_name, params)
            if outside:
                level = "dangerous"
                logger.info(f"E2: {tool_name} 操作工作目录外路径 → 升级为 DANGEROUS")

        if level == "safe":
            return {"approved": True}

        # SENSITIVE: 同 session 内已批准过的工具自动放行
        if level == "sensitive":
            approved_set = self._session_approved.get(session_id, set())
            if tool_name in approved_set:
                return {"approved": True}

        # 需要审批 — 推送到前端
        return await self._request_approval(session_id, tool_name, params, level)

    def _check_outside_workspace(self, tool_name: str, params: dict) -> bool:
        """E2: 检测文件操作是否涉及工作目录以外的路径。"""
        _FILE_TOOLS = {"write_file", "delete_file", "move_file", "read_file",
                       "list_directory", "run_script", "run_shell", "run_command"}
        if tool_name not in _FILE_TOOLS:
            return False
        workspace = str(Path(__file__).resolve().parent.parent.parent)
        for key in ("path", "file_path", "target", "directory", "cwd", "command"):
            val = params.get(key, "")
            if not val or not isinstance(val, str):
                continue
            try:
                resolved = str(Path(val).resolve())
            except Exception:
                continue
            if not resolved.startswith(workspace) and not resolved.startswith("/tmp") and not resolved.startswith("/private/tmp"):
                return True
        return False

    async def _request_approval(self, session_id: str, tool_name: str,
                                 params: dict, level: str) -> dict:
        """通过 WebSocket 推送审批请求，等待用户确认。"""
        request_id = f"approve_{int(time.time() * 1000)}_{tool_name}"

        # 如果没有 WebSocket 连接，自动放行（非交互式场景如 Daemon）
        if not self._ws_channel or not self._ws_channel._connections:
            logger.warning(f"无 WebSocket 连接，自动放行: {tool_name}")
            return {"approved": True}

        # 创建 Future 等待用户响应
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending[request_id] = future

        # 推送审批请求到前端
        approval_msg = {
            "type": "tool_approval_request",
            "request_id": request_id,
            "tool_name": tool_name,
            "params": {k: str(v)[:200] for k, v in params.items()},  # 截断敏感参数
            "level": level,
            "session_id": session_id,
        }

        # 广播到所有 WebSocket 连接
        for cid, ws in list(self._ws_channel._connections.items()):
            try:
                await ws.send_json(approval_msg)
            except Exception:
                pass

        logger.info(f"工具审批请求已发送: {tool_name} (level={level}, id={request_id})")

        # 等待用户响应（60 秒超时）
        try:
            result = await asyncio.wait_for(future, timeout=60.0)
            if result.get("approved"):
                # 记录 session 级别的批准（SENSITIVE 工具后续自动放行）
                if level == "sensitive":
                    self._session_approved.setdefault(session_id, set()).add(tool_name)
                logger.info(f"用户批准工具: {tool_name}")
            else:
                logger.info(f"用户拒绝工具: {tool_name}")
            return result
        except asyncio.TimeoutError:
            logger.warning(f"工具审批超时: {tool_name}")
            return {"approved": False, "reason": f"审批超时 (60秒)，工具 {tool_name} 未执行"}
        finally:
            self._pending.pop(request_id, None)

    def handle_approval_response(self, request_id: str, approved: bool, reason: str = "") -> bool:
        """处理来自前端的审批响应。"""
        future = self._pending.get(request_id)
        if not future or future.done():
            return False
        if approved:
            future.set_result({"approved": True})
        else:
            future.set_result({"approved": False, "reason": reason or "用户拒绝"})
        return True

    def clear_session(self, session_id: str) -> None:
        """清除 session 级别的审批记录。"""
        self._session_approved.pop(session_id, None)

    # ─────────── 配置管理 API ───────────

    def get_config(self) -> dict:
        return {
            "enabled": self._enabled,
            "dangerous_tools": sorted(DANGEROUS_TOOLS | self._custom_dangerous - self._custom_safe),
            "sensitive_tools": sorted(SENSITIVE_TOOLS - self._custom_safe),
            "custom_dangerous": sorted(self._custom_dangerous),
            "custom_safe": sorted(self._custom_safe),
        }

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._save_config()

    def add_dangerous(self, tool_name: str) -> None:
        self._custom_dangerous.add(tool_name)
        self._custom_safe.discard(tool_name)
        self._save_config()

    def add_safe(self, tool_name: str) -> None:
        self._custom_safe.add(tool_name)
        self._custom_dangerous.discard(tool_name)
        self._save_config()

    def reset_tool(self, tool_name: str) -> None:
        self._custom_dangerous.discard(tool_name)
        self._custom_safe.discard(tool_name)
        self._save_config()


# 全局单例
_guard = ToolSafetyGuard()


def get_safety_guard() -> ToolSafetyGuard:
    return _guard
