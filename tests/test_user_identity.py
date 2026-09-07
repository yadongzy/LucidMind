"""测试多用户身份管理系统。

覆盖:
1. 用户目录创建与模板复制
2. 系统级文件（CORE.md）不复制到用户目录
3. 用户级文件 fallback 到系统默认
4. 自定义提示词加载
5. 自定义人格加载
6. build_identity_prompt 完整拼装
7. 多用户隔离
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from identity.user_identity import UserIdentityManager


@pytest.fixture
def tmp_dirs(tmp_path):
    """创建临时的系统身份目录和用户数据目录。"""
    sys_dir = tmp_path / "identity"
    sys_dir.mkdir()
    data_dir = tmp_path / "data"
    users_dir = data_dir / "users"
    users_dir.mkdir(parents=True)

    # 创建系统默认模板
    (sys_dir / "CORE.md").write_text("# Immutable Core Rules\nSafety rules", encoding="utf-8")
    (sys_dir / "SOUL.md").write_text("# SOUL Default\nI am LucidMind", encoding="utf-8")
    (sys_dir / "USER.md").write_text("# 用户画像\n待填写", encoding="utf-8")
    (sys_dir / "BOOTSTRAP.md").write_text("# 首次引导\n你好！", encoding="utf-8")

    return sys_dir, users_dir


@pytest.fixture
def mgr(tmp_dirs):
    """创建指向临时目录的 UserIdentityManager。"""
    sys_dir, users_dir = tmp_dirs
    m = UserIdentityManager()
    # Monkey-patch 路径
    import identity.user_identity as mod
    original_sys = mod._SYSTEM_IDENTITY_DIR
    original_users = mod._USERS_DIR
    mod._SYSTEM_IDENTITY_DIR = sys_dir
    mod._USERS_DIR = users_dir
    yield m
    mod._SYSTEM_IDENTITY_DIR = original_sys
    mod._USERS_DIR = original_users


class TestUserDirCreation:
    """用户目录创建与模板复制。"""

    def test_ensure_user_dir_creates_directory(self, mgr, tmp_dirs):
        _, users_dir = tmp_dirs
        user_dir = mgr.ensure_user_dir("alice")
        assert user_dir.exists()
        assert (user_dir / "custom_prompts").exists()
        assert (user_dir / "personas").exists()

    def test_ensure_user_dir_copies_templates(self, mgr, tmp_dirs):
        _, users_dir = tmp_dirs
        user_dir = mgr.ensure_user_dir("bob")
        assert (user_dir / "SOUL.md").exists()
        assert (user_dir / "USER.md").exists()
        assert (user_dir / "BOOTSTRAP.md").exists()
        # 系统级文件不复制
        assert not (user_dir / "CORE.md").exists()

    def test_ensure_user_dir_idempotent(self, mgr, tmp_dirs):
        _, users_dir = tmp_dirs
        dir1 = mgr.ensure_user_dir("charlie")
        # 修改用户的 SOUL.md
        (dir1 / "SOUL.md").write_text("# 自定义灵魂", encoding="utf-8")
        dir2 = mgr.ensure_user_dir("charlie")
        # 不应覆盖用户的自定义内容
        assert (dir2 / "SOUL.md").read_text() == "# 自定义灵魂"


class TestSystemFiles:
    """系统级文件（所有用户共享）。"""

    def test_get_core_returns_system_file(self, mgr):
        core = mgr.get_core()
        assert "Immutable Core Rules" in core


class TestUserFiles:
    """用户级文件（per-user, fallback）。"""

    def test_get_soul_fallback_to_system(self, mgr):
        """未初始化用户目录时，fallback 到系统默认。"""
        soul = mgr.get_soul("unknown_user")
        assert "SOUL Default" in soul

    def test_get_soul_user_override(self, mgr, tmp_dirs):
        """用户自定义 SOUL.md 覆盖系统默认。"""
        mgr.ensure_user_dir("dave")
        mgr.update_soul("dave", "# Dave的灵魂\n我是Dave的AI")
        soul = mgr.get_soul("dave")
        assert "Dave的灵魂" in soul
        assert "SOUL Default" not in soul

    def test_get_user_profile_fallback(self, mgr):
        profile = mgr.get_user_profile("unknown")
        assert "用户画像" in profile

    def test_get_bootstrap_per_user(self, mgr, tmp_dirs):
        mgr.ensure_user_dir("eve")
        bootstrap = mgr.get_bootstrap("eve")
        assert "首次引导" in bootstrap


class TestCustomPrompts:
    """用户自定义提示词片段。"""

    def test_add_and_get_custom_prompt(self, mgr, tmp_dirs):
        mgr.ensure_user_dir("frank")
        mgr.add_custom_prompt("frank", "coding_style", "## 编码风格\n使用 Python 3.12")
        prompts = mgr.get_custom_prompts("frank")
        assert len(prompts) == 1
        assert prompts[0]["name"] == "coding_style"
        assert "Python 3.12" in prompts[0]["content"]

    def test_multiple_custom_prompts(self, mgr, tmp_dirs):
        mgr.ensure_user_dir("grace")
        mgr.add_custom_prompt("grace", "style", "简洁直接")
        mgr.add_custom_prompt("grace", "format", "使用表格")
        prompts = mgr.get_custom_prompts("grace")
        assert len(prompts) == 2

    def test_remove_custom_prompt(self, mgr, tmp_dirs):
        mgr.ensure_user_dir("heidi")
        mgr.add_custom_prompt("heidi", "temp", "临时")
        assert mgr.remove_custom_prompt("heidi", "temp")
        prompts = mgr.get_custom_prompts("heidi")
        assert len(prompts) == 0

    def test_no_custom_prompts_for_new_user(self, mgr, tmp_dirs):
        mgr.ensure_user_dir("ivan")
        prompts = mgr.get_custom_prompts("ivan")
        assert len(prompts) == 0


class TestUserPersonas:
    """用户自定义人格。"""

    def test_add_and_get_user_persona(self, mgr, tmp_dirs):
        mgr.ensure_user_dir("judy")
        mgr.add_user_persona("judy", "coder", "# 程序员\n专注代码")
        personas = mgr.get_user_personas("judy")
        assert len(personas) == 1
        assert personas[0]["name"] == "coder"
        assert "程序员" in personas[0]["description"]


class TestBuildIdentityPrompt:
    """完整的身份提示词构建。"""

    def test_build_contains_all_sections(self, mgr, tmp_dirs):
        mgr.ensure_user_dir("kate")
        prompt = mgr.build_identity_prompt("kate")
        assert "Immutable Core Rules" in prompt  # CORE.md
        assert "SOUL Default" in prompt           # SOUL.md (from template copy)
        assert "用户画像" in prompt               # USER.md (from template copy)

    def test_build_includes_custom_prompts(self, mgr, tmp_dirs):
        mgr.ensure_user_dir("leo")
        mgr.add_custom_prompt("leo", "rules", "## 规则\n总是用中文回答")
        prompt = mgr.build_identity_prompt("leo")
        assert "总是用中文回答" in prompt

    def test_build_with_custom_soul(self, mgr, tmp_dirs):
        mgr.ensure_user_dir("mike")
        mgr.update_soul("mike", "# Mike的灵魂\n我叫小明")
        prompt = mgr.build_identity_prompt("mike")
        assert "小明" in prompt
        assert "默认灵魂" not in prompt  # 被用户自定义覆盖

    def test_build_with_profile_context(self, mgr, tmp_dirs):
        """profile_context 参数注入程序化用户偏好。"""
        mgr.ensure_user_dir("nina")
        profile_ctx = "[用户画像]\n偏好: language=zh-CN; style=concise"
        prompt = mgr.build_identity_prompt("nina", profile_context=profile_ctx)
        assert "language=zh-CN" in prompt
        assert "style=concise" in prompt

    def test_build_without_profile_context(self, mgr, tmp_dirs):
        """空 profile_context 不影响输出。"""
        mgr.ensure_user_dir("oscar")
        prompt_with = mgr.build_identity_prompt("oscar", profile_context="")
        prompt_without = mgr.build_identity_prompt("oscar")
        assert prompt_with == prompt_without


class TestMultiUserIsolation:
    """多用户隔离。"""

    def test_different_users_different_souls(self, mgr, tmp_dirs):
        mgr.ensure_user_dir("user_a")
        mgr.ensure_user_dir("user_b")
        mgr.update_soul("user_a", "# A的灵魂\n我是A")
        mgr.update_soul("user_b", "# B的灵魂\n我是B")
        assert "我是A" in mgr.get_soul("user_a")
        assert "我是B" in mgr.get_soul("user_b")
        assert "我是B" not in mgr.get_soul("user_a")

    def test_different_users_different_custom_prompts(self, mgr, tmp_dirs):
        mgr.ensure_user_dir("x")
        mgr.ensure_user_dir("y")
        mgr.add_custom_prompt("x", "style", "正式")
        mgr.add_custom_prompt("y", "style", "随意")
        x_prompts = mgr.get_custom_prompts("x")
        y_prompts = mgr.get_custom_prompts("y")
        assert x_prompts[0]["content"] == "正式"
        assert y_prompts[0]["content"] == "随意"

    def test_shared_core(self, mgr, tmp_dirs):
        """CORE.md 对所有用户相同。"""
        prompt_a = mgr.build_identity_prompt("user_a")
        prompt_b = mgr.build_identity_prompt("user_b")
        assert "Immutable Core Rules" in prompt_a
        assert "Immutable Core Rules" in prompt_b


class TestUserInfo:
    """用户信息 API。"""

    def test_user_info_new_user(self, mgr):
        info = mgr.get_user_info("new_user")
        assert info["user_id"] == "new_user"
        assert info["has_custom_identity"] is False

    def test_user_info_existing_user(self, mgr, tmp_dirs):
        mgr.ensure_user_dir("existing")
        mgr.add_custom_prompt("existing", "test_prompt", "test")
        info = mgr.get_user_info("existing")
        assert info["has_custom_identity"] is True
        assert "test_prompt" in info["custom_prompts"]


class TestProfileIntegration:
    """UserProfileAdapter → build_identity_prompt 集成测试。"""

    def test_profile_adapter_to_identity_prompt_chain(self, mgr, tmp_dirs):
        """验证完整链路：UserProfileAdapter 生成的上下文能正确注入身份提示词。"""
        from adapters.memory.user_profile import UserProfileAdapter
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_dir = Path(tmpdir)
            # Monkey-patch profiles dir
            import adapters.memory.user_profile as up_mod
            original_dir = up_mod.PROFILES_DIR
            up_mod.PROFILES_DIR = profiles_dir

            try:
                adapter = UserProfileAdapter()
                adapter.update_preference("test_user", "language", "zh-CN")
                adapter.update_preference("test_user", "style", "concise")
                adapter.add_fact("test_user", "Python developer")

                ctx = adapter.get_context_prompt("test_user")
                assert "[用户画像]" in ctx
                assert "language=zh-CN" in ctx
                assert "Python developer" in ctx

                mgr.ensure_user_dir("test_user")
                prompt = mgr.build_identity_prompt("test_user", profile_context=ctx)
                assert "language=zh-CN" in prompt
                assert "Python developer" in prompt
                assert "Immutable Core Rules" in prompt  # CORE still there
            finally:
                up_mod.PROFILES_DIR = original_dir

    def test_empty_profile_no_injection(self, mgr, tmp_dirs):
        """空画像不应产生多余内容。"""
        from adapters.memory.user_profile import UserProfileAdapter
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            import adapters.memory.user_profile as up_mod
            original_dir = up_mod.PROFILES_DIR
            up_mod.PROFILES_DIR = Path(tmpdir)

            try:
                adapter = UserProfileAdapter()
                ctx = adapter.get_context_prompt("nonexistent_user")
                assert ctx == ""

                mgr.ensure_user_dir("nonexistent_user")
                prompt_with = mgr.build_identity_prompt("nonexistent_user", profile_context=ctx)
                prompt_without = mgr.build_identity_prompt("nonexistent_user")
                assert prompt_with == prompt_without
            finally:
                up_mod.PROFILES_DIR = original_dir


class TestPathSafety:
    """路径安全。"""

    def test_unsafe_user_id_sanitized(self, mgr, tmp_dirs):
        """用户 ID 中的路径遍历字符被清理。"""
        user_dir = mgr.ensure_user_dir("../../../etc/passwd")
        # 不应超出 users 目录
        _, users_dir = tmp_dirs
        assert str(user_dir).startswith(str(users_dir))

    def test_unsafe_prompt_name_sanitized(self, mgr, tmp_dirs):
        mgr.ensure_user_dir("safe")
        result = mgr.add_custom_prompt("safe", "../../hack", "evil content")
        assert result is True
        # 文件应在 custom_prompts 目录内
        prompts = mgr.get_custom_prompts("safe")
        assert len(prompts) == 1
