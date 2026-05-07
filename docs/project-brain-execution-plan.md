# LucidMind Project Brain Execution Plan

> Goal: make LucidMind a transparent, governable, long-running project brain — not a Codex replacement, but an orchestration layer for Codex, local tools, MCP, memory, governance, and task reports.

## 1. Strategic Positioning

### 1.1 What LucidMind is

LucidMind is a **transparent and governable project brain**.

It should maintain long-term project state, orchestrate tools and coding agents, execute tasks through verifiable loops, produce reports, and remember decisions across sessions.

### 1.2 What LucidMind is not

LucidMind should not try to become another Codex.

Codex is optimized for short-term software engineering execution: repository understanding, patch generation, test fixing, and code review. LucidMind should use Codex-like agents as execution specialists when useful, while LucidMind owns state, governance, continuity, and auditability.

### 1.3 Strategic sentence

LucidMind does not replace Codex. It orchestrates Codex, local tools, MCP, long-term memory, project state, and governance into a transparent project brain that can safely maintain a project over time.

## 2. Competitive Frame

| Competitor | Core Strength | LucidMind Response |
|---|---|---|
| Codex | Single-agent coding execution, patch/test/review ability | Treat as callable coding executor; LucidMind owns memory, plan, verification, report |
| Hermes | Identity continuity, memory rhythm, multi-channel gateway, skill lifecycle | Learn from setup, skill curator, gateway discipline; do not compete on platform count first |
| OpenClaw | Workspace memory, project files, agent lifestyle | Keep Markdown-compatible memory but add visible governance and Python-native tools |
| Agent OS-style competitors | Group intelligence, slots, governance, long-running project kernel | Avoid concept-first architecture; win through one reliable project task lifecycle loop |

## 3. Product Goal

Build one reliable loop first:

```text
User gives a project goal
  -> LucidMind loads project state
  -> retrieves memories, rules, decisions, risks
  -> creates a visible plan
  -> chooses executor: local tools / MCP / Codex CLI / sub-agent
  -> modifies or inspects project
  -> runs tests and checks logs
  -> generates a task report
  -> stores decisions and lessons
  -> next task continues from the previous state
```

This loop is more important than large abstractions such as nine slots or a full Agent OS. The first milestone is not a complete operating system; it is a dependable project task lifecycle.

## 4. Core Principles

### 4.1 Transparent

Users must see what the agent is doing and why.

Required visible events:

- Planning
- Memory retrieval
- Project state loading
- File reads and writes
- Tool calls
- Test execution
- Error recovery
- Approval requests
- Report generation
- Memory updates

### 4.2 Long-term

LucidMind must remember project-level knowledge across sessions:

- Architecture decisions
- Test commands
- Run commands
- Protected files
- User preferences
- Failed approaches
- Accepted patterns
- Known risks
- Current task state
- Previous reports

### 4.3 Governable

LucidMind must not only act; it must act inside boundaries.

Governance requirements:

- Core file protection
- Dangerous operation approval
- Diff summary before risky write
- Test evidence before completion
- Rollback point or recovery plan
- Human-readable task report
- No hidden destructive actions

### 4.4 Extensible

New capabilities should be adapters, tools, skills, or MCP servers. Brain core should not grow for every new integration.

## 5. Target Architecture

### 5.1 Existing architecture to preserve

```text
API / CLI / Channels
  -> Brain Core
  -> Ports
  -> Adapters / Skills / MCP
  -> Storage / Logs / Reports
```

The current Ports & Adapters direction should remain. Project Brain additions should be modular and injected through existing layers.

### 5.2 New subsystems

```text
project_state/
  indexer.py       # scans project and builds state snapshot
  schema.py        # typed project state structures
  store.py         # read/write project_state.json
  detector.py      # framework/test/run command detection
  reporter.py      # state summaries for Brain/context

reports/
  task_reporter.py # generates per-task markdown reports
  templates.py     # report templates

skills/codex_cli/
  manifest.json
  main.py          # Codex CLI ToolPort implementation
  README.md

execution/
  lifecycle.py     # task lifecycle orchestration helpers
  evidence.py      # test/log/diff evidence objects
```

No new Port is required for the first phase. Use existing ToolPort, MemoryPort, StreamPort, and LearningPort. A new Port should only be introduced after the first working loop proves that existing ports are insufficient.

