"""Skills Discovery — 扫描并加载插件。

拆分自 skills/__init__.py，负责插件发现与加载。
支持三种技能形态：code（代码执行）、prompt（知识文档）、hybrid（两者兼备）。
"""

import importlib
import importlib.util
import json
import platform
from typing import Any

from logs import get_logger
from skills.registry import _SKILLS_DIR, _registry

logger = get_logger("skills.discovery")


def _load_adapter_from_file(py_path, module_name: str) -> list[Any]:
    """从Python文件加载所有 Adapter 类实例。"""
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


def _load_prompt_skill(sub_dir, manifest: dict) -> dict | None:
    """加载 prompt 型技能（只读取 SKILL.md，不加载 Python 代码）。

    改进2: 支持 kind: "prompt" 技能形态。
    """
    skill_md_name = manifest.get("skill_md", "SKILL.md")
    skill_md_path = sub_dir / skill_md_name
    if not skill_md_path.exists():
        logger.warning(f"⚠️ prompt 技能缺少 {skill_md_name}: {manifest.get('name', sub_dir.name)}")
        return None
    try:
        prompt_content = skill_md_path.read_text("utf-8")
        return {
            "prompt_content": prompt_content,
            "prompt_tokens": len(prompt_content),
        }
    except Exception as e:
        logger.warning(f"❌ 读取 SKILL.md 失败: {sub_dir.name} — {e}")
        return None


def discover_skills() -> list[Any]:
    """扫描 skills/ 目录，加载所有插件（manifest目录 + 旧格式单文件）。

    支持三种 kind：
    - "code"（默认）：加载 Python Adapter，提供可执行工具
    - "prompt"：只读取 SKILL.md，注入 LLM context 作为知识
    - "hybrid"：既加载代码又读取 SKILL.md
    """
    _registry.clear()
    all_adapters = []
    current_platform = platform.system().lower()

    # 1. 扫描子目录（新格式：含 manifest.json）
    for sub_dir in sorted(_SKILLS_DIR.iterdir()):
        if not sub_dir.is_dir() or sub_dir.name.startswith("_"):
            continue
        manifest_path = sub_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            # Safety by Default: 加载前安全检查
            from skills.discovery_safety import check_plugin_safety
            safety = check_plugin_safety(sub_dir)
            if safety["blocked"]:
                logger.warning(f"🛡️ 插件安全阻断: {sub_dir.name} — {safety['blocked_reason']}")
                _registry[sub_dir.name] = {"name": sub_dir.name, "status": "security_blocked",
                                           "security": safety, "adapters": []}
                continue

            manifest = json.loads(manifest_path.read_text("utf-8"))
            name = manifest.get("name", sub_dir.name)
            kind = manifest.get("kind", "code")

            if not manifest.get("enabled", True):
                logger.info(f"⏸️  插件已禁用: {name}")
                _registry[name] = {**manifest, "status": "disabled", "adapters": [], "security": safety}
                continue
            # 平台检查（"all" 匹配所有平台）
            plats = manifest.get("platform", [])
            if isinstance(plats, str):
                plats = [plats]
            if plats and "all" not in [p.lower() for p in plats] and current_platform not in [p.lower() for p in plats]:
                logger.info(f"⏭️  插件跳过(平台不匹配): {name} 需要 {plats}")
                _registry[name] = {**manifest, "status": "platform_skip", "adapters": []}
                continue

            # --- prompt 型技能：只读取 SKILL.md，不加载代码 ---
            if kind == "prompt":
                prompt_data = _load_prompt_skill(sub_dir, manifest)
                if prompt_data:
                    _registry[name] = {**manifest, "status": "loaded", "kind": "prompt",
                                       "adapters": [], "security": safety, **prompt_data}
                    logger.info(f"✅ 加载知识技能: {name} v{manifest.get('version', '?')} "
                                f"[📄prompt {prompt_data['prompt_tokens']}字符]")
                continue

            # --- code / hybrid 型技能：加载 Python 代码 ---
            entry = manifest.get("entry", "main.py")
            entry_path = sub_dir / entry
            if not entry_path.exists():
                logger.warning(f"❌ 插件入口不存在: {name}/{entry}")
                continue
            trust_level = manifest.get("trust_level", "audited")
            if trust_level == "sandboxed":
                # Level 2: 子进程隔离执行
                from adapters.tools.subprocess_skill import SubprocessSkillAdapter
                adapter = SubprocessSkillAdapter(sub_dir, manifest)
                adapters = [adapter]
                tools = manifest.get("tools", [])
                mode = "🔒subprocess"
            else:
                # Level 0/1: 进程内执行
                module_name = f"skills.{sub_dir.name}.{entry_path.stem}"
                adapters = _load_adapter_from_file(entry_path, module_name)
                tools = []
                for a in adapters:
                    tools.extend(t["function"]["name"] for t in a.list_tools())
                mode = "⚡in-process"
            all_adapters.extend(adapters)

            # hybrid 型：同时读取 SKILL.md
            extra = {}
            if kind == "hybrid":
                prompt_data = _load_prompt_skill(sub_dir, manifest)
                if prompt_data:
                    extra = prompt_data
                    mode += "+📄prompt"

            _registry[name] = {**manifest, "status": "loaded", "tools_actual": tools,
                               "adapters": adapters, "security": safety, "trust_level": trust_level,
                               "kind": kind, **extra}
            logger.info(f"✅ 加载插件: {name} v{manifest.get('version', '?')} [{mode}] → {', '.join(tools)}")
            try:
                from diagnostics import record_event
                record_event("plugin_load", "discover", "success", 0, input_summary=f"plugin={name}", output_summary=f"tools={','.join(tools)}")
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"❌ 加载插件失败: {sub_dir.name} — {e}")
            try:
                from diagnostics import record_event
                record_event("plugin_load", "discover", "failure", 0, input_summary=f"plugin={sub_dir.name}", error=str(e)[:200])
            except Exception:
                pass

    # 2. 扫描单文件（旧格式兼容）
    for py_file in sorted(_SKILLS_DIR.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        name = py_file.stem
        if name in _registry:
            continue
        try:
            module_name = f"skills.{name}"
            adapters = _load_adapter_from_file(py_file, module_name)
            all_adapters.extend(adapters)
            tools = []
            for a in adapters:
                tools.extend(t["function"]["name"] for t in a.list_tools())
            _registry[name] = {
                "name": name, "version": "0.0.0", "description": f"旧格式插件: {name}",
                "status": "loaded", "tools_actual": tools, "adapters": adapters, "enabled": True,
                "legacy": True, "kind": "code",
            }
            logger.info(f"✅ 加载技能(旧格式): {name} → {', '.join(tools)}")
        except Exception as e:
            logger.warning(f"❌ 加载技能失败: {py_file.name} — {e}")

    logger.info(f"🎯 共加载 {len(all_adapters)} 个插件适配器 ({len(_registry)} 个插件)")
    return all_adapters
