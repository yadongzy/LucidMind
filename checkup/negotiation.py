"""Brain-Codex Negotiation Protocol — 双向协商协议。

不是单向发指令，而是 Brain 提出问题 → Codex 返回多个方案 → Brain 评估选择。

协商流程:
1. Brain 感知到问题 (体检/用户反馈/行为模式)
2. Brain 构造 NegotiationRequest
3. Codex 返回 NegotiationResponse (多方案)
4. Brain 评估方案 → 选择最优 / 请求用户确认
5. 执行选中方案 → 记录到进化日志
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from logs import get_logger

logger = get_logger("checkup.negotiation")


@dataclass
class Proposal:
    """单个方案。"""
    id: str
    title: str
    description: str
    approach: str           # fix_code | refactor | add_feature | config_change
    estimated_risk: str     # low | medium | high
    estimated_effort: str   # trivial | small | medium | large
    files_affected: list[str] = field(default_factory=list)
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NegotiationRequest:
    """Brain → Codex 的协商请求。"""
    id: str
    timestamp: str
    problem: str
    context: str = ""
    constraints: list[str] = field(default_factory=list)
    max_proposals: int = 3

    def to_dict(self) -> dict:
        return asdict(self)

    def to_prompt(self) -> str:
        """转换为发给 Codex 的 prompt。"""
        lines = [
            f"## 协商请求: {self.id}",
            f"",
            f"**问题**: {self.problem}",
        ]
        if self.context:
            lines.append(f"**上下文**: {self.context}")
        if self.constraints:
            lines.append(f"**约束**: {', '.join(self.constraints)}")
        lines.extend([
            f"",
            f"请提供最多 {self.max_proposals} 个方案，每个方案包含:",
            f"1. 标题和描述",
            f"2. 方法 (fix_code/refactor/add_feature/config_change)",
            f"3. 风险评估 (low/medium/high)",
            f"4. 工作量评估 (trivial/small/medium/large)",
            f"5. 涉及文件",
            f"6. 优缺点",
            f"",
            f"输出 JSON 格式:",
            f'```json',
            f'[{{"id":"A","title":"...","description":"...","approach":"...","estimated_risk":"...","estimated_effort":"...","files_affected":[],"pros":[],"cons":[]}}]',
            f'```',
        ])
        return "\n".join(lines)


@dataclass
class NegotiationResponse:
    """Codex → Brain 的协商响应。"""
    request_id: str
    proposals: list[Proposal] = field(default_factory=list)
    raw_response: str = ""

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "proposals": [p.to_dict() for p in self.proposals],
        }


@dataclass
class NegotiationDecision:
    """Brain 的决策记录。"""
    request_id: str
    selected_proposal_id: str
    decision: str = "approved"  # approved | approved_with_modification | rejected | deferred
    modification: str = ""
    decided_by: str = "brain"   # brain | user
    decided_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class NegotiationProtocol:
    """Brain-Codex 协商管理器。"""

    _counter = 0

    def create_request(self, problem: str, context: str = "",
                       constraints: list[str] | None = None) -> NegotiationRequest:
        """Brain 创建协商请求。"""
        NegotiationProtocol._counter += 1
        req = NegotiationRequest(
            id=f"NEG-{NegotiationProtocol._counter:04d}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            problem=problem,
            context=context,
            constraints=constraints or [],
        )
        logger.info(f"协商请求: {req.id} — {problem[:60]}")
        return req

    def parse_response(self, request_id: str, raw_text: str) -> NegotiationResponse:
        """解析 Codex 的响应为结构化方案。"""
        response = NegotiationResponse(request_id=request_id, raw_response=raw_text)

        # 尝试从 raw_text 中提取 JSON
        try:
            import re
            json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', raw_text, re.DOTALL)
            if json_match:
                proposals_data = json.loads(json_match.group(1))
            else:
                proposals_data = json.loads(raw_text)

            for p in proposals_data:
                response.proposals.append(Proposal(
                    id=p.get("id", "?"),
                    title=p.get("title", ""),
                    description=p.get("description", ""),
                    approach=p.get("approach", "fix_code"),
                    estimated_risk=p.get("estimated_risk", "medium"),
                    estimated_effort=p.get("estimated_effort", "small"),
                    files_affected=p.get("files_affected", []),
                    pros=p.get("pros", []),
                    cons=p.get("cons", []),
                ))
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning(f"协商响应解析失败: {e}")
            # 回退: 将整个响应作为单一方案
            response.proposals.append(Proposal(
                id="A",
                title="Codex 建议",
                description=raw_text[:500],
                approach="fix_code",
                estimated_risk="medium",
                estimated_effort="small",
            ))

        logger.info(f"协商响应: {request_id} → {len(response.proposals)} 个方案")
        return response

    def evaluate_proposals(self, proposals: list[Proposal]) -> Proposal | None:
        """Brain 自动评估: 选择风险最低、工作量最小的方案。"""
        if not proposals:
            return None

        risk_score = {"low": 0, "medium": 1, "high": 2}
        effort_score = {"trivial": 0, "small": 1, "medium": 2, "large": 3}

        ranked = sorted(proposals, key=lambda p: (
            risk_score.get(p.estimated_risk, 2),
            effort_score.get(p.estimated_effort, 2),
        ))
        best = ranked[0]
        logger.info(f"评估结果: 选择方案 {best.id} — {best.title} (risk={best.estimated_risk}, effort={best.estimated_effort})")
        return best

    def record_decision(self, request_id: str, proposal_id: str,
                        decision: str = "approved",
                        modification: str = "",
                        decided_by: str = "brain") -> NegotiationDecision:
        """记录决策。"""
        d = NegotiationDecision(
            request_id=request_id,
            selected_proposal_id=proposal_id,
            decision=decision,
            modification=modification,
            decided_by=decided_by,
            decided_at=datetime.now(timezone.utc).isoformat(),
        )
        logger.info(f"决策记录: {request_id} → {proposal_id} [{decision}]")
        return d
