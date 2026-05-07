"""自动发现 adapters/tools/ 下的工具适配器。

扫描目录下所有 .py 文件，找到 ToolPort 子类并自动实例化。
消灭"工具实现了但没注册"的问题。

排除规则：
- composite.py / tool_safety.py — 基础设施，不是工具
- 需要构造参数的类（SubAgentAdapter、MCPClientAdapter）单独处理
- _deprecated/ 目录跳过
"""

import importlib
import inspect
import os
import pkgutil

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools.discover")

# 不自动发现的模块（需要特殊初始化或不是工具）
_SKIP_MODULES = {"composite", "tool_safety", "discover", "__init__"}

# 需要构造参数的类 → 不自动实例化，由 api/main.py 手动创建
_MANUAL_CLASSES = {"SubAgentAdapter", "CompositeToolAdapter", "MCPClientAdapter",
                   "ToolSafetyGuard", "StdioMCPClient", "HttpMCPClient"}


def discover_tool_adapters() -> list[ToolPort]:
    """扫描 adapters/tools/ 目录，自动发现并实例化所有工具适配器。

    Returns:
        已实例化的 ToolPort 列表（不含需要手动初始化的特殊类）
    """
    tools_dir = os.path.dirname(__file__)
    adapters: list[ToolPort] = []
    seen_classes: set[str] = set()

    for _, module_name, is_pkg in pkgutil.iter_modules([tools_dir]):
        if module_name in _SKIP_MODULES or module_name.startswith("_"):
            continue

        try:
            mod = importlib.import_module(f"adapters.tools.{module_name}")
        except Exception as e:
            logger.warning(f"跳过模块 {module_name}: {e}")
            continue

        for attr_name in dir(mod):
            cls = getattr(mod, attr_name)
            if (inspect.isclass(cls)
                    and issubclass(cls, ToolPort)
                    and cls is not ToolPort
                    and cls.__name__ not in _MANUAL_CLASSES
                    and cls.__name__ not in seen_classes):
                seen_classes.add(cls.__name__)
                try:
                    instance = cls()
                    adapters.append(instance)
                    tool_names = [t["function"]["name"] for t in instance.list_tools()]
                    logger.info(f"自动发现: {cls.__name__} → {tool_names}")
                except Exception as e:
                    logger.warning(f"实例化 {cls.__name__} 失败: {e}")

    logger.info(f"自动发现完成: {len(adapters)} 个工具适配器, "
                f"{sum(len(a.list_tools()) for a in adapters)} 个工具")
    return adapters
