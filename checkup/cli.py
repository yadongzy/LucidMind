"""Checkup CLI — 命令行体检入口。

用法:
    python -m checkup            # 运行全部体检
    python -m checkup --json     # 输出 JSON 格式
    python -m checkup --save     # 保存报告到 data/checkup/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from checkup.runner import ProjectCheckupRunner


def main():
    parser = argparse.ArgumentParser(description="LucidMind 项目体检")
    parser.add_argument("--project-id", default="lucidmind", help="项目 ID")
    parser.add_argument("--root", default=str(Path(__file__).parent.parent),
                       help="项目根目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--save", action="store_true", help="保存报告到文件")
    args = parser.parse_args()

    runner = ProjectCheckupRunner(args.root, args.project_id)
    report = runner.run_all()

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(report.to_markdown())

    if args.save:
        save_dir = Path(args.root) / "data" / "checkup"
        save_dir.mkdir(parents=True, exist_ok=True)

        # JSON
        json_path = save_dir / f"report_{report.timestamp[:10]}.json"
        json_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # Markdown
        md_path = save_dir / f"report_{report.timestamp[:10]}.md"
        md_path.write_text(report.to_markdown(), encoding="utf-8")

        print(f"\n📁 报告已保存: {json_path}")
        print(f"📁 报告已保存: {md_path}")

    # 返回码: 有 fail 则非零
    if report.summary.get("fail", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
