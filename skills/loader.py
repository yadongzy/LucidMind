"""Skills Loader — 三层加载架构（对标 OpenClaw loader.ts）。

Layer 1 (启动时): 只读 manifest.json → 注册到 _registry (PluginMeta)
Layer 2 (按需):   读取 SKILL.md → 提供给 Brain 作为工具使用说明
Layer 3 (首次调用): 加载 Python 代码 → 实例化 Adapter → 注册到 CompositeToolAdapter
"""

import importlib
import importlib.util
import json
import pathlib
import platform
import time
from dataclasses import dataclass, field
from typing import Any

from logs import get_logger

logger = get_logger("skills.loader")

_SKILLS_DIR = pathlib.Path(__file__).parent


@dataclass
class PluginMeta:
    """Layer 1: 轻量元数据（只从 manifest.json 提取）。"""
    name: str
    version: str = "0.0.0"
    description: str = ""
    tool_names: list[str] = field(default_factory=list)
    platform: list[str] = field(default_factory=list)
    enabled: bool = True
    dependencies: list[str] = field(default_factory=list)
    entry: str = "main.py"
    path: pathlib.Path = field(default_factory=lambda: pathlib.Path("."))
    status: str = "registered"  # registered | loaded | active | error | disabled | platform_skip | security_blocked
    load_level: int = 1  # 1=metadata, 2=skill_doc, 3=full
    skill_doc: str | None = None  # Layer 2: SKILL.md 内容
    error: str | None = None
    security: dict | None = None
    adapters: list[Any] = field(default_factory=list)
    tools_actual: list[str] = field(default_factory=list)
    _manifest_raw: dict = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict:
        """转换为 API 可返回的 dict（排除 adapters 实例）。"""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "tool_names": self.tool_names,
            "platform": self.platform,
            "enabled": self.enabled,
            "dependencies": self.dependencies,
            "status": self.status,
            "load_level": self.load_level,
            "skill_doc": self.skill_doc,
            "error": self.error,
            "security": self.security,
            "tools_actual": self.tools_actual,
        }


# 全局 PluginMeta 注册表
_meta_registry: dict[str, PluginMeta] = {}


def layer1_scan() -> dict[str, PluginMeta]:
    """Layer 1: 扫描 skills/ 目录，只读 manifest.json 提取元数据。

    不加载任何 Python 代码，目标 < 100ms。
    """
    global _meta_registry
    _meta_registry = {}
    current_platform = platform.system().lower()
    t0 = time.time()

    for sub_dir in sorted(_SKILLS_DIR.iterdir()):
        if not sub_dir.is_dir() or sub_dir.name.startswith("_"):
            continue
        manifest_path = sub_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text("utf-8"))
            name = manifest.get("name", sub_dir.name)
            plats = manifest.get("platform", [])
            if isinstance(plats, str):
                plats = [plats]
            tool_names = manifest.get("tools", [])
            if isinstance(tool_names, str):
                tool_names = [tool_names]

            meta = PluginMeta(
                name=name,
                version=manifest.get("version", "0.0.0"),
                description=manifest.get("description", ""),
                tool_names=tool_names,
                platform=plats,
                enabled=manifest.get("enabled", True),
                dependencies=manifest.get("dependencies", []),
                entry=manifest.get("entry", "main.py"),
                path=sub_dir,
                _manifest_raw=manifest,
            )

            # 状态判定
            if not meta.enabled:
                meta.status = "disabled"
            elif plats and "all" not in [p.lower() for p in plats] and current_platform not in [p.lower() for p in plats]:
                meta.status = "platform_skip"
            else:
                meta.status = "registered"

            _meta_registry[name] = meta
        except Exception as e:
            logger.warning(f"Layer 1 扫描失败: {sub_dir.name} — {e}")
            _meta_registry[sub_dir.name] = PluginMeta(
                name=sub_dir.name, path=sub_dir, status="error", error=str(e)
            )

    elapsed = (time.time() - t0) * 1000
    logger.info(f"Layer 1 扫描完成: {len(_meta_registry)} 个插件 ({elapsed:.1f}ms)")
    return _meta_registry