## 6. Project State Index

### 6.1 Purpose

The project state index is the persistent map of what the project is, how it runs, how it is tested, and what risks or decisions are known.

### 6.2 Minimal data model

File: `data/project_state.json`

```json
{
  "project_name": "LucidMind",
  "root": "/path/to/project",
  "updated_at": "2026-05-06T00:00:00+08:00",
  "languages": ["python", "javascript"],
  "frameworks": ["fastapi", "vite", "lit"],
  "entrypoints": ["api/main.py", "cli.py"],
  "test_commands": [
    "python -m pytest tests/test_brain.py -v",
    "python -m pytest tests/ --ignore=tests/_deprecated -v --tb=short"
  ],
  "run_commands": [
    "python -m uvicorn api.main:app --host 0.0.0.0 --port 8765"
  ],
  "core_files": ["brain.py", "brain_daemon.py", "api/main.py", "task_dispatcher.py", "ports/"],
  "protected_rules": ["do not modify core files without confirmation", "do not delete files without confirmation"],
  "recent_decisions": [],
  "known_risks": [],
  "last_task_report": null
}
```

### 6.3 Detection scope for v1

The first indexer should detect only practical items:

- Python package metadata from `pyproject.toml`
- API entrypoint from `api/main.py`
- CLI entrypoint from `[project.scripts]`
- Test commands from `.rules/11-testing-iron.md` and README
- Protected files from `.rules/15-file-protection.md`
- Frontend framework from `frontend-v2/package.json` if present
- Git branch and last commit via read-only git commands

### 6.4 Acceptance criteria

- Running the indexer creates `data/project_state.json`.
- Re-running updates `updated_at` without deleting user decisions.
- Missing optional files do not crash indexing.
- Output is human-readable and deterministic enough for tests.

## 7. Task Report System

### 7.1 Purpose

Every meaningful task should leave an audit trail. The report is the engineering memory of the project.

### 7.2 Report location

```text
logs/task_reports/YYYY-MM-DD-HHMM-task-slug.md
```

### 7.3 Report template

```markdown
# Task Report: <title>

## Goal

## Context Loaded
- Project state:
- Memories:
- Rules:
- Files inspected:

## Plan

## Actions Taken

## Files Changed

## Tests Run

## Result

## Risks / Unfinished Work

## Decisions to Remember

## Next Suggested Step
```

### 7.4 Acceptance criteria

- A report is generated for each implementation task.
- Report includes exact test commands if tests were run.
- If tests were not run, report explicitly says so.
- Report lists changed files and risks.
- Report can be searched by memory system later.

## 8. Codex CLI Skill

### 8.1 Purpose

Codex should be treated as a coding executor, not as a competitor.

LucidMind decides when and why to call Codex. Codex performs code-heavy work. LucidMind verifies, reports, remembers, and governs.

### 8.2 Initial tools

Skill: `skills/codex_cli`

Tools:

- `codex_explain`: ask Codex to explain a repo area without writing
- `codex_review`: ask Codex for code review on a file or diff
- `codex_plan`: ask Codex for implementation options
- `codex_patch`: request patch generation; requires approval before write or application
- `codex_fix_tests`: ask Codex to propose fixes for failing tests

### 8.3 Safety rules

- Default mode is read-only.
- Writes require explicit user approval.
- Workspace path must be inside allowed project root.
- Tool must capture stdout, stderr, exit code, and duration.
- Tool must not auto-push, auto-commit, or delete files.
- Tool output must be summarized into the task report.

### 8.4 Acceptance criteria

- If Codex CLI is missing, tool returns actionable setup guidance.
- Read-only explain/review works without modifying files.
- Patch mode cannot write without approval.
- All executions are logged and included in reports.

## 9. Minimal Multi-Agent Design

### 9.1 Do not start with open-ended swarm

A full group intelligence system is high-risk. Start with four deterministic roles.

| Role | Responsibility | Output |
|---|---|---|
| Planner | Understand goal, load project state, create plan | Plan with risks and required confirmations |
| Executor | Use tools/Codex/MCP to perform work | Action log and changed files |
| Reviewer | Check diff, rules, tests, risks | Review result and required fixes |
| Reporter | Write task report and memory updates | Markdown report and memory candidates |

