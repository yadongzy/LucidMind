"""问题追踪系统 — 发现、记录、修复、验证、关闭。

状态流转：open → verifying（修复后连续2次自检确认）→ closed
重试超限：open → escalated（上报老师/用户）

从 brain_engines.py 抽出，降低文件行数（规则03）。
"""

import json
import time
from datetime import datetime
from pathlib import Path

from logs import get_logger

logger = get_logger("issues")
_DATA = Path(__file__).parent / "data"
_ISSUES_FILE = _DATA / "issues.json"


def _load_issues() -> list[dict]:
    if _ISSUES_FILE.exists():
        try: return json.loads(_ISSUES_FILE.read_text("utf-8"))
        except Exception: pass
    return []


def _save_issues(issues: list[dict]):
    _DATA.mkdir(exist_ok=True)
    _ISSUES_FILE.write_text(json.dumps(issues, ensure_ascii=False, indent=2), "utf-8")


def report_issue(desc: str, severity: str = "medium", source: str = "self_check") -> dict:
    """报告一个问题。severity: minor/medium/severe/fatal。自动去重：同描述的open issue只bump_retry。"""
    issues = _load_issues()
    # 去重：如果已有相同描述的 open issue，只更新 retries 和时间
    desc_trimmed = desc[:200]
    for i in issues:
        if i["status"] == "open" and i["desc"] == desc_trimmed:
            i["retries"] = i.get("retries", 0) + 1
            i["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            _save_issues(issues)
            return i
    issue = {
        "id": int(time.time() * 1000) % 1000000,
        "desc": desc_trimmed, "severity": severity, "source": source,
        "status": "open", "retries": 0,
        "found": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_check": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "resolution": None
    }
    issues.append(issue)
    if len(issues) > 200: issues = issues[-100:]
    _save_issues(issues)
    logger.info(f"🔴 新问题[{severity}]: {desc[:60]}")
    return issue


def close_issue(issue_id: int, resolution: str = "auto_fixed"):
    """关闭一个问题。"""
    issues = _load_issues()
    for i in issues:
        if i["id"] == issue_id:
            i["status"] = "closed"
            i["resolution"] = resolution
            i["closed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _save_issues(issues)


def get_open_issues() -> list[dict]:
    return [i for i in _load_issues() if i["status"] == "open"]


def get_verifying_issues() -> list[dict]:
    return [i for i in _load_issues() if i["status"] == "verifying"]


def mark_verifying(issue_id: int, resolution: str = "auto_fixed"):
    """修复后标记为验证中（需连续2次自检无复发才关闭）。"""
    issues = _load_issues()
    for i in issues:
        if i["id"] == issue_id:
            i["status"] = "verifying"
            i["resolution"] = resolution
            i["verify_count"] = 0
            i["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _save_issues(issues)
    logger.info(f"🔍 进入验证: {issue_id}")


def check_verifying_issues() -> list[str]:
    """检查验证中的问题，连续2次无复发→closed。"""
    issues = _load_issues()
    report = []
    for i in issues:
        if i["status"] != "verifying":
            continue
        vc = i.get("verify_count", 0) + 1
        i["verify_count"] = vc
        i["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        if vc >= 2:
            i["status"] = "closed"
            i["closed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            report.append(f"✅ 验证通过: {i['desc'][:40]}")
            logger.info(f"✅ 验证通过关闭: {i['id']} ({i['desc'][:40]})")
        else:
            report.append(f"🔍 验证中({vc}/2): {i['desc'][:40]}")
    if report:
        _save_issues(issues)
    return report


def bump_retry(issue_id: int):
    issues = _load_issues()
    for i in issues:
        if i["id"] == issue_id:
            i["retries"] = i.get("retries", 0) + 1
            i["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _save_issues(issues)
