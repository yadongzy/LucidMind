"""S25: 语音基础 — Edge-TTS 文字转语音。

使用微软 Edge-TTS（免费），生成 MP3 音频文件。
新 Adapter，不修改 brain.py（规则 06）。
"""
from pathlib import Path
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools.tts")

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "output"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class TTSAdapter(ToolPort):
    """文字转语音工具：使用 Edge-TTS 生成音频。"""

    def list_tools(self) -> list[dict[str, Any]]:
        return [{
            "type": "function",
            "function": {
                "name": "text_to_speech",
                "description": "将文字转换为语音音频文件(MP3)。可选择不同的语音角色。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "要转换的文字"},
                        "voice": {"type": "string", "description": "语音角色，默认 zh-CN-XiaoxiaoNeural（中文女声）"},
                        "filename": {"type": "string", "description": "输出文件名（可选）"},
                    },
                    "required": ["text"],
                },
            },
        }]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "text_to_speech":
            return {"success": False, "result": None, "error": f"未知工具: {tool_name}"}
        return await self._tts(params)

    async def _tts(self, params: dict) -> dict[str, Any]:
        text = params.get("text", "").strip()
        if not text:
            return {"success": False, "result": None, "error": "文字为空"}
        voice = params.get("voice", "zh-CN-XiaoxiaoNeural")
        filename = params.get("filename", f"tts_{hash(text) & 0xFFFFFF:06x}.mp3")
        if not filename.endswith(".mp3"): filename += ".mp3"
        output_path = _OUTPUT_DIR / filename

        try:
            import edge_tts
            communicate = edge_tts.Communicate(text[:2000], voice)
            await communicate.save(str(output_path))
            logger.info(f"TTS完成: {output_path.name}, voice={voice}, {len(text)}字")
            return {"success": True, "result": f"已生成语音: /static/output/{filename} ({len(text)}字, {voice})", "error": None}
        except ImportError:
            return {"success": False, "result": None, "error": "需要 edge-tts: pip install edge-tts"}
        except Exception as e:
            logger.error(f"TTS失败: {e}")
            return {"success": False, "result": None, "error": f"TTS失败: {e}"}