### 9.2 Implementation strategy

Do not create separate autonomous agents at first. Implement role prompts or role functions inside the existing task lifecycle. Promote to separate agents only after handoff formats are stable.

### 9.3 Acceptance criteria

- Each role has a clear input and output object.
- Reviewer can reject Executor output.
- Reporter records incomplete work honestly.
- The loop can run sequentially before any parallelism is added.

## 10. Governance System

### 10.1 Governance boundaries

Governance should reuse existing rules first:

- Core file protection from `.rules/15-file-protection.md`
- Change declaration from `.rules/16-change-declaration.md`
- Test evidence from `.rules/11-testing-iron.md`
- Architecture boundaries from `.rules/01-architecture.md` and `.rules/10-code-guard.md`

### 10.2 New governance artifacts

Add these later after project state and reports exist:

```text
data/governance/policies.json
logs/governance_decisions.jsonl
logs/task_reports/*.md
```

### 10.3 Required checks before completion

A task cannot be called complete unless:

- Goal is restated.
- Changed files are listed.
- Tests run or not-run status is explicit.
- Risks are listed.
- Any skipped validation is explicitly explained.
- Report is generated for implementation tasks.

## 11. Memory Integration

### 11.1 What to store

Do not store everything. Store durable knowledge:

- Architecture decisions
- Repeated failures
- Test commands that worked
- User preferences
- Project-specific constraints
- Tool reliability notes
- Accepted implementation patterns
- Rejected approaches and reasons

### 11.2 What not to store

- Raw secrets
- Full logs unless summarized
- Temporary command output
- Duplicate task chatter
- Low-value greetings

### 11.3 Memory collections

Recommended collections:

- `project_decisions`
- `project_risks`
- `test_knowledge`
- `tool_lessons`
- `user_preferences`
- `task_summaries`

### 11.4 Acceptance criteria

- Each task report suggests memory candidates.
- Memory writes are concise and searchable.
- Risk and decision memories are evergreen.
- User can inspect what was remembered.

## 12. Web UI Direction

### 12.1 Why UI matters

LucidMind should win on observability. CLI-only experiences are already strong in Codex and Hermes. LucidMind's Web UI should become the governance cockpit.

### 12.2 Required panels

- Project State panel
- Current Task Lifecycle panel
- Memory Hits panel
- Tool Calls timeline
- Test Evidence panel
- Approval panel
- Task Reports browser
- Risk/Decision ledger

### 12.3 First UI milestone

Do not redesign the frontend first. Expose backend APIs and reports first. Add UI panels after the backend artifacts are stable.

## 13. Implementation Roadmap

## Phase 0: Positioning and Trust Cleanup

Duration: 0.5-1 day

Tasks:

1. Update README positioning against Codex/Hermes/OpenClaw honestly.
2. Add `docs/positioning.md` or link this plan from docs.
3. Fix CLI documentation mismatch if present.
4. Add missing optional dependencies for documented channels.

Acceptance criteria:

- README no longer claims inaccurate competitor weaknesses.
- Public positioning says LucidMind orchestrates Codex rather than replaces it.
- Documented commands match actual CLI behavior.

## Phase 1: Project State Index

Duration: 1-2 days

Tasks:

1. Create `project_state/schema.py`.
2. Create `project_state/indexer.py`.
3. Create `project_state/store.py`.
4. Add tests for detection and persistence.
5. Generate `data/project_state.json` locally.

Acceptance criteria:

- Indexer works on LucidMind repo.
- Tests cover missing optional files.
- Existing tests still pass.

## Phase 2: Task Report Generator

Duration: 1-2 days

Tasks:

1. Create `reports/task_reporter.py`.
2. Define report data model.
3. Generate Markdown report from structured task evidence.
4. Add tests for report generation.
5. Add report path to project state.

Acceptance criteria:

- Report generator creates deterministic Markdown.
- Tests verify required sections.
- Not-run tests are represented honestly.

## Phase 3: Lifecycle Loop v1

Duration: 2-4 days

Tasks:

1. Create lifecycle data structures.
2. Implement sequential Planner -> Executor -> Reviewer -> Reporter flow as helper functions.
3. Integrate project state loading.
4. Integrate task report output.
5. Keep Brain changes minimal; prefer API/startup or helper-level integration.

