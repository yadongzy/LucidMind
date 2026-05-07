"""Run Codex CLI read-only explain/review requests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills.codex_cli.runner import CodexCliRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only Codex CLI explain/review")
    parser.add_argument("mode", choices=["explain", "review"], help="Read-only Codex operation")
    parser.add_argument("--root", default=str(ROOT), help="Project root")
    parser.add_argument("--target", required=True, help="Repository file or area to inspect")
    parser.add_argument("--question", default="", help="Optional question")
    parser.add_argument("--executable", default="codex", help="Codex CLI executable name or path")
    args = parser.parse_args()

    runner = CodexCliRunner(Path(args.root).resolve(), executable=args.executable)
    if args.mode == "explain":
        result = runner.explain(args.target, args.question or "Explain this repository area.")
    else:
        result = runner.review(args.target, args.question or "Review this code for risks and correctness.")
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
