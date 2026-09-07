"""Plugin Discovery Safety — 插件发现阶段安全检查。

对标 OpenClaw discovery.ts 的安全检查：
- 路径逃逸检测（symlink / resolve）
- 权限检查（world-writable 拒绝）
- 所有权检查（非当前用户拒绝）
- 符号链接拒绝（manifest.json / main.py）
- 文件大小限制（>500KB 警告）
"""

import os
import stat
import pathlib
from typing import Any

from logs import get_logger

logger = get_logger("security")

_SKILLS_DIR = pathlib.Path(__file__).parent.resolve()
_MAX_PY_FILE_SIZE = 500 * 1024  # 500KB


def check_plugin_safety(plugin_dir: pathlib.Path) -> dict[str, Any]:
    """检查插件目录的安全性。

    Returns:
        {
            "safe": bool,
            "blocked": bool,
            "checks": [{"name": str, "passed": bool, "detail": str}, ...],
            "blocked_reason": str | None,
        }
    """
    checks: list[dict] = []
    blocked = False
    blocked_reason = None

    resolved = plugin_dir.resolve()

    # 1. 路径逃逸检测
    path_ok = str(resolved).startswith(str(_SKILLS_DIR))
    checks.append({
        "name": "path_escape",
        "passed": path_ok,
        "detail": f"resolved={resolved}" if not path_ok else "ok",
    })
    if not path_ok:
        blocked = True
        blocked_reason = f"路径逃逸: {resolved} 不在 {_SKILLS_DIR} 内"

    # 2. 符号链接拒绝（manifest.json 和入口文件）
    for fname in ("manifest.json", "main.py"):
        fpath = plugin_dir / fname
        if fpath.exists() and fpath.is_symlink():
            checks.append({
                "name": "symlink",
                "passed": False,
                "detail": f"{fname} 是符号链接 → {os.readlink(fpath)}",
            })
            blocked = True
            blocked_reason = f"{fname} 是符号链接（安全风险）"
        else:
            checks.append({
                "name": "symlink",
                "passed": True,
                "detail": f"{fname} ok",
            })

    # 3. 权限检查（world-writable）— 仅 Unix
    if hasattr(os, "stat"):
        try:
            dir_stat = os.stat(resolved)
            world_writable = bool(dir_stat.st_mode & stat.S_IWOTH)
            checks.append({
                "name": "world_writable",
                "passed": not world_writable,
                "detail": f"mode={oct(dir_stat.st_mode)}" if world_writable else "ok",
            })
            if world_writable:
                blocked = True
                blocked_reason = f"插件目录 world-writable: {oct(dir_stat.st_mode)}"
        except OSError as e:
            checks.append({
                "name": "world_writable",
                "passed": True,
                "detail": f"stat 失败(跳过): {e}",
            })

    # 4. 所有权检查 — 仅 Unix
    if hasattr(os, "getuid"):
        try:
            dir_stat = os.stat(resolved)
            current_uid = os.getuid()
            owner_ok = dir_stat.st_uid in (current_uid, 0)  # 当前用户或 root
            checks.append({
                "name": "ownership",
                "passed": owner_ok,
                "detail": f"owner_uid={dir_stat.st_uid}, current_uid={current_uid}" if not owner_ok else "ok",
            })
            if not owner_ok:
                blocked = True
                blocked_reason = f"插件目录所有者不是当前用户: uid={dir_stat.st_uid}"
        except OSError as e:
            checks.append({
                "name": "ownership",
                "passed": True,
                "detail": f"stat 失败(跳过): {e}",
            })

    # 5. 文件大小检查（.py 文件 > 500KB 警告）
    large_files = []
    try:
        for py_file in resolved.rglob("*.py"):
            if py_file.stat().st_size > _MAX_PY_FILE_SIZE:
                large_files.append(f"{py_file.name}({py_file.stat().st_size // 1024}KB)")
    except OSError:
        pass
    checks.append({
        "name": "file_size",
        "passed": len(large_files) == 0,
        "detail": f"大文件: {', '.join(large_files)}" if large_files else "ok",
    })
    # 大文件仅警告，不阻断

    safe = not blocked and all(c["passed"] for c in checks)

    if blocked:
        logger.warning(f"🛡️ 插件安全检查失败: {plugin_dir.name} — {blocked_reason}")
    elif not safe:
        logger.info(f"🛡️ 插件安全检查警告: {plugin_dir.name} — {[c for c in checks if not c['passed']]}")

    return {
        "safe": safe,
        "blocked": blocked,
        "checks": checks,
        "blocked_reason": blocked_reason,
    }
