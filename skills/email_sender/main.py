"""邮件发送插件 — 通过 SMTP 发送邮件。

需要在 .env 中配置:
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=your@email.com
  SMTP_PASS=your_app_password
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any

from ports.tool_port import ToolPort


class EmailSenderAdapter(ToolPort):

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {
                "name": "send_email",
                "description": "发送邮件（需要先配置 SMTP）。发送前会确认收件人和内容。",
                "parameters": {"type": "object", "properties": {
                    "to": {"type": "string", "description": "收件人邮箱地址"},
                    "subject": {"type": "string", "description": "邮件主题"},
                    "body": {"type": "string", "description": "邮件正文"},
                    "html": {"type": "boolean", "description": "是否为 HTML 格式（默认纯文本）"},
                }, "required": ["to", "subject", "body"]},
            }},
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "send_email":
            return self._send(params)
        return {"success": False, "error": f"未知工具: {tool_name}"}

    def _send(self, params: dict) -> dict:
        host = os.getenv("SMTP_HOST", "")
        port = int(os.getenv("SMTP_PORT", "587"))
        user = os.getenv("SMTP_USER", "")
        password = os.getenv("SMTP_PASS", "")

        if not all([host, user, password]):
            return {"success": False, "error": "SMTP 未配置。请在 .env 中设置 SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS"}

        to_addr = params.get("to", "")
        subject = params.get("subject", "")
        body = params.get("body", "")
        is_html = params.get("html", False)

        if not to_addr or not subject:
            return {"success": False, "error": "收件人和主题不能为空"}

        try:
            msg = MIMEMultipart()
            msg["From"] = user
            msg["To"] = to_addr
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "html" if is_html else "plain", "utf-8"))

            with smtplib.SMTP(host, port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.login(user, password)
                server.sendmail(user, [to_addr], msg.as_string())

            return {"success": True, "result": f"邮件已发送给 {to_addr}，主题: {subject}"}
        except Exception as e:
            return {"success": False, "error": f"邮件发送失败: {e}"}
