"""Skills Plugin System — 标准化插件协议。

## 插件目录结构（推荐）：
    skills/my_plugin/
        manifest.json    # 插件描述（name, version, tools, enabled, kind...）
        main.py          # 入口文件，导出 XxxAdapter 类（kind="code"/"hybrid"）
        SKILL.md         # 知识文档（kind="prompt"/"hybrid"）

## 旧格式兼容：
    skills/my_tool.py    # 单文件插件（无manifest）

## 技能形态（kind 字段）：
    - "code"（默认）：加载 Python Adapter，提供可执行工具
    - "prompt"：只读取 SKILL.md，注入 LLM context 作为知识
    - "hybrid"：既加载代码又读取 SKILL.md

manifest.json 示例:
    {
      "name": "clipboard",
      "version": "1.0.0",
      "description": "系统剪贴板读写",
      "entry": "main.py",
      "kind": "code",
      "tools": ["clipboard_read", "clipboard_write"],
      "platform": ["darwin"],
      "dependencies": [],
      "enabled": true
    }

## 模块拆分：
    - registry.py   → 共享状态、验证、CRUD
    - discovery.py  → 插件发现与加载
    - reload.py     → 热加载 + MCP 生成 + 安全标记
    - hub.py        → PluginHub 搜索与安装
    - token_budget.py → Token 预算管理
"""

# --- 薄门面层：从子模块重新导出所有公共 API ---

from skills.registry import (  # noqa: F401
    _SKILLS_DIR,
    _registry,
    _BUILTIN_PLUGINS,
    _validate_plugin_name,
    is_builtin,
    get_registry,
    delete_plugin,
    set_plugin_enabled,
)

from skills.discovery import (  # noqa: F401
    discover_skills,
)

from skills.reload import (  # noqa: F401
    set_tool_adapter_ref,
    hot_reload,
    _auto_generate_mcp_server,
    _mark_new_skill_sensitive,
)

from skills.hub import (  # noqa: F401
    refresh_hub_registry,
    search_hub,
    install_from_hub,
)

from skills.token_budget import (  # noqa: F401
    filter_tools_by_budget,
    filter_prompt_skills,
    get_prompt_skills_content,
)
