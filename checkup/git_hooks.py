"""Git Hook Integration — 将自愈引擎集成到 Git 工作流。

提供:
- pre-commit: 快速体检，阻止低质量提交
- post-merge: 自动修复合并引入的问题
- install_hooks(): 一键安装 git hooks
- uninstall_hooks(): 卸载

用法:
    python -m checkup.git_hooks install
    python -m checkup.git_hooks uninstall
    python -m checkup.git_hooks pre-commit
    python -m checkup.git_hooks post-merge
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("checkup.git_hooks")

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()

PRE_COMMIT_SCRIPT = '''#!/bin/sh
# LucidMind pre-commit hook — 快速代码体检
# 自动安装: python -m checkup.git_hooks install
python -m checkup.git_hooks pre-commit
exit $?
'''

POST_MERGE_SCRIPT = '''#!/bin/sh
# LucidMind post-merge hook — 自动修复合并引入的问题
# 自动安装: python -m checkup.git_hooks install
python -m checkup.git_hooks post-merge &
'''


def install_hooks(project_root: Path | None = None) -> dict[str, Any]:
    """安装 git hooks 到 .git/hooks/。"""
    root = project_root or _PROJECT_ROOT
    hooks_dir = root / ".git" / "hooks"

    if not hooks_dir.exists():
        return {"success": False, "error": ".git/hooks not found"}

    results = {}

    # pre-commit
    pre_commit_path = hooks_dir / "pre-commit"
    _write_hook(pre_commit_path, PRE_COMMIT_SCRIPT)
    results["pre-commit"] = str(pre_commit_path)

    # post-merge
    post_merge_path = hooks_dir / "post-merge"
    _write_hook(post_merge_path, POST_MERGE_SCRIPT)
    results["post-merge"] = str(post_merge_path)

    logger.info(f"Git hooks 已安装: {list(results.keys())}")
    return {"success": True, "hooks": results}


def uninstall_hooks(project_root: Path | None = None) -> dict[str, Any]:
    """卸载 LucidMind git hooks。"""
    root = project_root or _PROJECT_ROOT
    hooks_dir = root / ".git" / "hooks"
    removed = []

    for name in ("pre-commit", "post-merge"):
        hook_path = hooks_dir / name
        if hook_path.exists():
            content = hook_path.read_text(errors="ignore")
            if "LucidMind" in content:
                hook_path.unlink()
                removed.append(name)

    logger.info(f"Git hooks 已卸载: {removed}")
    return {"success": True, "removed": removed}


def run_pre_commit() -> int:
    """pre-commit hook 逻辑: 快速体检，分数低于阈值则阻止提交。"""
    from checkup.self_heal import SelfHealEngine

    threshold = 60  # 低于此分数阻止提交
    engine = SelfHealEngine(_PROJECT_ROOT)

    t0 = time.perf_counter()
    check = engine.quick_check()
    elapsed = (time.perf_counter() - t0) * 1000

    score = check["score"]
    issues = check["issues_count"]

    if score < threshold:
        print(f"\n❌ LucidMind pre-commit: 健康分数 {score}/100 (阈值 {threshold})")
        print(f"   问题数: {issues}")
        print(f"   运行 'python -m checkup.self_heal' 自动修复")
        print(f"   或使用 --no-verify 跳过\n")
        return 1

    icon = "✅" if score >= 80 else "⚠️"
    print(f"{icon} LucidMind: {score}/100 ({elapsed:.0f}ms)")
    return 0


def run_post_merge() -> int:
    """post-merge hook 逻辑: 检查合并后健康，必要时自愈。"""
    from checkup.self_heal import SelfHealEngine

    engine = SelfHealEngine(_PROJECT_ROOT)
    result = engine.heal_changed_files(trigger="post_merge")

    if result.improved:
        print(f"🔧 LucidMind post-merge: 自动修复 {result.original_score}→{result.final_score}")
    elif result.errors:
        print(f"⚠️ LucidMind post-merge: 自愈出错 ({result.errors[0][:60]})")
    else:
        print(f"✅ LucidMind post-merge: 健康正常 ({result.final_score}/100)")

    return 0


def _write_hook(path: Path, content: str):
    """写入 hook 脚本并设置可执行权限。"""
    path.write_text(content)
    path.chmod(0o755)


# ─────────────── CLI Entry ───────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m checkup.git_hooks [install|uninstall|pre-commit|post-merge]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "install":
        result = install_hooks()
        if result["success"]:
            print(f"✅ Hooks installed: {list(result['hooks'].keys())}")
        else:
            print(f"❌ {result['error']}")
            sys.exit(1)

    elif cmd == "uninstall":
        result = uninstall_hooks()
        print(f"✅ Hooks removed: {result['removed']}")

    elif cmd == "pre-commit":
        sys.exit(run_pre_commit())

    elif cmd == "post-merge":
        sys.exit(run_post_merge())

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
