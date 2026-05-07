"""Letta-style Memory Blocks — 命名记忆块 + Block 分裂 + 增量更新。

对标 Letta Memory Block 范式：
- 命名文本块直注 system prompt（零延迟核心记忆）
- 字符限制防止无限增长
- 受保护块防止 Agent 意外破坏
- 大块自动分裂为子块
- Agent 通过工具自主管理记忆

Block 类型:
- persona: AI 人格/身份（read_only）
- human:   用户画像/偏好
- project: 项目上下文/架构/约定
- 自定义:  任意命名块
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("memory.blocks")

_DEFAULT_LIMIT = 2000
_BLOCKS_PATH = Path(__file__).parent.parent / "data" / "memory" / "blocks.json"


@dataclass
class MemoryBlock:
    """Letta-style 命名记忆块。"""
    name: str
    label: str = ""
    value: str = ""
    description: str = ""
    limit: int = _DEFAULT_LIMIT
    read_only: bool = False
    updated_at: float = 0.0

    @property
    def usage(self) -> float:
        """使用率 (0.0 ~ 1.0)。"""
        return len(self.value) / self.limit if self.limit > 0 else 0.0

    @property
    def is_full(self) -> bool:
        return len(self.value) >= self.limit

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "label": self.label, "value": self.value,
            "description": self.description, "limit": self.limit,
            "read_only": self.read_only, "updated_at": self.updated_at,
            "char_count": len(self.value), "usage": round(self.usage, 2),
        }


class BlockManager:
    """管理命名记忆块集合。

    支持:
    - 读/写/追加命名块
    - 受保护块（read_only）
    - 字符限制 + 自动截断
    - Block 分裂（大块拆为子块）
    - 持久化到 JSON
    """

    def __init__(self, persist_path: Path | None = None):
        self._blocks: dict[str, MemoryBlock] = {}
        self._persist_path = persist_path or _BLOCKS_PATH
        self._load()

    # ─── 持久化 ───

    def _load(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text("utf-8"))
            valid_fields = set(MemoryBlock.__dataclass_fields__.keys())
            for bd in data.get("blocks", []):
                kwargs = {k: v for k, v in bd.items() if k in valid_fields}
                block = MemoryBlock(**kwargs)
                self._blocks[block.name] = block
            logger.debug(f"加载 {len(self._blocks)} 个记忆块")
        except Exception as e:
            logger.warning(f"记忆块加载失败: {e}")

    def _save(self) -> None:
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = {"blocks": [b.to_dict() for b in self._blocks.values()],
                    "saved_at": time.time()}
            self._persist_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"记忆块保存失败: {e}")

    # ─── 默认块 ───

    def ensure_defaults(self) -> None:
        """确保默认块存在（不覆盖已有内容）。"""
        defaults = [
            MemoryBlock(name="persona", label="AI 人格",
                        description="AI 的身份、性格、行为准则",
                        limit=1000, read_only=True),
            MemoryBlock(name="human", label="用户画像",
                        description="用户的基本信息、偏好、习惯",
                        limit=2000),
            MemoryBlock(name="project", label="项目上下文",
                        description="当前项目的关键信息、架构、约定",
                        limit=3000),
        ]
        changed = False
        for d in defaults:
            if d.name not in self._blocks:
                self._blocks[d.name] = d
                changed = True
        if changed:
            self._save()

    def sync_human_block_from_profile(self, user_id: str = "default") -> bool:
        """P2: 从 UserProfile 自动同步 human block 内容。

        仅在 human block 为空时填充，不覆盖用户手动设置的内容。
        """
        human = self._blocks.get("human")
        if not human or human.value.strip():
            return False  # 已有内容，不覆盖
        try:
            from adapters.memory.user_profile import UserProfileAdapter
            profile_adapter = UserProfileAdapter()
            prompt = profile_adapter.get_context_prompt(user_id)
            if prompt and len(prompt) > 10:
                human.value = prompt[:human.limit]
                human.updated_at = time.time()
                self._save()
                logger.info(f"human block 已从 UserProfile 同步 ({len(prompt)} chars)")
                return True
        except Exception as e:
            logger.debug(f"human block 同步跳过: {e}")
        return False

    # ─── CRUD ───

    def get(self, name: str) -> MemoryBlock | None:
        return self._blocks.get(name)

    def list_blocks(self) -> list[MemoryBlock]:
        return list(self._blocks.values())

    def create(self, name: str, label: str = "", value: str = "",
               description: str = "", limit: int = _DEFAULT_LIMIT,
               read_only: bool = False) -> MemoryBlock:
        """创建新块。"""
        if name in self._blocks:
            raise ValueError(f"Block '{name}' already exists")
        block = MemoryBlock(name=name, label=label, value=value,
                            description=description, limit=limit,
                            read_only=read_only, updated_at=time.time())
        self._blocks[name] = block
        self._save()
        logger.info(f"创建记忆块: {name} (limit={limit})")
        return block

    def update(self, name: str, value: str) -> MemoryBlock:
        """覆盖写入块内容。"""
        block = self._blocks.get(name)
        if not block:
            raise KeyError(f"Block '{name}' not found")
        if block.read_only:
            raise PermissionError(f"Block '{name}' is read-only")
        if len(value) > block.limit:
            value = value[:block.limit]
            logger.warning(f"Block '{name}' 内容截断到 {block.limit} 字符")
        block.value = value
        block.updated_at = time.time()
        self._save()
        return block

    def append(self, name: str, text: str) -> MemoryBlock:
        """追加内容到块（增量更新，适合边研究边记录）。"""
        block = self._blocks.get(name)
        if not block:
            raise KeyError(f"Block '{name}' not found")
        if block.read_only:
            raise PermissionError(f"Block '{name}' is read-only")
        new_value = block.value + text
        if len(new_value) > block.limit:
            # 大块可分裂
            if self._should_split(block, new_value):
                return self.split_block(name, new_value)
            new_value = new_value[:block.limit]
            logger.warning(f"Block '{name}' append 后截断到 {block.limit} 字符")
        block.value = new_value
        block.updated_at = time.time()
        self._save()
        return block

    def delete(self, name: str) -> bool:
        """删除块（受保护块不可删除）。"""
        block = self._blocks.get(name)
        if not block:
            return False
        if block.read_only:
            raise PermissionError(f"Block '{name}' is read-only")
        del self._blocks[name]
        self._save()
        return True

    # ─── Block 分裂 ───

    def _should_split(self, block: MemoryBlock, new_value: str) -> bool:
        """判断是否应该分裂（仅 project 类块支持分裂）。"""
        return (len(new_value) > block.limit * 1.2
                and not block.read_only
                and block.name in ("project",)
                or block.name.startswith("project"))

    def split_block(self, name: str, content: str | None = None) -> MemoryBlock:
        """将大块按段落分裂为子块。

        分裂策略:
        - 按 \\n\\n 分段
        - 原块保留第一段
        - 溢出部分创建 {name}-overview, {name}-details, {name}-notes 子块
        """
        block = self._blocks.get(name)
        if not block:
            raise KeyError(f"Block '{name}' not found")

        text = content or block.value
        if len(text) <= block.limit:
            if content:
                block.value = text
                block.updated_at = time.time()
                self._save()
            return block

        # 按段落切分
        paragraphs = text.split("\n\n")
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for para in paragraphs:
            if current_len + len(para) + 2 > block.limit and current:
                chunks.append("\n\n".join(current))
                current = [para]
                current_len = len(para)
            else:
                current.append(para)
                current_len += len(para) + 2
        if current:
            chunks.append("\n\n".join(current))

        # 更新原块
        block.value = chunks[0][:block.limit]
        block.updated_at = time.time()

        # 创建子块
        suffixes = ["overview", "details", "notes", "extra"]
        for i, chunk in enumerate(chunks[1:], 1):
            suffix = suffixes[i - 1] if i <= len(suffixes) else f"part{i}"
            sub_name = f"{name}-{suffix}"
            if sub_name in self._blocks:
                self._blocks[sub_name].value = chunk[:block.limit]
                self._blocks[sub_name].updated_at = time.time()
            else:
                self._blocks[sub_name] = MemoryBlock(
                    name=sub_name, label=f"{block.label} ({suffix})",
                    value=chunk[:block.limit],
                    description=f"从 {name} 自动分裂",
                    limit=block.limit, updated_at=time.time())

        self._save()
        logger.info(f"Block '{name}' 分裂: 1 → {len(chunks)} 块")
        return block

    # ─── Prompt 格式化 ───

    def format_for_prompt(self) -> str:
        """格式化所有非空块为 system prompt 注入文本。

        输出格式:
            <persona>
            ...内容...
            </persona>
            <human>
            ...内容...
            </human>
        """
        lines: list[str] = []
        for block in self._blocks.values():
            if not block.value.strip():
                continue
            lines.append(f"<{block.name}>")
            lines.append(block.value.strip())
            lines.append(f"</{block.name}>")
        return "\n".join(lines) if lines else ""
