"""Skill Scanner — 安装前静态安全扫描。

对标 OpenClaw src/security/skill-scanner.ts:
- 检测 shell exec、eval、crypto mining、env harvesting、数据外泄
- 安装前扫描，阻止危险 skill 进入系统

扫描等级:
- CRITICAL: 直接拒绝安装（挖矿、数据外泄、恶意网络）
- WARNING: 警告但允许安装（eval、subprocess、env 读取）
- INFO: 仅记录（动态导入等）
"""

import json
import re
import pathlib
import time
from atomic_persistence import append_jsonl
from typing import Any

from logs import get_logger

logger = get_logger("skill-scanner")

_SCAN_EXTENSIONS = {".py", ".js", ".sh", ".bat", ".ps1"}
_MAX_SCAN_FILE_SIZE = 1024 * 1024  # 1MB
_SCAN_HISTORY_PATH = pathlib.Path(__file__).parent.parent / "data" / "scan_history.jsonl"

# ─────────────────── 危险模式定义 ───────────────────

PATTERNS: list[dict[str, Any]] = [
    # CRITICAL — 直接拒绝
    {"name": "crypto_mining", "level": "critical",
     "regex": r"(stratum\+tcp|mining|cryptonight|xmrig|hashrate)",
     "description": "疑似加密货币挖矿代码"},
    {"name": "data_exfiltration", "level": "critical",
     "regex": r"(requests\.post|urllib\.request\.urlopen|httpx\.post)\s*\([^)]*?(password|secret|token|key|credential)",
     "description": "疑似数据外泄（将敏感信息发送到外部）"},
    {"name": "reverse_shell", "level": "critical",
     "regex": r"(socket\.connect|nc\s+-[elp]|/bin/(ba)?sh\s+-i|bash\s+-c.*?/dev/tcp)",
     "description": "疑似反向 Shell"},
    {"name": "malicious_download", "level": "critical",
     "regex": r"(curl|wget)\s+.*?\|\s*(ba)?sh",
     "description": "疑似下载并执行恶意脚本"},

    # WARNING — 警告但允许
    {"name": "shell_exec", "level": "warning",
     "regex": r"(subprocess\.(run|call|Popen|check_output)|os\.system|os\.popen)",
     "description": "Shell 命令执行"},
    {"name": "eval_exec", "level": "warning",
     "regex": r"\b(eval|exec|compile)\s*\(",
     "description": "动态代码执行 (eval/exec)"},
    {"name": "env_harvesting", "level": "warning",
     "regex": r"os\.environ\s*(\[|\.get\()",
     "description": "环境变量读取（可能泄露密钥）"},
    {"name": "file_system_write", "level": "warning",
     "regex": r"(open\s*\([^)]*['\"]w['\"]|\.write_text|\.write_bytes|shutil\.(rmtree|move|copy))",
     "description": "文件系统写入操作"},
    {"name": "network_request", "level": "warning",
     "regex": r"(import\s+(requests|httpx|aiohttp|urllib)|from\s+(requests|httpx|aiohttp|urllib))",
     "description": "网络请求库导入"},
    {"name": "ctypes_access", "level": "warning",
     "regex": r"(import\s+ctypes|from\s+ctypes)",
     "description": "C 层访问 (ctypes)"},

    # CRITICAL — 新增
    {"name": "base64_exec", "level": "critical",
     "regex": r"base64\.(b64)?decode.*?(exec|eval|subprocess)",
     "description": "Base64 解码后执行代码（常见混淆手法）"},
    {"name": "webhook_exfil", "level": "critical",
     "regex": r"(discord\.com/api/webhooks|hooks\.slack\.com)",
     "description": "向 Discord/Slack Webhook 发送数据"},

    # WARNING — 新增
    {"name": "global_var_write", "level": "warning",
     "regex": r"globals\(\)\[|setattr\(.*?__builtins__",
     "description": "修改全局变量或内建函数"},
    {"name": "temp_file_exec", "level": "warning",
     "regex": r"tempfile\..*(?:write|open).*?(?:exec|subprocess|os\.system)",
     "description": "写入临时文件后执行"},

    # INFO — 仅记录
    {"name": "dynamic_import", "level": "info",
     "regex": r"(__import__|importlib\.import_module)",
     "description": "动态模块导入"},
    {"name": "pickle_usage", "level": "info",
     "regex": r"(import\s+pickle|pickle\.(loads?|dumps?))",
     "description": "Pickle 序列化（反序列化可执行任意代码）"},
    {"name": "threading_usage", "level": "info",
     "regex": r"(import\s+threading|threading\.Thread)",
     "description": "多线程使用"},
]


