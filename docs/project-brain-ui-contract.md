# Project Brain UI/API Data Contract

This document defines the stable data contract for future Project Brain API and UI integration. It does not require modifying `api/main.py`, frontend files, or core Brain files.

## Principles

- API responses must expose evidence, not hidden reasoning.
- Governance state must be visible before any risky action is executed.
- Report and memory data must be traceable to a `project_id` and `task_id`.
- Missing optional systems such as Codex CLI must be represented as degraded capability, not failure of the whole cockpit.
- Core file changes must show `requires_confirmation` before any execution path can proceed.

## Object: ProjectState

Source path:

```text
data/projects/<project_id>/project_state.json
```

Shape:

```json
{
  "project_id": "lucidmind",
  "name": "LucidMind",
  "root": "/Users/yadong/Documents/LucidMind",
  "updated_at": "2026-05-06T00:00:00+00:00",
  "languages": ["python", "javascript"],
  "frameworks": ["fastapi"],
  "entrypoints": ["api/main.py", "cli.py"],
  "test_commands": ["python -m pytest tests/test_brain.py -v"],
  "run_commands": ["python cli.py start"],
  "core_files": ["brain.py", "api/main.py", "ports/"],
  "protected_rules": [".rules/15-file-protection.md"],
  "recent_decisions": [],
  "known_risks": [],
  "last_task_report": "data/projects/lucidmind/reports/example.md",
  "git": {
    "branch": "main",
    "commit": "abcdef0",
    "dirty": true
  },
  "capabilities": {
    "project_state": "available",
    "task_reports": "available",
    "governance": "available",
    "codex_cli": "missing"
  }
}
```

## Object: TaskReportSummary

Used by report list views.

```json
{
  "project_id": "lucidmind",
  "task_id": "lifecycle-remember-smoke",
  "title": "Lifecycle Remember Smoke",
  "path": "data/projects/lucidmind/reports/lifecycle-remember-smoke.md",
  "created_at": "2026-05-06T00:00:00+00:00",
  "result": "complete",
  "governance_result": "approved",
  "requires_confirmation": false,
  "tests_count": 1,
  "risks_count": 1,
  "decisions_count": 2
}
```

Allowed `result` values:

```text
complete | partial | blocked
```

Allowed `governance_result` values:

```text
approved | requires-confirmation | not-reviewed
```

## Object: TaskReportDetail

Used by report detail views.

```json
{
  "project_id": "lucidmind",
  "task_id": "lifecycle-remember-smoke",
  "title": "Lifecycle Remember Smoke",
  "goal": "Verify lifecycle script writes report and project memories in one run.",
  "context_loaded": ["languages:python", "frameworks:fastapi"],
  "plan": ["Load project state and constraints."],
  "actions_taken": ["Added --remember lifecycle memory write"],
  "files_changed": ["scripts/run_project_task_lifecycle.py"],
  "tests_run": ["python -m pytest tests/test_brain.py -v — passed"],
  "result": "complete",
  "risks": ["Keep memory candidates concise to avoid pollution"],
  "decisions_to_remember": ["Lifecycle --remember writes durable project memories"],
  "governance": {
    "governance_result": "approved",
    "protected_files": [],
    "required_confirmations": [],
    "dangerous_actions": []
  },
  "memory": {
    "remembered_count": 5,
    "collections": ["project_decisions", "project_risks", "test_knowledge", "task_summaries"]
  },
  "next_suggested_step": "Make governance policy configurable before API/UI integration",
  "markdown_path": "data/projects/lucidmind/reports/lifecycle-remember-smoke.md"
}
```

## Object: GovernanceReview

Used by preflight review panels and report rendering.

```json
{
  "approved": false,
  "risk_level": "high",
  "requires_confirmation": true,
  "reasons": [
    "Protected files require explicit confirmation.",
    "Dangerous actions require explicit confirmation."
  ],
  "protected_files": ["brain.py"],
  "dangerous_actions": ["git push origin main"],
  "policy_source": {
    "builtin": true,
    "config_path": "data/governance/policies.json",
    "config_loaded": true
  }
}
```

