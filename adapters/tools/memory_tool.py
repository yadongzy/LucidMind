"""Memory Tool Adapter — Agent 自主记忆管理工具（对标 Letta memory() 工具）。

让 Agent 通过工具自主决定何时读/写/追加记忆块，
实现"边研究边写入"的增量记忆更新模式。

工具:
- memory_read:   读取指定块或列出所有块
- memory_write:  覆盖写入块内容
- memory_append: 增量追加内容（适合研究过程中逐步记录）
"""

from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools.memory")


class MemoryToolAdapter(ToolPort):
    """Agent 自主记忆管理工具适配器。"""

    def __init__(self, block_manager=None):
        self._bm = block_manager

    def set_block_manager(self, bm) -> None:
        """注入 BlockManager（由 startup.py 调用）。"""
        self._bm = bm

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "memory_read",
                    "description": "读取记忆块。不指定 name 时列出所有块概览。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "块名称（persona/human/project 等）。留空列出所有块。",
                            }
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_write",
                    "description": "覆盖写入记忆块内容。用于更新用户偏好、项目信息等核心记忆。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "块名称",
                            },
                            "value": {
                                "type": "string",
                                "description": "新内容（完整替换）",
                            },
                        },
                        "required": ["name", "value"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_append",
                    "description": "向记忆块追加内容（增量写入）。适合边研究边记录发现。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "块名称",
                            },
                            "text": {
                                "type": "string",
                                "description": "追加的文本",
                            },
                        },
                        "required": ["name", "text"],
                    },
                },
            },
        ]

    async def execute(self, tool_name: str, params: dict[str, Any],
                      **kwargs) -> dict[str, Any]:
        if not self._bm:
            return {"success": False, "result": None,
                    "error": "BlockManager 未初始化"}
        try:
            if tool_name == "memory_read":
                return self._read(params)
            elif tool_name == "memory_write":
                return self._write(params)
            elif tool_name == "memory_append":
                return self._append(params)
            return {"success": False, "result": None,
                    "error": f"未知工具: {tool_name}"}
        except PermissionError as e:
            return {"success": False, "result": None, "error": str(e)}
        except KeyError as e:
            return {"success": False, "result": None, "error": str(e)}
        except Exception as e:
            logger.warning(f"memory tool error: {e}")
            return {"success": False, "result": None, "error": str(e)}

    def _read(self, params: dict) -> dict[str, Any]:
        name = params.get("name")
        if name:
            block = self._bm.get(name)
            if not block:
                return {"success": False, "result": None,
                        "error": f"Block '{name}' not found"}
            return {"success": True, "result": block.to_dict(), "error": None}
        # 列出所有块（只返回摘要，不返回完整 value）
        blocks = []
        for b in self._bm.list_blocks():
            blocks.append({
                "name": b.name, "label": b.label,
                "char_count": len(b.value), "limit": b.limit,
                "usage": round(b.usage, 2), "read_only": b.read_only,
                "description": b.description,
            })
        return {"success": True,
                "result": {"blocks": blocks, "total": len(blocks)},
                "error": None}

    def _write(self, params: dict) -> dict[str, Any]:
        name = params.get("name", "")
        value = params.get("value", "")
        block = self._bm.update(name, value)
        logger.info(f"memory_write: {name} ({len(value)} chars)")
        return {"success": True, "result": block.to_dict(), "error": None}

    def _append(self, params: dict) -> dict[str, Any]:
        name = params.get("name", "")
        text = params.get("text", "")
        block = self._bm.append(name, text)
        logger.info(f"memory_append: {name} (+{len(text)} chars)")
        return {"success": True, "result": block.to_dict(), "error": None}
