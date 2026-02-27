"""
tool_call_parser.py — 从 LLM 文本回复中解析 XML 格式的工具调用。

MiniMax-M1 等模型有时会将工具调用以 XML 文本形式输出，而非通过
function calling API 返回结构化 tool_calls。本模块负责：
1. 检测文本中是否包含 XML tool call
2. 解析并转换为标准 tool_calls 格式
3. 从文本中剥离已解析的 tool call XML（保留纯文本部分）

支持的 XML 格式：
  [tool_call]
  <invoke name="tool_name">
  <parameter name="key">value</parameter>
  </invoke>

  或带 minimax:tool_call 标签：
  <invoke name="tool_name">
  <parameter name="key">value</parameter>
  </invoke>
  </minimax:tool_call>
"""

import re
import json
import uuid
import logging

logger = logging.getLogger("lucid.tool_call_parser")

# 检测是否包含 XML tool call 的快速预检
_QUICK_CHECK_RE = re.compile(r'<invoke\s+name=', re.IGNORECASE)

# 提取 <invoke name="...">...</invoke> 块
_INVOKE_RE = re.compile(
    r'<invoke\s+name=["\'](\w+)["\'][^>]*>'
    r'([\s\S]*?)'
    r'</invoke>',
    re.IGNORECASE,
)

# 提取 <parameter name="...">...</parameter>
_PARAM_RE = re.compile(
    r'<parameter\s+name=["\'](\w+)["\']>\s*([\s\S]*?)\s*</parameter>',
    re.IGNORECASE,
)

# 剥离 XML tool call 相关标签（用于提取纯文本）
_STRIP_INVOKE_RE = re.compile(
    r'\[tool_call\]\s*'
    r'(?:<invoke\b[^>]*>[\s\S]*?</invoke>\s*'
    r'(?:</minimax:tool_call>\s*)?)',
    re.IGNORECASE,
)
_STRIP_INVOKE_ONLY_RE = re.compile(
    r'<invoke\b[^>]*>[\s\S]*?</invoke>\s*'
    r'(?:</minimax:tool_call>\s*)?',
    re.IGNORECASE,
)
_STRIP_MINIMAX_TAG_RE = re.compile(r'</?minimax:tool_call>', re.IGNORECASE)
_STRIP_TOOL_CALL_MARKER_RE = re.compile(r'\[tool_call\]\s*', re.IGNORECASE)


def has_xml_tool_calls(text: str) -> bool:
    """快速检测文本中是否可能包含 XML 格式的工具调用。"""
    if not text:
        return False
    return bool(_QUICK_CHECK_RE.search(text))


def parse_xml_tool_calls(text: str) -> list[dict]:
    """从文本中解析 XML 格式的工具调用。

    返回标准 tool_calls 格式:
    [{"id": "...", "type": "function",
      "function": {"name": "...", "arguments": "..."}}]

    如果没有找到有效的 XML tool call，返回空列表。
    """
    if not text or not has_xml_tool_calls(text):
        return []

    tool_calls = []
    for match in _INVOKE_RE.finditer(text):
        tool_name = match.group(1)
        invoke_body = match.group(2)

        params = {}
        for pm in _PARAM_RE.finditer(invoke_body):
            param_name = pm.group(1)
            param_value = pm.group(2).strip()
            params[param_name] = param_value

        if not tool_name:
            continue

        tc_id = f"xmltc_{tool_name}_{uuid.uuid4().hex[:8]}"
        tool_calls.append({
            "id": tc_id,
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps(params, ensure_ascii=False),
            },
        })

    if tool_calls:
        names = ", ".join(tc["function"]["name"] for tc in tool_calls)
        logger.info(f"🔧 XML解析: 从文本中提取到 {len(tool_calls)} 个工具调用: {names}")

    return tool_calls


def strip_xml_tool_calls(text: str) -> str:
    """从文本中移除 XML tool call 标记，保留纯文本部分。

    用于在解析并执行工具调用后，将干净的文本内容作为 assistant 回复。
    """
    if not text:
        return text

    # 移除 [tool_call] + <invoke>...</invoke> 块
    cleaned = _STRIP_INVOKE_RE.sub("", text)
    # 移除残留的 <invoke>...</invoke> 块
    cleaned = _STRIP_INVOKE_ONLY_RE.sub("", cleaned)
    # 移除残留的 minimax 标签
    cleaned = _STRIP_MINIMAX_TAG_RE.sub("", cleaned)
    # 移除残留的 [tool_call] 标记
    cleaned = _STRIP_TOOL_CALL_MARKER_RE.sub("", cleaned)

    return cleaned.strip()
