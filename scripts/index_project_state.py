"""Generate a project state snapshot for LucidMind."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project_state.indexer import ProjectStateIndexer
from project_state.store import ProjectStateStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Index project state into data/projects/<project_id>/project_state.json")
    parser.add_argument("--root", default=str(ROOT), help="Project root to index")
    parser.add_argument("--project-id", default="lucidmind", help="Project identifier used for storage path")
    parser.add_argument("--print", action="store_true", help="Print generated state JSON")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    state = ProjectStateIndexer(root, project_id=args.project_id).build()
    path = ProjectStateStore(root, project_id=args.project_id).save(state)

    if args.print:
        print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
    print(f"Project state written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
