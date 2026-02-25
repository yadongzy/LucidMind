"""Tests for GUI Automation and Vision adapters."""
import asyncio
import platform
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path


# ── GUI Automation Tests ──

class TestGUIAutomationAdapter:
    """gui_automation.py 的单元测试。"""

    def _make_adapter(self):
        from adapters.tools.gui_automation import GUIAutomationAdapter
        return GUIAutomationAdapter()

    def test_list_tools_returns_four(self):
        """正向：list_tools 返回 4 个工具定义。"""
        adapter = self._make_adapter()
        tools = adapter.list_tools()
        names = [t["function"]["name"] for t in tools]
        assert set(names) == {"gui_mouse", "gui_keyboard", "gui_screen", "gui_window"}

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        """异常：未知工具名返回错误。"""
        adapter = self._make_adapter()
        r = await adapter.execute("gui_nonexistent", {})
        assert r["success"] is False
        assert "未知工具" in r["error"]

    @pytest.mark.asyncio
    async def test_mouse_missing_coords(self):
        """异常：鼠标点击缺少坐标。"""
        adapter = self._make_adapter()
        r = await adapter.execute("gui_mouse", {"action": "click"})
        assert r["success"] is False
        assert "坐标" in r.get("error", "") or "x" in r.get("error", "")

    @pytest.mark.asyncio
    async def test_keyboard_missing_text(self):
        """异常：键盘操作缺少 text 参数。"""
        adapter = self._make_adapter()
        r = await adapter.execute("gui_keyboard", {"action": "type", "text": ""})
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_window_non_darwin(self):
        """异常：非 macOS 平台窗口操作返回错误。"""
        adapter = self._make_adapter()
        with patch("platform.system", return_value="Linux"):
            r = await adapter.execute("gui_window", {"action": "list"})
            assert r["success"] is False
            assert "macOS" in r["error"]

    @pytest.mark.asyncio
    async def test_clipboard_non_darwin(self):
        """异常：非 macOS 平台剪贴板输入返回错误。"""
        adapter = self._make_adapter()
        with patch("platform.system", return_value="Linux"):
            r = await adapter._type_via_clipboard("test")
            assert r["success"] is False
            assert "macOS" in r["error"]

    @pytest.mark.asyncio
    async def test_mouse_position(self):
        """正向：获取鼠标位置（mock pyautogui）。"""
        adapter = self._make_adapter()
        mock_pos = MagicMock()
        mock_pos.x = 100
        mock_pos.y = 200
        with patch("pyautogui.position", return_value=mock_pos):
            r = await adapter.execute("gui_mouse", {"action": "position"})
            assert r["success"] is True
            assert "100" in r["result"] and "200" in r["result"]

    @pytest.mark.asyncio
    async def test_hotkey_has_delay(self):
        """正向：hotkey 操作后有延迟（防止 'l' 前缀 bug）。"""
        adapter = self._make_adapter()
        with patch("pyautogui.hotkey"):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                r = await adapter.execute("gui_keyboard", {"action": "hotkey", "text": "cmd+l"})
                assert r["success"] is True
                mock_sleep.assert_called_with(0.3)


# ── Vision Adapter Tests ──

class TestVisionAdapter:
    """vision.py 的单元测试。"""

    def _make_adapter(self):
        from adapters.tools.vision import VisionAdapter
        return VisionAdapter()

    def test_list_tools(self):
        """正向：list_tools 返回 analyze_image。"""
        adapter = self._make_adapter()
        tools = adapter.list_tools()
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "analyze_image"

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        """异常：图片不存在返回错误。"""
        adapter = self._make_adapter()
        r = await adapter.execute("analyze_image", {"filename": "nonexistent_abc123.png"})
        assert r["success"] is False
        assert "不存在" in r["error"]

    @pytest.mark.asyncio
    async def test_unsupported_format(self):
        """异常：不支持的图片格式。"""
        adapter = self._make_adapter()
        # 创建临时 txt 文件
        tmp = Path("/tmp/test_vision.txt")
        tmp.write_text("not an image")
        try:
            r = await adapter.execute("analyze_image", {"filename": str(tmp)})
            assert r["success"] is False
            assert "不支持" in r["error"]
        finally:
            tmp.unlink(missing_ok=True)

    def test_resolve_path_absolute(self):
        """正向：绝对路径解析。"""
        adapter = self._make_adapter()
        # 用一个已知存在的文件测试
        p = adapter._resolve_path(__file__)
        assert p is not None

    def test_resolve_path_nonexistent(self):
        """异常：不存在的文件返回 None。"""
        adapter = self._make_adapter()
        p = adapter._resolve_path("totally_fake_image_xyz.png")
        assert p is None

    @pytest.mark.asyncio
    async def test_ollama_llava_called_first(self):
        """正向：优先调用本地 Ollama llava。"""
        adapter = self._make_adapter()
        # 创建临时图片
        from PIL import Image
        tmp = Path("/tmp/test_vision_llava.png")
        Image.new("RGB", (10, 10), (255, 0, 0)).save(str(tmp))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": "A red image"}}

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            r = await adapter.execute("analyze_image", {"filename": str(tmp)})
            assert r["success"] is True
            assert "red" in r["result"].lower() or "A red image" in r["result"]
            # 验证调用的是 Ollama URL
            call_args = mock_client.post.call_args
            assert "11434" in str(call_args) or "ollama" in str(call_args).lower()

        tmp.unlink(missing_ok=True)
