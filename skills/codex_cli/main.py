"""Codex CLI ToolPort adapter — makes codex_explain/review/patch/fix_tests real Brain tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from skills.codex_cli.runner import CodexCliRunner


class CodexCliAdapter:
    """ToolPort-compatible adapter for Codex CLI skill.

    Exposes codex_explain, codex_review, codex_patch, codex_fix_tests
    as callable tools for the Brain's CompositeToolAdapter.
    """

    def __init__(self):
        root = os.environ.get("LUCIDMIND_PROJECT_ROOT", str(Path(__file__).resolve().parent.parent.parent))
        self._runner = CodexCliRunner(root)

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "codex_explain",
                    "description": "Ask Codex CLI to explain a repository area without writing files. Returns Codex analysis.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {
                                "type": "string",
                                "description": "File or directory path to explain (e.g. 'brain.py', 'adapters/tools/')",
                            },
                            "question": {
                                "type": "string",
                                "description": "Specific question about the target (default: explain the architecture)",
                            },
                        },
                        "required": ["target"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "codex_review",
                    "description": "Ask Codex CLI to review a file or diff for risks and correctness. Read-only, no writes.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {
                                "type": "string",
                                "description": "File or diff to review (e.g. 'governance/policy.py')",
                            },
                            "question": {
                                "type": "string",
                                "description": "Specific review focus (default: risks and correctness)",
                            },
                        },
                        "required": ["target"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "codex_patch",
                    "description": "Ask Codex CLI to generate and apply a patch. REQUIRES user approval — will be blocked without it.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {
                                "type": "string",
                                "description": "File to patch",
                            },
                            "instruction": {
                                "type": "string",
                                "description": "What changes to make",
                            },
                        },
                        "required": ["target", "instruction"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "codex_fix_tests",
                    "description": "Ask Codex CLI to fix failing tests. REQUIRES user approval.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "test_command": {
                                "type": "string",
                                "description": "The failing test command (e.g. 'pytest tests/test_brain.py -v')",
                            },
                        },
                        "required": ["test_command"],
                    },
                },
            },
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "codex_explain":
            result = self._runner.explain(params["target"], params.get("question", ""))
        elif tool_name == "codex_review":
            result = self._runner.review(params["target"], params.get("question", ""))
        elif tool_name == "codex_patch":
            result = self._runner.patch(params["target"], params["instruction"], approved=False)
        elif tool_name == "codex_fix_tests":
            result = self._runner.fix_tests(params["test_command"], approved=False)
        else:
            return {"success": False, "error": f"Unknown codex tool: {tool_name}"}

        if result.success:
            return {"success": True, "result": result.stdout or "(Codex returned no output)"}
        else:
            return {"success": False, "error": result.error, "result": result.stderr or result.stdout or ""}
