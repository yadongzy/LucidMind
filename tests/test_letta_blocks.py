"""Phase D Letta 增量模式测试 — MemoryBlock + BlockManager + MemoryToolAdapter。"""

import asyncio
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ─────────────── MemoryBlock 数据结构 ───────────────

def test_memory_block_defaults():
    from memory.letta_blocks import MemoryBlock
    b = MemoryBlock(name="test")
    assert b.name == "test"
    assert b.value == ""
    assert b.limit == 2000
    assert b.read_only is False
    assert b.usage == 0.0
    assert b.is_full is False


def test_memory_block_usage():
    from memory.letta_blocks import MemoryBlock
    b = MemoryBlock(name="test", value="x" * 500, limit=1000)
    assert b.usage == 0.5
    assert b.is_full is False


def test_memory_block_full():
    from memory.letta_blocks import MemoryBlock
    b = MemoryBlock(name="test", value="x" * 1000, limit=1000)
    assert b.is_full is True
    assert b.usage == 1.0


def test_memory_block_to_dict():
    from memory.letta_blocks import MemoryBlock
    b = MemoryBlock(name="persona", label="AI", value="Hello", limit=100)
    d = b.to_dict()
    assert d["name"] == "persona"
    assert d["char_count"] == 5
    assert d["usage"] == 0.05


# ─────────────── BlockManager CRUD ───────────────

@pytest.fixture
def bm(tmp_path):
    from memory.letta_blocks import BlockManager
    return BlockManager(persist_path=tmp_path / "blocks.json")


def test_create_block(bm):
    b = bm.create("test", label="Test Block", value="hello")
    assert b.name == "test"
    assert b.value == "hello"
    assert bm.get("test") is not None


def test_create_duplicate_raises(bm):
    bm.create("dup")
    with pytest.raises(ValueError):
        bm.create("dup")


def test_update_block(bm):
    bm.create("test", value="old")
    b = bm.update("test", "new")
    assert b.value == "new"


def test_update_nonexistent_raises(bm):
    with pytest.raises(KeyError):
        bm.update("nonexistent", "value")


def test_update_readonly_raises(bm):
    bm.create("locked", read_only=True, value="immutable")
    with pytest.raises(PermissionError):
        bm.update("locked", "changed")


def test_update_truncates(bm):
    bm.create("small", limit=10)
    b = bm.update("small", "x" * 50)
    assert len(b.value) == 10


def test_append_block(bm):
    bm.create("log", value="a")
    b = bm.append("log", "b")
    assert b.value == "ab"


def test_append_readonly_raises(bm):
    bm.create("locked", read_only=True, value="x")
    with pytest.raises(PermissionError):
        bm.append("locked", "y")


def test_delete_block(bm):
    bm.create("temp")
    assert bm.delete("temp") is True
    assert bm.get("temp") is None


def test_delete_nonexistent(bm):
    assert bm.delete("ghost") is False


def test_delete_readonly_raises(bm):
    bm.create("perm", read_only=True)
    with pytest.raises(PermissionError):
        bm.delete("perm")


def test_list_blocks(bm):
    bm.create("a")
    bm.create("b")
    assert len(bm.list_blocks()) == 2


# ─────────────── 持久化 ───────────────

def test_persistence(tmp_path):
    from memory.letta_blocks import BlockManager
    path = tmp_path / "blocks.json"
    bm1 = BlockManager(persist_path=path)
    bm1.create("persist_test", value="saved data")
    # 重新加载
    bm2 = BlockManager(persist_path=path)
    b = bm2.get("persist_test")
    assert b is not None
    assert b.value == "saved data"


# ─────────────── ensure_defaults ───────────────

def test_ensure_defaults(bm):
    bm.ensure_defaults()
    assert bm.get("persona") is not None
    assert bm.get("human") is not None
    assert bm.get("project") is not None
    assert bm.get("persona").read_only is True


def test_ensure_defaults_no_overwrite(bm):
    bm.create("human", value="existing user info")
    bm.ensure_defaults()
    assert bm.get("human").value == "existing user info"


# ─────────────── Block 分裂 ───────────────

def test_split_block(bm):
    # 创建一个 project 块，内容超过 limit
    bm.create("project", label="项目", limit=50)
    long_content = "\n\n".join([f"Section {i}: " + "x" * 30 for i in range(5)])
    b = bm.split_block("project", long_content)
    # 原块应被截断
    assert len(b.value) <= 50
    # 应创建子块
    blocks = bm.list_blocks()
    assert len(blocks) > 1
    sub_names = [bl.name for bl in blocks if bl.name.startswith("project-")]
    assert len(sub_names) > 0


def test_split_small_content_no_split(bm):
    bm.create("project", label="项目", limit=500, value="small")
    b = bm.split_block("project", "still small")
    assert b.value == "still small"
    assert len(bm.list_blocks()) == 1


# ─────────────── format_for_prompt ───────────────

def test_format_for_prompt(bm):
    bm.create("persona", value="I am LucidMind", read_only=True)
    bm.create("human", value="User likes Python")
    text = bm.format_for_prompt()
    assert "<persona>" in text
    assert "I am LucidMind" in text
    assert "<human>" in text
    assert "User likes Python" in text


def test_format_empty_blocks(bm):
    bm.create("empty", value="")
    assert bm.format_for_prompt() == ""


# ─────────────── MemoryToolAdapter ───────────────

@pytest.fixture
def tool(bm):
    from adapters.tools.memory_tool import MemoryToolAdapter
    bm.ensure_defaults()
    return MemoryToolAdapter(bm)


def test_tool_list_tools(tool):
    tools = tool.list_tools()
    names = [t["function"]["name"] for t in tools]
    assert "memory_read" in names
    assert "memory_write" in names
    assert "memory_append" in names


def test_tool_read_all(tool):
    result = asyncio.get_event_loop().run_until_complete(
        tool.execute("memory_read", {}))
    assert result["success"] is True
    assert result["result"]["total"] >= 3  # persona, human, project


def test_tool_read_specific(tool):
    result = asyncio.get_event_loop().run_until_complete(
        tool.execute("memory_read", {"name": "persona"}))
    assert result["success"] is True
    assert result["result"]["name"] == "persona"


def test_tool_read_nonexistent(tool):
    result = asyncio.get_event_loop().run_until_complete(
        tool.execute("memory_read", {"name": "ghost"}))
    assert result["success"] is False


def test_tool_write(tool):
    result = asyncio.get_event_loop().run_until_complete(
        tool.execute("memory_write", {"name": "human", "value": "Likes coffee"}))
    assert result["success"] is True
    assert result["result"]["value"] == "Likes coffee"


def test_tool_write_readonly(tool):
    result = asyncio.get_event_loop().run_until_complete(
        tool.execute("memory_write", {"name": "persona", "value": "evil"}))
    assert result["success"] is False
    assert "read-only" in result["error"]


def test_tool_append(tool):
    asyncio.get_event_loop().run_until_complete(
        tool.execute("memory_write", {"name": "human", "value": "A. "}))
    result = asyncio.get_event_loop().run_until_complete(
        tool.execute("memory_append", {"name": "human", "text": "B."}))
    assert result["success"] is True
    assert result["result"]["value"] == "A. B."


def test_tool_no_block_manager():
    from adapters.tools.memory_tool import MemoryToolAdapter
    tool = MemoryToolAdapter()
    result = asyncio.get_event_loop().run_until_complete(
        tool.execute("memory_read", {}))
    assert result["success"] is False
    assert "未初始化" in result["error"]
