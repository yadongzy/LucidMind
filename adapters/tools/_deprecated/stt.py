"""S37: STT Adapter — 语音转文字（Speech-to-Text）。

使用 Whisper API 或本地 faster-whisper 做语音识别。
降级方案: 无模型时返回提示信息。
"""
import os
import asyncio
from pathlib import Path
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("stt")

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "uploads"


class STTAdapter(ToolPort):
    """语音转文字适配器。"""

    def __init__(self):
        self._whisper_model = None
        self._model_loaded = False

    def _ensure_model(self):
        """延迟加载 whisper 模型。"""
        if self._model_loaded:
            return
        self._model_loaded = True
        try:
            import whisper
            self._whisper_model = whisper.load_model("base")
            logger.info("Whisper 模型已加载 (base)")
        except ImportError:
            logger.info("whisper 未安装，STT 使用降级模式")
        except Exception as e:
            logger.warning(f"Whisper 加载失败: {e}")

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "speech_to_text":
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        audio_path = params.get("audio_path", "")
        if not audio_path:
            return {"success": False, "error": "缺少 audio_path 参数"}
        p = Path(audio_path)
        if not p.exists():
            # 尝试在 uploads 目录查找
            p = _OUTPUT_DIR / audio_path
        if not p.exists():
            return {"success": False, "error": f"音频文件不存在: {audio_path}"}

        self._ensure_model()

        if self._whisper_model:
            try:
                result = await asyncio.to_thread(
                    self._whisper_model.transcribe, str(p), language=params.get("language")
                )
                text = result.get("text", "").strip()
                lang = result.get("language", "unknown")
                logger.info(f"STT 完成: {text[:60]}... (lang={lang})")
                return {"success": True, "result": f"识别结果: {text}\n语言: {lang}"}
            except Exception as e:
                return {"success": False, "error": f"语音识别失败: {e}"}
        else:
            # 降级: 返回文件信息
            size_kb = p.stat().st_size / 1024
            return {"success": True, "result": f"音频文件: {p.name} ({size_kb:.1f}KB)\n"
                    f"提示: 安装 openai-whisper 可启用语音识别 (pip install openai-whisper)"}

    def list_tools(self) -> list[dict[str, Any]]:
        return [{
            "type": "function",
            "function": {
                "name": "speech_to_text",
                "description": "语音转文字 — 将音频文件转换为文本。支持 mp3/wav/m4a 等格式。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "audio_path": {"type": "string", "description": "音频文件路径"},
                        "language": {"type": "string", "description": "语言代码(可选，如 zh/en)"},
                    },
                    "required": ["audio_path"],
                },
            },
        }]
