"""Deterministic sequential roles for the Project Brain lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field

from execution.evidence import LifecycleEvidence
from governance.policy import GovernancePolicy, GovernanceReview


@dataclass
class RoleOutput:
    role: str
    status: str
    messages: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)


class PlannerRole:
    name = "Planner"

    def run(self, evidence: LifecycleEvidence) -> RoleOutput:
        if not evidence.plan:
            evidence.plan.extend([
                "Load project state and constraints.",
                "Perform bounded implementation.",
                "Review governance and test status.",
                "Write report and memory candidates.",
            ])
        return RoleOutput(self.name, "ready", ["Plan prepared."], {"plan": evidence.plan})


class ExecutorRole:
    name = "Executor"

    def run(self, evidence: LifecycleEvidence, actions: list[str], files_changed: list[str]) -> RoleOutput:
        evidence.actions_taken.extend(actions)
        evidence.files_changed.extend(files_changed)
        return RoleOutput(self.name, "complete", ["Execution evidence recorded."], {
            "actions_taken": actions,
            "files_changed": files_changed,
        })


class ReviewerRole:
    name = "Reviewer"

    def __init__(self, policy: GovernancePolicy | None = None):
        self.policy = policy or GovernancePolicy()

    def run(self, evidence: LifecycleEvidence) -> RoleOutput:
        review = self.policy.review(evidence.files_changed, evidence.actions_taken)
        missing_tests = not evidence.tests
        messages = list(review.reasons)
        if missing_tests:
            messages.append("Completion requires explicit test status.")
        if review.requires_confirmation or missing_tests:
            evidence.result = "partial"
            if missing_tests and "Tests not recorded." not in evidence.risks:
                evidence.risks.append("Tests not recorded.")
            return RoleOutput(self.name, "rejected", messages, {"governance": review})
        return RoleOutput(self.name, "approved", ["Review passed."], {"governance": review})


class ReporterRole:
    name = "Reporter"

    def run(self, evidence: LifecycleEvidence, governance_review: GovernanceReview | None = None) -> RoleOutput:
        if governance_review and governance_review.reasons:
            evidence.risks.extend(reason for reason in governance_review.reasons if reason not in evidence.risks)
        if evidence.result not in {"complete", "partial", "blocked"}:
            evidence.result = "partial"
        return RoleOutput(self.name, "ready", ["Report evidence finalized."], {
            "result": evidence.result,
            "risks": evidence.risks,
        })


class SequentialRoleRunner:
    def __init__(self, policy: GovernancePolicy | None = None):
        self.planner = PlannerRole()
        self.executor = ExecutorRole()
        self.reviewer = ReviewerRole(policy)
        self.reporter = ReporterRole()

    def run(self, evidence: LifecycleEvidence, actions: list[str], files_changed: list[str]) -> list[RoleOutput]:
        outputs = [
            self.planner.run(evidence),
            self.executor.run(evidence, actions, files_changed),
        ]
        review_output = self.reviewer.run(evidence)
        outputs.append(review_output)
        outputs.append(self.reporter.run(evidence, review_output.data.get("governance")))
        return outputs
