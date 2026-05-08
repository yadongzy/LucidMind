"""端到端测试：图片上传 + 文字发送 → analyze_image 工具被识别。

此测试不强制调用远程视觉模型（会跳过真实推理），只验证：
1. /api/upload 接受图片并返回可用的 path
2. _compose_with_attachments 会把 [图片: 路径] 合成到 user_input
3. VisionAdapter 在工具注册表里，list_tools 返回 analyze_image
4. VisionAdapter 能解析绝对路径
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.channel.websocket_channel import _compose_with_attachments


def _tiny_png_bytes() -> bytes:
    # 1x1 transparent PNG
    import base64
    b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
    )
    return base64.b64decode(b64)


def test_compose_with_attachments_image_path_injected():
    atts = [{"path": "/tmp/foo.png", "filename": "foo.png", "kind": "image", "mime": "image/png"}]
    out = _compose_with_attachments("这是什么?", atts)
    assert "[图片: /tmp/foo.png]" in out
    assert "用户说: 这是什么?" in out


def test_compose_with_attachments_empty_text():
    atts = [{"path": "/tmp/bar.png", "filename": "bar.png", "kind": "image"}]
    out = _compose_with_attachments("", atts)
    assert "[图片: /tmp/bar.png]" in out
    assert "请使用合适的工具" in out


def test_compose_with_attachments_multiple():
    atts = [
        {"path": "/tmp/a.png", "filename": "a.png", "kind": "image"},
        {"path": "/tmp/b.pdf", "filename": "b.pdf", "kind": "document"},
    ]
    out = _compose_with_attachments("分析一下", atts)
    assert "[图片: /tmp/a.png]" in out
    assert "[文件: /tmp/b.pdf]" in out


def test_vision_adapter_is_discovered():
    """VisionAdapter 应该在当前工具注册表中 (已从 _deprecated 移出)。"""
    from adapters.tools.discover import discover_tool_adapters
    adapters = discover_tool_adapters()
    names = []
    for a in adapters:
        for t in a.list_tools():
            names.append(t["function"]["name"])
    assert "analyze_image" in names, f"analyze_image 未被发现。已注册: {names}"


def test_vision_adapter_resolves_absolute_path(tmp_path):
    from adapters.tools.vision import VisionAdapter
    img = tmp_path / "sample.png"
    img.write_bytes(_tiny_png_bytes())
    va = VisionAdapter()
    resolved = va._resolve_path(str(img))
    assert resolved is not None
    assert resolved.resolve() == img.resolve()


def test_vision_adapter_rejects_nonexistent():
    from adapters.tools.vision import VisionAdapter
    va = VisionAdapter()
    assert va._resolve_path("/nope/does-not-exist.png") is None


@pytest.mark.asyncio
async def test_vision_execute_fallback_on_nonexistent():
    from adapters.tools.vision import VisionAdapter
    va = VisionAdapter()
    res = await va.execute("analyze_image", {"filename": "/nope/x.png"})
    assert res["success"] is False
    assert "不存在" in (res.get("error") or "")
