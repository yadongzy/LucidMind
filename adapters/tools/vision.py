"""S24: 图片视觉理解 — 通过多模态LLM分析图片内容。

调用 DeepSeek-VL 或兼容的多模态 API，将图片 base64 编码后发送。
新 Adapter，不修改 brain.py（规则 06）。
"""
import asyncio
import base64
import os
from pathlib import Path
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools.vision")

_UPLOAD_DIR = Path(__file__).parent.parent.parent / "data" / "uploads"


class VisionAdapter(ToolPort):
    """图片视觉理解工具：通过多模态LLM分析图片。"""

    def __init__(self):
        self._api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self._base_url = os.getenv("VISION_API_URL", "https://api.deepseek.com/v1")

    def list_tools(self) -> list[dict[str, Any]]:
        return [{
            "type": "function",
            "function": {
                "name": "analyze_image",
                "description": "分析图片内容：识别物体、文字、场景、图表数据等。传入图片文件名或路径。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "图片文件名或路径"},
                        "question": {"type": "string", "description": "关于图片的具体问题（可选）"},
                    },
                    "required": ["filename"],
                },
            },
        }]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "analyze_image":
            return {"success": False, "result": None, "error": f"未知工具: {tool_name}"}
        return await self._analyze(params)

    def _resolve_path(self, filename: str) -> Path | None:
        p = Path(filename)
        if p.is_absolute() and p.exists(): return p
        # 在项目根目录下查找（支持相对路径如 data/screenshots/xxx.png）
        root = Path(__file__).parent.parent.parent
        rp = root / filename
        if rp.exists(): return rp
        # 在 uploads 和 screenshots 目录下查找
        for d in (_UPLOAD_DIR, root / "data" / "screenshots"):
            fp = d / filename
            if fp.exists(): return fp
            if d.exists():
                for f in d.iterdir():
                    if filename in f.name and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
                        return f
        return None

    async def _analyze(self, params: dict) -> dict[str, Any]:
        filename = params.get("filename", "")
        question = params.get("question", "请详细描述这张图片的内容。")
        path = self._resolve_path(filename)
        if not path:
            return {"success": False, "result": None, "error": f"图片不存在: {filename}"}

        ext = path.suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
            return {"success": False, "result": None, "error": f"不支持的图片格式: {ext}"}

        img_data = path.read_bytes()
        b64 = base64.b64encode(img_data).decode("utf-8")

        try:
            from PIL import Image
            img = Image.open(str(path))
            w, h = img.size
            basic_info = f"图片: {path.name}, 尺寸: {w}x{h}, 格式: {ext}"
        except Exception:
            basic_info = f"图片: {path.name}, 格式: {ext}"

        # 优先使用本地 Ollama llava（多模态视觉模型）
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        vision_model = os.getenv("VISION_MODEL", "llava")
        try:
            import httpx
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(f"{ollama_url}/api/chat", json={
                    "model": vision_model,
                    "messages": [{"role": "user", "content": question, "images": [b64]}],
                    "stream": False,
                })
                if resp.status_code == 200:
                    analysis = resp.json()["message"]["content"]
                    logger.info(f"视觉分析完成(llava): {path.name}, {len(analysis)}字")
                    return {"success": True, "result": f"{basic_info}\n\n分析结果:\n{analysis}", "error": None}
                logger.warning(f"Ollama llava 不可用({resp.status_code}), 尝试远程API")
        except Exception as e:
            logger.warning(f"Ollama llava 调用失败: {e}, 尝试远程API")

        # 备用：远程多模态 API
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "bmp": "image/bmp", "webp": "image/webp"}.get(ext.lstrip("."), "image/png")
        if self._api_key:
            try:
                import httpx
                headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
                payload = {
                    "model": os.getenv("VISION_REMOTE_MODEL", "deepseek-chat"),
                    "messages": [{"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                        {"type": "text", "text": question},
                    ]}],
                    "max_tokens": 1000,
                }
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(f"{self._base_url}/chat/completions", json=payload, headers=headers)
                    if resp.status_code == 200:
                        analysis = resp.json()["choices"][0]["message"]["content"]
                        logger.info(f"视觉分析完成(remote): {path.name}, {len(analysis)}字")
                        return {"success": True, "result": f"{basic_info}\n\n分析结果:\n{analysis}", "error": None}
            except Exception as e:
                logger.warning(f"远程多模态调用失败: {e}")

        return self._fallback_analyze(path, basic_info, question)

    def _fallback_analyze(self, path: Path, basic_info: str, question: str) -> dict[str, Any]:
        """降级分析：无多模态LLM时，用PIL提取基本信息。"""
        try:
            from PIL import Image
            img = Image.open(str(path))
            w, h = img.size
            colors = img.getcolors(maxcolors=256*256) if img.mode in ("RGB", "RGBA", "P") else None
            dominant = ""
            if colors:
                colors.sort(key=lambda x: x[0], reverse=True)
                dominant = f"\n主要颜色(前5): {colors[:5]}"
            hist = img.histogram()
            brightness = sum(hist[:256]) / max(sum(hist), 1)
            result = f"{basic_info}\n模式: {img.mode}\n宽高比: {w/h:.2f}{dominant}\n亮度分布: {'偏亮' if brightness > 0.5 else '偏暗'}"
            result += f"\n\n(注: 多模态LLM不可用，仅提供基本图片属性分析。完整内容识别需要多模态模型支持。)"
            return {"success": True, "result": result, "error": None}
        except Exception as e:
            return {"success": True, "result": f"{basic_info}\n(基本分析失败: {e})", "error": None}
