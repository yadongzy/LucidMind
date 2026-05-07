"""Create a project-scoped task report."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project_state.store import ProjectStateStore
from reports.task_reporter import TaskReport, TaskReportGenerator


def _split_items(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a markdown task report in data/projects/<project_id>/reports/")
    parser.add_argument("--root", default=str(ROOT), help="Project root")
    parser.add_argument("--project-id", default="lucidmind", help="Project identifier")
    parser.add_argument("--task-id", required=True, help="Stable task id used as report filename")
    parser.add_argument("--title", required=True, help="Report title")
    parser.add_argument("--goal", default="", help="Task goal")
    parser.add_argument("--result", default="partial", choices=["complete", "partial", "blocked"], help="Task result status")
    parser.add_argument("--context", default="", help="Semicolon-separated loaded context entries")
    parser.add_argument("--plan", default="", help="Semicolon-separated plan entries")
    parser.add_argument("--actions", default="", help="Semicolon-separated action entries")
    parser.add_argument("--files", default="", help="Semicolon-separated changed files")
    parser.add_argument("--tests", default="", help="Semicolon-separated test evidence entries")
    parser.add_argument("--risks", default="", help="Semicolon-separated risk entries")
    parser.add_argument("--decisions", default="", help="Semicolon-separated durable decisions")
    parser.add_argument("--next-step", default="", help="Next suggested step")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report = TaskReport(
        task_id=args.task_id,
        title=args.title,
        goal=args.goal,
        project_id=args.project_id,
        context_loaded=_split_items(args.context),
        plan=_split_items(args.plan),
        actions_taken=_split_items(args.actions),
        files_changed=_split_items(args.files),
        tests_run=_split_items(args.tests),
        result=args.result,
        risks=_split_items(args.risks),
        decisions_to_remember=_split_items(args.decisions),
        next_suggested_step=args.next_step,
    )
    path = TaskReportGenerator(root).save(report)

    store = ProjectStateStore(root, project_id=args.project_id)
    state = store.load()
    if state:
        state.last_task_report = str(path.relative_to(root))
        store.save(state)

    print(f"Task report written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