Allowed `risk_level` values:

```text
low | high
```

UI requirement:

- If `requires_confirmation` is true, the UI must show a blocking confirmation state.
- If `protected_files` is non-empty, the UI must list each file explicitly.
- If `dangerous_actions` is non-empty, the UI must show the exact action text.

## Object: LifecycleTimeline

Used by cockpit timeline views.

```json
{
  "project_id": "lucidmind",
  "task_id": "role-safe-report-smoke",
  "events": [
    {
      "role": "Planner",
      "status": "ready",
      "messages": ["Plan prepared."],
      "created_at": "2026-05-06T00:00:00+00:00"
    },
    {
      "role": "Executor",
      "status": "complete",
      "messages": ["Execution evidence recorded."],
      "created_at": "2026-05-06T00:00:01+00:00"
    },
    {
      "role": "Reviewer",
      "status": "approved",
      "messages": ["Review passed."],
      "created_at": "2026-05-06T00:00:02+00:00"
    },
    {
      "role": "Reporter",
      "status": "ready",
      "messages": ["Report evidence finalized."],
      "created_at": "2026-05-06T00:00:03+00:00"
    }
  ]
}
```

Allowed role values:

```text
Planner | Executor | Reviewer | Reporter
```

Allowed role status values:

```text
ready | complete | approved | rejected
```

## Object: MemoryCandidate

Used by memory candidate panels.

```json
{
  "collection": "project_decisions",
  "content": "Lifecycle --remember writes durable project memories",
  "metadata": {
    "project_id": "lucidmind",
    "task_id": "lifecycle-remember-smoke"
  },
  "status": "remembered",
  "memory_id": "mem_abc123"
}
```

Allowed `status` values:

```text
candidate | remembered | skipped
```

Required collections:

```text
project_decisions
project_risks
test_knowledge
task_summaries
tool_lessons
```

## Object: CodexReadOnlyResult

Used by Codex explain/review panels.

```json
{
  "success": false,
  "tool": "codex_explain",
  "prompt": "Read-only explain request. Target: project_state. Do not modify files.",
  "stdout": "",
  "stderr": "",
  "exit_code": null,
  "duration_ms": 9.19,
  "error": "Codex CLI not found. Install Codex CLI or configure the executable path before using this skill."
}
```

Allowed `tool` values:

```text
codex_explain | codex_review
```

UI requirement:

- If `success` is false and `exit_code` is null, show setup guidance rather than a task failure banner.
- The UI must display that Codex mode is read-only.

## Proposed Read-only API Surface

These endpoints are a proposed contract only. They are not currently mounted.

```text
GET /api/project-brain/projects/{project_id}/state
GET /api/project-brain/projects/{project_id}/reports
GET /api/project-brain/projects/{project_id}/reports/{task_id}
POST /api/project-brain/projects/{project_id}/governance/review
GET /api/project-brain/projects/{project_id}/governance/decisions
GET /api/project-brain/projects/{project_id}/memory/candidates?task_id=<task_id>
POST /api/project-brain/projects/{project_id}/codex/explain
POST /api/project-brain/projects/{project_id}/codex/review
```

Initial API integration should be read-only except governance review and Codex read-only request endpoints. No endpoint should execute file writes, shell commands, commits, pushes, or deletes without explicit governance approval.

## UI Cockpit Panels

Recommended first UI panels:

1. Project State panel
2. Latest Reports panel
3. Lifecycle Timeline panel
4. Governance Review panel
5. Memory Candidates panel
6. Codex Read-only Review panel

## Acceptance Criteria Before API/UI Integration

- `python -m pytest tests/test_brain.py -v` passes.
- Full Project Brain regression passes.
- A safe lifecycle task produces `governance_result=approved`.
- A protected-file lifecycle task produces `governance_result=requires-confirmation`.
- `--remember` writes memory candidates to expected collections.
- Codex missing state returns actionable setup guidance.
- No changes are made to `brain.py`, `api/main.py`, `ports/`, or frontend files without explicit confirmation.