def layer2_load_skill_doc(name: str) -> str | None:
    """Layer 2: 读取 SKILL.md 技能描述文档。

    最多 2000 字符，超出自动截断。
    """
    meta = _meta_registry.get(name)
    if not meta:
        return None
    if meta.load_level >= 2 and meta.skill_doc is not None:
        return meta.skill_doc

    skill_md = meta.path / "SKILL.md"
    if not skill_md.exists():
        meta.load_level = max(meta.load_level, 2)
        return None

    try:
        content = skill_md.read_text("utf-8")
        if len(content) > 2000:
            content = content[:2000] + "\n...(已截断)"
        meta.skill_doc = content
        meta.load_level = max(meta.load_level, 2)
        logger.info(f"Layer 2 加载: {name} SKILL.md ({len(content)} chars)")
        return content
    except Exception as e:
        logger.warning(f"Layer 2 加载失败: {name} — {e}")
        return None


def layer3_full_load(name: str) -> list[Any]:
    """Layer 3: 完整加载 Python 代码，实例化 Adapter。

    首次工具调用时触发。
    """
    meta = _meta_registry.get(name)
    if not meta:
        return []
    if meta.load_level >= 3 and meta.adapters:
        return meta.adapters
    if meta.status in ("disabled", "platform_skip", "security_blocked", "error"):
        return []

    entry_path = meta.path / meta.entry
    if not entry_path.exists():
        meta.status = "error"
        meta.error = f"入口文件不存在: {meta.entry}"
        return []

    try:
        # 安全检查
        try:
            from skills.discovery_safety import check_plugin_safety
            safety = check_plugin_safety(meta.path)
            meta.security = safety
            if safety.get("blocked"):
                meta.status = "security_blocked"
                meta.error = safety.get("blocked_reason", "安全检查未通过")
                logger.warning(f"Layer 3 安全阻断: {name} — {meta.error}")
                return []
        except ImportError:
            pass

        module_name = f"skills.{meta.path.name}.{entry_path.stem}"
        adapters = _load_adapter_from_file(entry_path, module_name)
        meta.adapters = adapters
        meta.tools_actual = []
        for a in adapters:
            meta.tools_actual.extend(t["function"]["name"] for t in a.list_tools())
        meta.status = "active"
        meta.load_level = 3
        logger.info(f"Layer 3 加载: {name} → {', '.join(meta.tools_actual)}")

        try:
            from diagnostics import record_event
            record_event("plugin_load", "layer3_load", "success", 0,
                         input_summary=f"plugin={name}",
                         output_summary=f"tools={','.join(meta.tools_actual)}")
        except Exception:
            pass

        return adapters
    except Exception as e:
        meta.status = "error"
        meta.error = str(e)
        logger.warning(f"Layer 3 加载失败: {name} — {e}")
        try:
            from diagnostics import record_event
            record_event("plugin_load", "layer3_load", "failure", 0,
                         input_summary=f"plugin={name}", error=str(e)[:200])
        except Exception:
            pass
        return []


def find_plugin_by_tool(tool_name: str) -> str | None:
    """根据工具名查找对应的插件（用于懒加载）。"""
    for name, meta in _meta_registry.items():
        if tool_name in meta.tool_names:
            return name
    return None


def get_meta_registry() -> dict[str, PluginMeta]:
    """返回 PluginMeta 注册表。"""
    return _meta_registry


def get_registry_dict() -> dict[str, dict]:
    """返回 API 可用的注册表 dict。"""
    return {name: meta.to_dict() for name, meta in _meta_registry.items()}


def _load_adapter_from_file(py_path: pathlib.Path, module_name: str) -> list[Any]:
    """从 Python 文件加载所有 Adapter 类实例。"""
    adapters = []
    spec = importlib.util.spec_from_file_location(module_name, py_path)
    if not spec or not spec.loader:
        return adapters
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for attr_name in dir(mod):
        if attr_name.endswith("Adapter") and attr_name != "ToolPort":
            cls = getattr(mod, attr_name)
            if hasattr(cls, "list_tools") and hasattr(cls, "execute"):
                adapters.append(cls())
    return adapters
