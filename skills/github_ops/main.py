"""GitHub 操作插件 — Issue/PR 查询和创建。

需要在 .env 中配置: GITHUB_TOKEN=ghp_xxxxx
"""

import json
import os
import urllib.request
from typing import Any

from ports.tool_port import ToolPort

_API = "https://api.github.com"


class GitHubOpsAdapter(ToolPort):

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {
                "name": "gh_issues",
                "description": "列出 GitHub 仓库的 Issues",
                "parameters": {"type": "object", "properties": {
                    "repo": {"type": "string", "description": "仓库，格式 owner/repo"},
                    "state": {"type": "string", "description": "状态: open/closed/all（默认 open）"},
                    "limit": {"type": "integer", "description": "数量（默认10）"},
                }, "required": ["repo"]},
            }},
            {"type": "function", "function": {
                "name": "gh_create_issue",
                "description": "创建 GitHub Issue",
                "parameters": {"type": "object", "properties": {
                    "repo": {"type": "string", "description": "仓库，格式 owner/repo"},
                    "title": {"type": "string", "description": "Issue 标题"},
                    "body": {"type": "string", "description": "Issue 正文（Markdown）"},
                    "labels": {"type": "string", "description": "标签，逗号分隔（可选）"},
                }, "required": ["repo", "title"]},
            }},
            {"type": "function", "function": {
                "name": "gh_prs",
                "description": "列出 GitHub 仓库的 Pull Requests",
                "parameters": {"type": "object", "properties": {
                    "repo": {"type": "string", "description": "仓库，格式 owner/repo"},
                    "state": {"type": "string", "description": "状态: open/closed/all（默认 open）"},
                }, "required": ["repo"]},
            }},
            {"type": "function", "function": {
                "name": "gh_repo_info",
                "description": "获取 GitHub 仓库基本信息",
                "parameters": {"type": "object", "properties": {
                    "repo": {"type": "string", "description": "仓库，格式 owner/repo"},
                }, "required": ["repo"]},
            }},
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        token = os.getenv("GITHUB_TOKEN", "")
        if not token:
            return {"success": False, "error": "未配置 GITHUB_TOKEN。请在 .env 中设置。"}
        if tool_name == "gh_issues":
            return self._issues(token, params)
        elif tool_name == "gh_create_issue":
            return self._create_issue(token, params)
        elif tool_name == "gh_prs":
            return self._prs(token, params)
        elif tool_name == "gh_repo_info":
            return self._repo_info(token, params)
        return {"success": False, "error": f"未知工具: {tool_name}"}

    def _api_call(self, token: str, method: str, path: str, data: dict | None = None) -> dict:
        url = f"{_API}{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, method=method, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "LucidMind/1.0",
            "Content-Type": "application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    def _issues(self, token: str, params: dict) -> dict:
        repo = params.get("repo", "")
        state = params.get("state", "open")
        limit = params.get("limit", 10)
        try:
            data = self._api_call(token, "GET", f"/repos/{repo}/issues?state={state}&per_page={limit}")
            issues = [{"number": i["number"], "title": i["title"], "state": i["state"],
                       "user": i["user"]["login"], "labels": [l["name"] for l in i.get("labels", [])]}
                      for i in data if "pull_request" not in i]
            return {"success": True, "result": f"{repo}: {len(issues)} issues ({state})", "issues": issues}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_issue(self, token: str, params: dict) -> dict:
        repo = params.get("repo", "")
        title = params.get("title", "")
        body = params.get("body", "")
        labels = [l.strip() for l in params.get("labels", "").split(",") if l.strip()]
        try:
            payload = {"title": title, "body": body}
            if labels:
                payload["labels"] = labels
            data = self._api_call(token, "POST", f"/repos/{repo}/issues", payload)
            return {"success": True, "result": f"Issue #{data['number']} 已创建: {data['html_url']}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _prs(self, token: str, params: dict) -> dict:
        repo = params.get("repo", "")
        state = params.get("state", "open")
        try:
            data = self._api_call(token, "GET", f"/repos/{repo}/pulls?state={state}&per_page=10")
            prs = [{"number": p["number"], "title": p["title"], "state": p["state"],
                    "user": p["user"]["login"], "head": p["head"]["ref"]} for p in data]
            return {"success": True, "result": f"{repo}: {len(prs)} PRs ({state})", "prs": prs}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _repo_info(self, token: str, params: dict) -> dict:
        repo = params.get("repo", "")
        try:
            d = self._api_call(token, "GET", f"/repos/{repo}")
            info = {
                "name": d["full_name"], "description": d.get("description", ""),
                "stars": d["stargazers_count"], "forks": d["forks_count"],
                "language": d.get("language", ""), "open_issues": d["open_issues_count"],
                "default_branch": d["default_branch"], "url": d["html_url"],
            }
            return {"success": True, "result": f"{info['name']}: ⭐{info['stars']} 🍴{info['forks']}", "info": info}
        except Exception as e:
            return {"success": False, "error": str(e)}
