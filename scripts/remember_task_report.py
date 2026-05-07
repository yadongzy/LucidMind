"""Store durable memory candidates from a task report payload."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory.project_memory import ProjectMemoryIntegrator
from reports.task_reporter import TaskReport


def _split_items(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Remember durable candidates from task report fields")
    parser.add_argument("--root", default=str(ROOT), help="Project root")
    parser.add_argument("--project-id", default="lucidmind", help="Project identifier")
    parser.add_argument("--task-id", required=True, help="Task id")
    parser.add_argument("--title", required=True, help="Report title")
    parser.add_argument("--goal", default="", help="Task goal")
    parser.add_argument("--actions", default="", help="Semicolon-separated action entries")
    parser.add_argument("--files", default="", help="Semicolon-separated changed files")
    parser.add_argument("--tests", default="", help="Semicolon-separated test evidence entries")
    parser.add_argument("--risks", default="", help="Semicolon-separated risks")
    parser.add_argument("--decisions", default="", help="Semicolon-separated durable decisions")
    parser.add_argument("--result", default="partial", choices=["complete", "partial", "blocked"], help="Task result")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report = TaskReport(
        task_id=args.task_id,
        title=args.title,
        goal=args.goal,
        project_id=args.project_id,
        actions_taken=_split_items(args.actions),
        files_changed=_split_items(args.files),
        tests_run=_split_items(args.tests),
        risks=_split_items(args.risks),
        decisions_to_remember=_split_items(args.decisions),
        result=args.result,
    )
    integrator = ProjectMemoryIntegrator(root / "data" / "projects" / args.project_id / "project_memory.sqlite3")
    ids = integrator.remember_candidates(integrator.candidates_from_report(report))
    print(f"Remembered {len(ids)} memory candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