Acceptance criteria:

- A task can produce a lifecycle trace and final report.
- Reviewer can mark task incomplete.
- Completion requires explicit test status.

## Phase 4: Codex CLI Skill

Duration: 1-3 days

Tasks:

1. Create `skills/codex_cli/manifest.json`.
2. Implement read-only `codex_explain` and `codex_review` first.
3. Add guarded `codex_patch` later.
4. Add tests for missing CLI and safe command construction.
5. Add report integration for Codex outputs.

Acceptance criteria:

- Missing Codex CLI returns clear error.
- Read-only tools do not modify files.
- Patch mode is gated by approval.

## Phase 5: Governance Hardening

Duration: 2-4 days

Tasks:

1. Add policy reader for protected files and dangerous actions.
2. Add governance decision log.
3. Add approval requirement for high-risk writes.
4. Add rollback guidance in reports.
5. Add tests for core-file detection.

Acceptance criteria:

- Core file writes are detected before execution.
- Dangerous operations require approval.
- Reports include governance decisions.

## Phase 6: Web UI Cockpit

Duration: 4-7 days

Tasks:

1. Add API endpoints for project state and task reports.
2. Add reports browser panel.
3. Add current lifecycle timeline.
4. Add memory hits and tool calls panels.
5. Add approval UX for guarded operations.

Acceptance criteria:

- User can inspect project state in browser.
- User can open past task reports.
- User can see lifecycle events live.

## Phase 7: Minimal Role System

Duration: 3-5 days

Tasks:

1. Define Planner/Executor/Reviewer/Reporter schemas.
2. Implement sequential role execution.
3. Add role-specific report sections.
4. Add tests for rejected review and incomplete report.
5. Only then consider parallel sub-agents.

Acceptance criteria:

- Role outputs are structured.
- Reviewer can block completion.
- Reporter records unresolved issues.

## 14. Milestone Demo

The first public demo should be narrow and convincing:

```text
Goal: improve or fix a small module in LucidMind.

LucidMind:
1. Loads project_state.json.
2. Reads relevant rules and memories.
3. Creates a visible plan.
4. Edits a non-core module or asks for confirmation for core files.
5. Runs exact tests.
6. Generates a task report.
7. Stores one decision and one lesson.
8. On next task, recalls the previous report.
```

Success is not measured by concept coverage. Success is measured by whether the loop finishes honestly with evidence.

## 15. Metrics

Track these metrics per task:

- Files inspected
- Files changed
- Tools called
- Test commands run
- Test pass/fail count
- Recovery attempts
- User approvals requested
- Report generated yes/no
- Memory candidates generated
- Completion status: complete / partial / blocked

Long-term metrics:

- Number of reusable decisions
- Number of repeated failures reduced
- Time from goal to verified report
- Percentage of tasks with valid reports
- Percentage of risky actions caught before execution

## 16. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Concept over-expansion | Many abstractions, no working loop | Build project task lifecycle first |
| Multi-agent chaos | Cost, contradiction, unclear responsibility | Start with sequential roles |
| Codex dependency risk | External tool may be unavailable | Codex skill is optional; local tools remain fallback |
| Report noise | Reports become verbose and unused | Use fixed template and concise evidence |
| Memory pollution | Too many low-value memories | Store only durable decisions, risks, preferences, lessons |
| Core file accidents | Project instability | Enforce protected file checks and approval |
| UI-first distraction | Backend artifacts unstable | Build state/report APIs before UI panels |

## 17. Immediate Next Actions

Recommended execution order:

1. Update public positioning documentation.
2. Build `project_state` minimal indexer.
3. Build task report generator.
4. Add lifecycle trace object.
5. Add Codex CLI read-only skill.
6. Add governance log.
7. Add browser panels.
8. Add sequential Planner/Executor/Reviewer/Reporter roles.

## 18. Definition of Done for the Strategy

This strategy is implemented when LucidMind can repeatedly do the following on its own project:

```text
Understand project state -> execute a bounded task -> verify with tests/logs -> generate report -> remember decisions -> continue next time from stored context
```

If this loop is reliable, LucidMind does not need to claim it is an Agent OS. It will already behave like a transparent, governable project brain.
