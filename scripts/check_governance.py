"""Check Project Brain governance risk for proposed file/action changes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from governance.decision_log import GovernanceDecision, GovernanceDecisionLog
from governance.policy import GovernancePolicy


def _split_items(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Review governance risk and append a decision log entry")
    parser.add_argument("--root", default=str(ROOT), help="Project root")
    parser.add_argument("--project-id", default="lucidmind", help="Project identifier")
    parser.add_argument("--task-id", required=True, help="Task id")
    parser.add_argument("--files", default="", help="Semicolon-separated changed files")
    parser.add_argument("--actions", default="", help="Semicolon-separated actions")
    parser.add_argument("--write-log", action="store_true", help="Append governance decision log")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    review = GovernancePolicy.from_project_root(root).review(_split_items(args.files), _split_items(args.actions))
    payload = {
        "approved": review.approved,
        "risk_level": review.risk_level,
        "requires_confirmation": review.requires_confirmation,
        "reasons": review.reasons,
        "protected_files": review.protected_files,
        "dangerous_actions": review.dangerous_actions,
    }
    if args.write_log:
        GovernanceDecisionLog(root, project_id=args.project_id).append(
            GovernanceDecision(
                task_id=args.task_id,
                action="governance_check",
                approved=review.approved,
                risk_level=review.risk_level,
                reasons=review.reasons,
                metadata=payload,
            )
        )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if review.approved else 2


if __name__ == "__main__":
    raise SystemExit(main())