def scan_file(filepath: pathlib.Path) -> list[dict]:
    """扫描单个文件，返回发现的问题列表。"""
    findings = []

    # 文件大小保护
    try:
        fsize = filepath.stat().st_size
    except OSError:
        fsize = 0
    if fsize > _MAX_SCAN_FILE_SIZE:
        logger.warning(f"⚠️ 文件过大跳过扫描: {filepath.name} ({fsize // 1024}KB > 1MB)")
        return [{"file": str(filepath.name), "level": "warning",
                 "pattern": "file_too_large", "description": f"文件过大({fsize // 1024}KB)，跳过扫描",
                 "line": 0, "match": ""}]

    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return [{"file": str(filepath), "level": "error",
                 "pattern": "read_error", "description": f"文件读取失败: {e}",
                 "line": 0, "match": ""}]

    in_multiline_comment = False
    for lineno, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        # 跳过单行注释
        if stripped.startswith("#"):
            continue
        # 跳过多行字符串/注释（简化处理：三引号切换）
        if '"""' in stripped or "'''" in stripped:
            count = stripped.count('"""') + stripped.count("'''")
            if count % 2 == 1:
                in_multiline_comment = not in_multiline_comment
            continue
        if in_multiline_comment:
            continue
        for pat in PATTERNS:
            m = re.search(pat["regex"], line, re.IGNORECASE)
            if m:
                findings.append({
                    "file": str(filepath.name),
                    "level": pat["level"],
                    "pattern": pat["name"],
                    "description": pat["description"],
                    "line": lineno,
                    "match": m.group(0)[:80],
                })
    return findings


def scan_skill_directory(skill_dir: pathlib.Path) -> dict:
    """扫描整个 skill 目录，返回扫描报告。

    Returns:
        {
            "safe": bool,          # True = 可以安装
            "block": bool,         # True = 存在 CRITICAL，应阻止安装
            "findings": [...],     # 所有发现
            "summary": str,        # 人类可读摘要
            "critical": int,
            "warnings": int,
            "info": int,
        }
    """
    if not skill_dir.is_dir():
        return {"safe": True, "block": False, "findings": [],
                "summary": "目录不存在，跳过扫描", "critical": 0, "warnings": 0, "info": 0}

    all_findings = []
    scan_files = [f for f in skill_dir.rglob("*") if f.is_file() and f.suffix in _SCAN_EXTENSIONS]
    for f in scan_files:
        all_findings.extend(scan_file(f))

    critical = sum(1 for f in all_findings if f["level"] == "critical")
    warnings = sum(1 for f in all_findings if f["level"] == "warning")
    info = sum(1 for f in all_findings if f["level"] == "info")
    block = critical > 0
    safe = critical == 0 and warnings == 0

    parts = []
    if critical:
        parts.append(f"🚫 {critical} 个严重问题")
    if warnings:
        parts.append(f"⚠️ {warnings} 个警告")
    if info:
        parts.append(f"ℹ️ {info} 个提示")
    if not parts:
        parts.append("✅ 未发现安全问题")
    summary = f"扫描 {skill_dir.name}: {', '.join(parts)}"

    logger.info(summary)
    if block:
        for f in all_findings:
            if f["level"] == "critical":
                logger.warning(f"  🚫 {f['file']}:{f['line']} — {f['description']}: {f['match']}")

    result = {
        "safe": safe,
        "block": block,
        "findings": all_findings,
        "summary": summary,
        "critical": critical,
        "warnings": warnings,
        "info": info,
    }
    # 扫描结果持久化
    _persist_scan_result(skill_dir.name, result)
    return result


def _persist_scan_result(plugin_name: str, result: dict) -> None:
    """将扫描结果追加写入 scan_history.jsonl。"""
    try:
        _SCAN_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": time.time(),
            "plugin": plugin_name,
            "safe": result["safe"],
            "block": result["block"],
            "critical": result["critical"],
            "warnings": result["warnings"],
            "info": result["info"],
            "summary": result["summary"],
        }
        append_jsonl(_SCAN_HISTORY_PATH, record)
    except Exception as e:
        logger.warning(f"扫描历史持久化失败: {e}")


def get_scan_history(limit: int = 50) -> list[dict]:
    """读取最近的扫描历史记录。"""
    if not _SCAN_HISTORY_PATH.exists():
        return []
    try:
        lines = _SCAN_HISTORY_PATH.read_text("utf-8").strip().splitlines()
        records = []
        for line in lines[-limit:]:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records
    except Exception:
        return []
