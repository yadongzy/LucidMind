"""Run a minimal Project Brain task lifecycle and write its report."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.evidence import TestEvidence
from execution.lifecycle import TaskLifecycle
from execution.roles import SequentialRoleRunner
from memory.project_memory import ProjectMemoryIntegrator


def _split_items(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a minimal sequential project task lifecycle")
    parser.add_argument("--root", default=str(ROOT), help="Project root")
    parser.add_argument("--project-id", default="lucidmind", help="Project identifier")
    parser.add_argument("--task-id", required=True, help="Stable task id")
    parser.add_argument("--title", required=True, help="Report title")
    parser.add_argument("--goal", required=True, help="Task goal")
    parser.add_argument("--actions", default="", help="Semicolon-separated action entries")
    parser.add_argument("--files", default="", help="Semicolon-separated changed files")
    parser.add_argument("--tests", default="", help="Semicolon-separated test evidence entries")
    parser.add_argument("--risks", default="", help="Semicolon-separated risks")
    parser.add_argument("--decisions", default="", help="Semicolon-separated durable decisions")
    parser.add_argument("--result", default="partial", choices=["complete", "partial", "blocked"], help="Lifecycle result")
    parser.add_argument("--next-step", default="", help="Next suggested step")
    parser.add_argument("--run-roles", action="store_true", help="Run Planner -> Executor -> Reviewer -> Reporter before writing report")
    parser.add_argument("--remember", action="store_true", help="Write durable memory candidates after report generation")
    args = parser.parse_args()

    lifecycle = TaskLifecycle(Path(args.root).resolve(), project_id=args.project_id)
    evidence = lifecycle.create_evidence(args.task_id, args.goal)
    actions = _split_items(args.actions)
    files_changed = _split_items(args.files)
    evidence.actions_taken.extend(actions)
    evidence.files_changed.extend(files_changed)
    evidence.risks.extend(_split_items(args.risks))
    evidence.decisions.extend(_split_items(args.decisions))
    evidence.result = args.result
    for item in _split_items(args.tests):
        evidence.tests.append(TestEvidence(command=item, status="recorded"))

    governance_review = None
    role_outputs = []
    if args.run_roles:
        evidence.actions_taken = []
        evidence.files_changed = []
        role_outputs = SequentialRoleRunner().run(evidence, actions, files_changed)
        for output in role_outputs:
            if output.role == "Reviewer":
                governance_review = output.data.get("governance")
                if output.status == "approved" and args.result == "complete":
                    evidence.result = "complete"
                break

    path = lifecycle.write_report(
        evidence,
        title=args.title,
        next_step=args.next_step,
        governance_review=governance_review,
    )
    print(f"Lifecycle report written: {path}")
    if role_outputs:
        print("Roles: " + " -> ".join(f"{output.role}:{output.status}" for output in role_outputs))
    if args.remember:
        db_path = lifecycle.root / "data" / "projects" / args.project_id / "project_memory.sqlite3"
        integrator = ProjectMemoryIntegrator(db_path)
        ids = integrator.remember_candidates(integrator.candidates_from_evidence(evidence))
        print(f"Remembered {len(ids)} memory candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
