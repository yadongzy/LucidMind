"""Project Brain memory candidate integration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from execution.evidence import LifecycleEvidence
from memory.store import MemoryStore
from reports.task_reporter import TaskReport


@dataclass
class MemoryCandidate:
    collection: str
    content: str
    metadata: dict


_COLLECTIONS = {
    "decision": "project_decisions",
    "risk": "project_risks",
    "test": "test_knowledge",
    "tool": "tool_lessons",
    "summary": "task_summaries",
}


class ProjectMemoryIntegrator:
    def __init__(self, db_path: str | Path):
        self.store = MemoryStore(Path(db_path))

    def candidates_from_evidence(self, evidence: LifecycleEvidence) -> list[MemoryCandidate]:
        candidates: list[MemoryCandidate] = []
        metadata = {"task_id": evidence.task_id, "project_id": evidence.project_id}
        for decision in evidence.decisions:
            candidates.append(MemoryCandidate(_COLLECTIONS["decision"], decision, metadata))
        for risk in evidence.risks:
            candidates.append(MemoryCandidate(_COLLECTIONS["risk"], risk, metadata))
        for test in evidence.tests_as_lines():
            candidates.append(MemoryCandidate(_COLLECTIONS["test"], test, metadata))
        summary = self._summary(evidence)
        if summary:
            candidates.append(MemoryCandidate(_COLLECTIONS["summary"], summary, metadata))
        return self._filter_candidates(candidates)

    def candidates_from_report(self, report: TaskReport) -> list[MemoryCandidate]:
        evidence = LifecycleEvidence(
            task_id=report.task_id,
            goal=report.goal,
            project_id=report.project_id,
            actions_taken=report.actions_taken,
            files_changed=report.files_changed,
            risks=report.risks,
            decisions=report.decisions_to_remember,
            result=report.result,
        )
        candidates = self.candidates_from_evidence(evidence)
        metadata = {"task_id": report.task_id, "project_id": report.project_id}
        for test_line in report.tests_run:
            candidates.append(MemoryCandidate(_COLLECTIONS["test"], test_line, metadata))
        return self._filter_candidates(candidates)

    def remember_candidates(self, candidates: list[MemoryCandidate]) -> list[str]:
        ids: list[str] = []
        for candidate in self._filter_candidates(candidates):
            mem_id = self.store.add(
                candidate.collection,
                candidate.content,
                metadata=candidate.metadata,
                skip_noise_filter=True,
            )
            if mem_id:
                ids.append(mem_id)
        return ids

    @staticmethod
    def _summary(evidence: LifecycleEvidence) -> str:
        if not evidence.actions_taken and not evidence.files_changed:
            return ""
        actions = "; ".join(evidence.actions_taken[:5]) or "No actions recorded"
        files = ", ".join(evidence.files_changed[:8]) or "No files changed"
        return f"Task {evidence.task_id} ({evidence.result}): {actions}. Files: {files}."

    @staticmethod
    def _filter_candidates(candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
        filtered: list[MemoryCandidate] = []
        seen: set[tuple[str, str]] = set()
        for candidate in candidates:
            content = candidate.content.strip()
            if len(content) < 8:
                continue
            key = (candidate.collection, content)
            if key in seen:
                continue
            seen.add(key)
            filtered.append(MemoryCandidate(candidate.collection, content, candidate.metadata))
        return filtered
