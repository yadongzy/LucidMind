#!/usr/bin/env python3
"""§14 Milestone Demo — end-to-end project brain loop on LucidMind itself.

Demonstrates:
  1. Load project state
  2. Create a visible plan
  3. Run governance check
  4. Execute a bounded task (non-core file change)
  5. Run tests
  6. Generate task report
  7. Store decisions and lessons
  8. Record metrics
  9. Print summary
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from project_state.indexer import ProjectStateIndexer
from project_state.store import ProjectStateStore
from governance.policy import GovernancePolicy
from reports.task_reporter import TaskReport, TaskReportGenerator
from reports.metrics import TaskMetrics, MetricsCollector
from memory.project_memory import ProjectMemoryIntegrator


def main():
    parser = argparse.ArgumentParser(description="Project Brain milestone demo")
    parser.add_argument("--project-id", default="lucidmind")
    parser.add_argument("--task", default="milestone-demo")
    parser.add_argument("--goal", default="Verify the full project brain loop on LucidMind itself.")
    parser.add_argument("--test-cmd", default="python -m pytest tests/test_brain.py -v")
    parser.add_argument("--files", default="scripts/run_milestone_demo.py", help="Comma-separated changed files")
    args = parser.parse_args()

    t0 = time.time()
    files_changed = [f.strip() for f in args.files.split(",") if f.strip()]

    print("=" * 60)
    print("  Project Brain Milestone Demo")
    print("=" * 60)

    # Step 1: Load project state
    print("\n[1/8] Loading project state...")
    indexer = ProjectStateIndexer(ROOT, args.project_id)
    state = indexer.build()
    store = ProjectStateStore(ROOT, args.project_id)
    store.save(state)
    print(f"  Project: {state.project_name}")
    print(f"  Languages: {state.languages}")
    print(f"  Git: {state.git_branch} @ {state.git_commit}")

    # Step 2: Create a visible plan
    print("\n[2/8] Creating plan...")
    plan = [
        f"Goal: {args.goal}",
        f"Changed files: {', '.join(files_changed)}",
        f"Test command: {args.test_cmd}",
        "Governance check before execution.",
        "Generate report and store memory.",
    ]
    for step in plan:
        print(f"  • {step}")

    # Step 3: Governance check
    print("\n[3/8] Running governance check...")
    policy = GovernancePolicy.from_project_root(ROOT)
    review = policy.review(files_changed)
    gov_result = "approved" if review.approved else "requires-confirmation"
    print(f"  Result: {gov_result}")
    print(f"  Protected files: {review.protected_files or 'none'}")
    if review.requires_confirmation:
        print("  ⚠ Governance requires confirmation. In production, this would block.")

    # Step 4: Execute task (already done — this script IS the task)
    print("\n[4/8] Executing task...")
    print("  Task is the demo script itself — execution complete.")

    # Step 5: Run tests
    print(f"\n[5/8] Running tests: {args.test_cmd}")
    test_result = subprocess.run(
        args.test_cmd.split(), cwd=ROOT, capture_output=True, text=True, timeout=120
    )
    tests_passed = test_result.returncode == 0
    test_output = test_result.stdout.strip().split("\n")[-1] if test_result.stdout else "no output"
    print(f"  Exit code: {test_result.returncode}")
    print(f"  Result: {test_output}")

    # Step 6: Generate report
    print("\n[6/8] Generating task report...")
    report = TaskReport(
        task_id=args.task,
        title="Milestone Demo",
        goal=args.goal,
        project_id=args.project_id,
        context_loaded=[f"languages:{','.join(state.languages)}", f"frameworks:{','.join(state.frameworks)}"],
        plan=plan,
        actions_taken=["Ran full project brain loop demo"],
        files_changed=files_changed,
        tests_run=[f"{args.test_cmd} — {'passed' if tests_passed else 'FAILED'}"],
        result="complete" if tests_passed else "partial",
        risks=["Demo script does not modify production code"],
        decisions_to_remember=["Full project brain loop verified end-to-end"],
        governance_result=gov_result,
        protected_files=review.protected_files,
        required_confirmations=[],
        dangerous_actions=review.dangerous_actions,
        next_suggested_step="Build frontend cockpit panels for live monitoring",
    )
    gen = TaskReportGenerator(ROOT)
    report_path = gen.save(report)
    print(f"  Report: {report_path.relative_to(ROOT)}")

    # Step 7: Store memory
    print("\n[7/8] Storing project memories...")
    db_path = ROOT / "data" / "projects" / args.project_id / "project_memory.db"
    integrator = ProjectMemoryIntegrator(db_path)
    candidates = integrator.candidates_from_report(report)
    ids = integrator.remember_candidates(candidates)
    print(f"  Remembered: {len(ids)} candidates")

    # Step 8: Record metrics
    print("\n[8/8] Recording metrics...")
    duration_ms = (time.time() - t0) * 1000
    metrics = TaskMetrics(
        project_id=args.project_id,
        task_id=args.task,
        files_inspected=0,
        files_changed=len(files_changed),
        tools_called=0,
        test_commands_run=1,
        tests_passed=1 if tests_passed else 0,
        tests_failed=0 if tests_passed else 1,
        recovery_attempts=0,
        approvals_requested=1 if review.requires_confirmation else 0,
        report_generated=True,
        memory_candidates=len(ids),
        completion_status="complete" if tests_passed else "partial",
        duration_ms=round(duration_ms, 1),
    )
    collector = MetricsCollector(ROOT, args.project_id)
    collector.record(metrics)
    print(f"  Duration: {duration_ms:.0f}ms")

    # Summary
    print("\n" + "=" * 60)
    print("  DEMO COMPLETE")
    print("=" * 60)
    print(f"  Status: {'✅ PASS' if tests_passed else '❌ FAIL'}")
    print(f"  Report: {report_path.relative_to(ROOT)}")
    print(f"  Memories: {len(ids)}")
    print(f"  Governance: {gov_result}")
    print(f"  Duration: {duration_ms:.0f}ms")
    print()

    sys.exit(0 if tests_passed else 1)


if __name__ == "__main__":
    main()
