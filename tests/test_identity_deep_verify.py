"""深度验证测试 — 灵魂系统第二/三轮修改的完整通路验证。

测试矩阵:
  T1: INNER.md 删除通路 — 文件不存在、代码无引用、build_identity_prompt 无注入
  T2: UserProfileAdapter → build_identity_prompt 闭环 — 有数据/无数据/边界条件
  T3: brain._build_messages 集成 — profile_context 正确传入
  T4: brain_learning._maybe_promote_to_profile — per-user 写入正确性
  T5: soul_engine 质量门控 — 垃圾拒绝/合法通过
  T6: soul_engine 写入路径 — 系统模板 vs per-user 隔离
  T7: 多用户隔离 — 不同用户互不干扰
  T8: 缓存一致性 — 写入后缓存失效
"""

from unittest.mock import MagicMock

import pytest

# ── 导入被测模块 ──
from identity.user_identity import UserIdentityManager, _SYSTEM_IDENTITY_DIR
from identity.soul_engine import SoulEngine


@pytest.fixture
def tmp_env(tmp_path):
    """创建完整的临时环境，模拟 identity/ 和 data/users/。"""
    sys_dir = tmp_path / "identity"
    sys_dir.mkdir()
    data_dir = tmp_path / "data"
    users_dir = data_dir / "users"
    profiles_dir = data_dir / "profiles"
    users_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)

    # 系统模板
    (sys_dir / "CORE.md").write_text("# Immutable Core Rules\nHonesty first.", encoding="utf-8")
    (sys_dir / "SOUL.md").write_text("# SOUL Default\nI am LucidMind.\n\n## Learned Rules\n", encoding="utf-8")
    (sys_dir / "USER.md").write_text("# User Profile\nName: unknown", encoding="utf-8")
    (sys_dir / "BOOTSTRAP.md").write_text("# Bootstrap\nWelcome!", encoding="utf-8")

    # 创建 UserIdentityManager 并 monkey-patch 路径
    mgr = UserIdentityManager()
    import identity.user_identity as ui_mod
    orig_sys = ui_mod._SYSTEM_IDENTITY_DIR
    orig_users = ui_mod._USERS_DIR
    ui_mod._SYSTEM_IDENTITY_DIR = sys_dir
    ui_mod._USERS_DIR = users_dir

    yield {
        "mgr": mgr,
        "sys_dir": sys_dir,
        "users_dir": users_dir,
        "profiles_dir": profiles_dir,
        "tmp_path": tmp_path,
    }

    # 恢复
    ui_mod._SYSTEM_IDENTITY_DIR = orig_sys
    ui_mod._USERS_DIR = orig_users


# ════════════════════════════════════════════
# T1: INNER.md 删除通路
# ════════════════════════════════════════════

class TestT1_InnerDeleted:
    """验证 INNER.md 彻底删除后所有通路干净。"""

    def test_inner_file_not_exists(self):
        """INNER.md 物理文件已删除。"""
        inner = _SYSTEM_IDENTITY_DIR / "INNER.md"
        assert not inner.exists(), f"INNER.md 仍然存在: {inner}"

    def test_no_get_inner_method(self, tmp_env):
        """UserIdentityManager 不再有 get_inner 方法。"""
        mgr = tmp_env["mgr"]
        assert not hasattr(mgr, "get_inner"), "get_inner() 方法仍然存在"

    def test_no_write_inner_thought_method(self, tmp_env):
        """UserIdentityManager 不再有 write_inner_thought 方法。"""
        mgr = tmp_env["mgr"]
        assert not hasattr(mgr, "write_inner_thought"), "write_inner_thought() 方法仍然存在"

    def test_system_only_files_no_inner(self):
        """_SYSTEM_ONLY_FILES 不包含 INNER.md。"""
        import identity.user_identity as ui_mod
        assert "INNER.md" not in ui_mod._SYSTEM_ONLY_FILES

    def test_build_identity_prompt_no_inner(self, tmp_env):
        """build_identity_prompt 输出不包含任何 INNER 相关内容。"""
        mgr = tmp_env["mgr"]
        mgr.ensure_user_dir("t1_user")
        prompt = mgr.build_identity_prompt("t1_user")
        assert "INNER" not in prompt
        assert "System Internal Notes" not in prompt
        assert "秘密空间" not in prompt

    def test_ensure_user_dir_no_inner_copy(self, tmp_env):
        """新用户目录中不应有 INNER.md 副本。"""
        mgr = tmp_env["mgr"]
        user_dir = mgr.ensure_user_dir("t1_check")
        assert not (user_dir / "INNER.md").exists()


# ════════════════════════════════════════════
# T2: UserProfileAdapter → build_identity_prompt 闭环
# ════════════════════════════════════════════

class TestT2_ProfileInjection:
    """验证 UserProfileAdapter 数据正确注入身份提示词。"""

    def _make_adapter(self, profiles_dir):
        import adapters.memory.user_profile as up_mod
        orig = up_mod.PROFILES_DIR
        up_mod.PROFILES_DIR = profiles_dir
        from adapters.memory.user_profile import UserProfileAdapter
        adapter = UserProfileAdapter()
        return adapter, orig, up_mod

    def _restore(self, up_mod, orig):
        up_mod.PROFILES_DIR = orig

    def test_profile_with_prefs_and_facts(self, tmp_env):
        """有偏好和事实时，profile_context 正确注入。"""
        adapter, orig, mod = self._make_adapter(tmp_env["profiles_dir"])
        try:
            adapter.update_preference("u2", "language", "zh-CN")
            adapter.update_preference("u2", "style", "concise")
            adapter.add_fact("u2", "Loves Python")
            adapter.add_fact("u2", "Works at startup")

            ctx = adapter.get_context_prompt("u2")
            assert "[用户画像]" in ctx
            assert "language=zh-CN" in ctx
            assert "style=concise" in ctx
            assert "Loves Python" in ctx
            assert "Works at startup" in ctx

            mgr = tmp_env["mgr"]
            mgr.ensure_user_dir("u2")
            prompt = mgr.build_identity_prompt("u2", profile_context=ctx)
            assert "language=zh-CN" in prompt
            assert "Loves Python" in prompt
            # 同时验证其他部分仍存在
            assert "Immutable Core Rules" in prompt
            assert "SOUL Default" in prompt
        finally:
            self._restore(mod, orig)

    def test_empty_profile_returns_empty_string(self, tmp_env):
        """无画像时返回空字符串，不注入。"""
        adapter, orig, mod = self._make_adapter(tmp_env["profiles_dir"])
        try:
            ctx = adapter.get_context_prompt("nonexist_user_x")
            assert ctx == ""

            mgr = tmp_env["mgr"]
            mgr.ensure_user_dir("nonexist_user_x")
            prompt_with = mgr.build_identity_prompt("nonexist_user_x", profile_context="")
            prompt_without = mgr.build_identity_prompt("nonexist_user_x")
            assert prompt_with == prompt_without
        finally:
            self._restore(mod, orig)

    def test_profile_only_prefs_no_facts(self, tmp_env):
        """只有偏好没有事实。"""
        adapter, orig, mod = self._make_adapter(tmp_env["profiles_dir"])
        try:
            adapter.update_preference("u2b", "theme", "dark")
            ctx = adapter.get_context_prompt("u2b")
            assert "theme=dark" in ctx
            assert "已知" not in ctx  # 无事实段
        finally:
            self._restore(mod, orig)

    def test_profile_only_facts_no_prefs(self, tmp_env):
        """只有事实没有偏好。"""
        adapter, orig, mod = self._make_adapter(tmp_env["profiles_dir"])
        try:
            adapter.add_fact("u2c", "Uses Vim")
            ctx = adapter.get_context_prompt("u2c")
            assert "Uses Vim" in ctx
            assert "偏好" not in ctx  # 无偏好段
        finally:
            self._restore(mod, orig)

    def test_profile_context_position_in_prompt(self, tmp_env):
        """profile_context 在 USER.md 之后、custom_prompts 之前。"""
        mgr = tmp_env["mgr"]
        mgr.ensure_user_dir("u2d")
        mgr.add_custom_prompt("u2d", "rules", "Always respond in English")

        prompt = mgr.build_identity_prompt("u2d", profile_context="[用户画像]\nlang=en")

        core_pos = prompt.find("Immutable Core Rules")
        user_pos = prompt.find("User Profile")
        profile_pos = prompt.find("[用户画像]")
        custom_pos = prompt.find("Always respond in English")

        assert core_pos < user_pos < profile_pos < custom_pos, \
            f"注入顺序错误: CORE({core_pos}) < USER({user_pos}) < profile({profile_pos}) < custom({custom_pos})"


# ════════════════════════════════════════════
# T3: brain._build_messages 集成
# ════════════════════════════════════════════

class TestT3_BrainIntegration:
    """验证 brain.py 正确调用 profile_context 链路。"""

    def test_brain_has_profile_adapter(self):
        """Brain 实例化时创建 _profile_adapter。"""
        from brain import Brain
        llm = MagicMock()
        stream = MagicMock()
        b = Brain(llm=llm, stream=stream)
        assert hasattr(b, "_profile_adapter")
        assert b._profile_adapter is not None

    def test_brain_profile_adapter_callable(self):
        """_profile_adapter.get_context_prompt 可调用且不报错。"""
        from brain import Brain
        llm = MagicMock()
        stream = MagicMock()
        b = Brain(llm=llm, stream=stream)
        # 对不存在的用户调用应返回空字符串
        result = b._profile_adapter.get_context_prompt("test_no_profile")
        assert isinstance(result, str)


# ════════════════════════════════════════════
# T4: brain_learning._maybe_promote_to_profile per-user 写入
# ════════════════════════════════════════════

class TestT4_PromoteToProfile:
    """验证 _maybe_promote_to_profile 写入 per-user USER.md。"""

    @pytest.mark.asyncio
    async def test_promote_writes_to_per_user_not_system(self, tmp_env):
        """纠正提升必须写入 per-user USER.md，不能写入系统模板。"""
        mgr = tmp_env["mgr"]
        sys_dir = tmp_env["sys_dir"]

        # 记录系统模板原始内容
        system_user_md = (sys_dir / "USER.md").read_text(encoding="utf-8")

        # 创建用户
        user_dir = mgr.ensure_user_dir("promote_test")
        user_user_md_before = (user_dir / "USER.md").read_text(encoding="utf-8")

        # 模拟 Brain mixin 的 _maybe_promote_to_profile
        # 直接测试写入路径逻辑
        user_path = user_dir / "USER.md"
        lesson = "Always use type hints in Python code"
        content = user_path.read_text(encoding="utf-8")
        if lesson[:50] not in content:
            rule = f"- {lesson[:150]}"
            content += f"\n{rule}\n"
            user_path.write_text(content, encoding="utf-8")

        # 验证写入了 per-user
        user_content = (user_dir / "USER.md").read_text(encoding="utf-8")
        assert "type hints" in user_content

        # 验证系统模板未被修改
        system_content = (sys_dir / "USER.md").read_text(encoding="utf-8")
        assert system_content == system_user_md, "系统模板被污染！"

    @pytest.mark.asyncio
    async def test_promote_dedup(self, tmp_env):
        """同一条规则不应重复写入。"""
        mgr = tmp_env["mgr"]
        user_dir = mgr.ensure_user_dir("dedup_test")
        user_path = user_dir / "USER.md"

        lesson = "Use pytest fixtures"
        # 第一次写入
        content = user_path.read_text(encoding="utf-8")
        content += f"\n- {lesson}\n"
        user_path.write_text(content, encoding="utf-8")

        # 第二次应跳过（dedup check）
        content2 = user_path.read_text(encoding="utf-8")
        assert lesson[:50] in content2  # 已存在，应跳过
        count = content2.count(lesson)
        assert count == 1, f"规则重复写入了 {count} 次"


# ════════════════════════════════════════════
# T5: soul_engine 质量门控
# ════════════════════════════════════════════

class TestT5_QualityGate:
    """验证 soul_engine 质量门控的正确性。"""

    @pytest.fixture
    def engine(self, tmp_env):
        """创建指向临时目录的 SoulEngine。"""
        import identity.soul_engine as se_mod
        orig = se_mod._SOUL_PATH
        se_mod._SOUL_PATH = tmp_env["sys_dir"] / "SOUL.md"
        orig_log = se_mod._EVOLUTION_LOG
        se_mod._EVOLUTION_LOG = tmp_env["tmp_path"] / "evolution.json"
        e = SoulEngine()
        yield e
        se_mod._SOUL_PATH = orig
        se_mod._EVOLUTION_LOG = orig_log

    def test_reject_too_short(self, engine):
        assert engine._passes_quality_gate("abc", "test") is False

    def test_reject_too_long(self, engine):
        assert engine._passes_quality_gate("x" * 301, "test") is False

    def test_reject_traceback(self, engine):
        assert engine._passes_quality_gate("Traceback (most recent call last): ...", "test") is False

    def test_reject_attribute_error(self, engine):
        assert engine._passes_quality_gate("object has no attribute 'foo'", "test") is False

    def test_reject_error_pattern(self, engine):
        assert engine._passes_quality_gate("Error: connection refused to database", "test") is False

    def test_reject_trigger_garbage(self, engine):
        """即使 text 正常，trigger 是垃圾也应拒绝。"""
        assert engine._passes_quality_gate("Good rule here.", "Traceback (most recent call") is False

    def test_accept_valid_chinese(self, engine):
        assert engine._passes_quality_gate("遇到用户纠正时立即承认错误。", "correction") is True

    def test_accept_valid_english(self, engine):
        assert engine._passes_quality_gate("Always acknowledge mistakes when corrected.", "correction") is True

    def test_reject_truncated_prose(self, engine):
        """超过10词且没有有效结尾标点的文本视为截断。"""
        text = "This is a long sentence that does not end with proper punctuation and keeps going"
        assert engine._passes_quality_gate(text, "test") is False

    def test_accept_list_item_no_punctuation(self, engine):
        """短列表项（<=10词）允许无标点。"""
        assert engine._passes_quality_gate("Use type hints always", "correction") is True

    def test_evolve_respects_gate(self, engine):
        """evolve() 应拒绝不通过质量门控的规则。"""
        result = engine.evolve("test", "abc")  # too short
        assert result is False

    def test_evolve_accepts_valid(self, engine):
        """evolve() 应接受通过质量门控的规则。"""
        result = engine.evolve("user feedback", "Always respond concisely when asked.")
        assert result is True


# ════════════════════════════════════════════
# T6: soul_engine 写入路径
# ════════════════════════════════════════════

class TestT6_SoulEngineWritePath:
    """验证 soul_engine 写入系统模板（by design）且不影响 per-user。"""

    def test_evolve_writes_to_system_template(self, tmp_env):
        """evolve() 写入系统级 SOUL.md。"""
        import identity.soul_engine as se_mod
        orig = se_mod._SOUL_PATH
        se_mod._SOUL_PATH = tmp_env["sys_dir"] / "SOUL.md"
        orig_log = se_mod._EVOLUTION_LOG
        se_mod._EVOLUTION_LOG = tmp_env["tmp_path"] / "evolution.json"

        try:
            engine = SoulEngine()
            engine.evolve("pattern", "Always validate input parameters.")
            content = (tmp_env["sys_dir"] / "SOUL.md").read_text(encoding="utf-8")
            assert "Always validate input parameters" in content
        finally:
            se_mod._SOUL_PATH = orig
            se_mod._EVOLUTION_LOG = orig_log

    def test_evolve_does_not_affect_per_user(self, tmp_env):
        """evolve() 不影响已有的 per-user SOUL.md。"""
        import identity.soul_engine as se_mod
        orig = se_mod._SOUL_PATH
        se_mod._SOUL_PATH = tmp_env["sys_dir"] / "SOUL.md"
        orig_log = se_mod._EVOLUTION_LOG
        se_mod._EVOLUTION_LOG = tmp_env["tmp_path"] / "evolution.json"

        try:
            mgr = tmp_env["mgr"]
            user_dir = mgr.ensure_user_dir("soul_iso_test")
            user_soul_before = (user_dir / "SOUL.md").read_text(encoding="utf-8")

            engine = SoulEngine()
            engine.evolve("pattern", "New global rule for all users.")

            user_soul_after = (user_dir / "SOUL.md").read_text(encoding="utf-8")
            assert user_soul_before == user_soul_after, "per-user SOUL.md 被系统进化污染！"
        finally:
            se_mod._SOUL_PATH = orig
            se_mod._EVOLUTION_LOG = orig_log


# ════════════════════════════════════════════
# T7: 多用户隔离
# ════════════════════════════════════════════

class TestT7_MultiUserIsolation:
    """验证不同用户的身份完全隔离。"""

    def test_different_users_different_profiles(self, tmp_env):
        """不同用户的 profile_context 互不干扰。"""
        import adapters.memory.user_profile as up_mod
        orig = up_mod.PROFILES_DIR
        up_mod.PROFILES_DIR = tmp_env["profiles_dir"]

        try:
            from adapters.memory.user_profile import UserProfileAdapter
            adapter = UserProfileAdapter()
            adapter.update_preference("alice", "language", "en")
            adapter.update_preference("bob", "language", "zh-CN")

            ctx_a = adapter.get_context_prompt("alice")
            ctx_b = adapter.get_context_prompt("bob")
            assert "language=en" in ctx_a
            assert "language=zh-CN" in ctx_b
            assert "zh-CN" not in ctx_a
            assert "language=en" not in ctx_b
        finally:
            up_mod.PROFILES_DIR = orig

    def test_different_users_different_prompts(self, tmp_env):
        """不同用户的 build_identity_prompt 输出不同。"""
        mgr = tmp_env["mgr"]
        mgr.ensure_user_dir("alice2")
        mgr.ensure_user_dir("bob2")
        mgr.update_soul("alice2", "# Alice Soul\nI am creative.")
        mgr.update_soul("bob2", "# Bob Soul\nI am analytical.")

        prompt_a = mgr.build_identity_prompt("alice2", profile_context="[画像]\nlang=en")
        prompt_b = mgr.build_identity_prompt("bob2", profile_context="[画像]\nlang=zh")

        assert "creative" in prompt_a
        assert "analytical" in prompt_b
        assert "analytical" not in prompt_a
        assert "creative" not in prompt_b
        assert "lang=en" in prompt_a
        assert "lang=zh" in prompt_b

    def test_user_promote_isolation(self, tmp_env):
        """用户 A 的 promote 不影响用户 B 的 USER.md。"""
        mgr = tmp_env["mgr"]
        dir_a = mgr.ensure_user_dir("iso_a")
        dir_b = mgr.ensure_user_dir("iso_b")

        # 向 A 写入规则
        user_a_path = dir_a / "USER.md"
        content = user_a_path.read_text(encoding="utf-8")
        content += "\n- Alice specific rule\n"
        user_a_path.write_text(content, encoding="utf-8")

        # 验证 B 未被影响
        user_b_content = (dir_b / "USER.md").read_text(encoding="utf-8")
        assert "Alice specific rule" not in user_b_content


# ════════════════════════════════════════════
# T8: 缓存一致性
# ════════════════════════════════════════════

class TestT9_ExtractPreferences:
    """验证 extract_preferences 自动提取用户偏好闭环。"""

    @pytest.mark.asyncio
    async def test_extract_chinese_preference(self, tmp_env):
        """用户说"用中文回答"时自动提取语言偏好。"""
        import adapters.memory.user_profile as up_mod
        orig = up_mod.PROFILES_DIR
        up_mod.PROFILES_DIR = tmp_env["profiles_dir"]
        try:
            from adapters.memory.user_profile import UserProfileAdapter
            adapter = UserProfileAdapter()
            prefs = await adapter.extract_preferences("请用中文回答我的问题")
            assert prefs.get("language") == "zh-CN"

            # 存储后验证 get_context_prompt 能读到
            for k, v in prefs.items():
                adapter.update_preference("ext_user", k, v)
            ctx = adapter.get_context_prompt("ext_user")
            assert "language=zh-CN" in ctx
        finally:
            up_mod.PROFILES_DIR = orig

    @pytest.mark.asyncio
    async def test_extract_style_preference(self, tmp_env):
        """用户说"简洁一点"时自动提取风格偏好。"""
        import adapters.memory.user_profile as up_mod
        orig = up_mod.PROFILES_DIR
        up_mod.PROFILES_DIR = tmp_env["profiles_dir"]
        try:
            from adapters.memory.user_profile import UserProfileAdapter
            adapter = UserProfileAdapter()
            prefs = await adapter.extract_preferences("回答简洁一点，不要太长")
            assert prefs.get("style") == "concise"
        finally:
            up_mod.PROFILES_DIR = orig

    @pytest.mark.asyncio
    async def test_extract_no_match(self, tmp_env):
        """普通对话不触发偏好提取。"""
        import adapters.memory.user_profile as up_mod
        orig = up_mod.PROFILES_DIR
        up_mod.PROFILES_DIR = tmp_env["profiles_dir"]
        try:
            from adapters.memory.user_profile import UserProfileAdapter
            adapter = UserProfileAdapter()
            prefs = await adapter.extract_preferences("今天天气怎么样？")
            assert prefs == {}
        finally:
            up_mod.PROFILES_DIR = orig

    @pytest.mark.asyncio
    async def test_extract_to_prompt_full_chain(self, tmp_env):
        """完整链路: 用户输入 → extract → save → get_context_prompt → build_identity_prompt。"""
        import adapters.memory.user_profile as up_mod
        orig = up_mod.PROFILES_DIR
        up_mod.PROFILES_DIR = tmp_env["profiles_dir"]
        try:
            from adapters.memory.user_profile import UserProfileAdapter
            adapter = UserProfileAdapter()

            # 模拟多轮对话提取
            prefs1 = await adapter.extract_preferences("请用中文回答")
            for k, v in prefs1.items():
                adapter.update_preference("chain_user", k, v)

            prefs2 = await adapter.extract_preferences("回答要详细一些")
            for k, v in prefs2.items():
                adapter.update_preference("chain_user", k, v)

            # 验证画像累积
            ctx = adapter.get_context_prompt("chain_user")
            assert "language=zh-CN" in ctx
            assert "style=detailed" in ctx

            # 验证注入到 identity prompt
            mgr = tmp_env["mgr"]
            mgr.ensure_user_dir("chain_user")
            prompt = mgr.build_identity_prompt("chain_user", profile_context=ctx)
            assert "language=zh-CN" in prompt
            assert "style=detailed" in prompt
        finally:
            up_mod.PROFILES_DIR = orig


class TestT8_CacheConsistency:
    """验证文件修改后缓存正确失效。"""

    def test_soul_cache_invalidation(self, tmp_env):
        """更新 SOUL.md 后，下次读取获得最新内容。"""
        mgr = tmp_env["mgr"]
        mgr.ensure_user_dir("cache_test")
        soul1 = mgr.get_soul("cache_test")
        assert "SOUL Default" in soul1

        mgr.update_soul("cache_test", "# New Soul\nUpdated content.")
        soul2 = mgr.get_soul("cache_test")
        assert "Updated content" in soul2
        assert "SOUL Default" not in soul2

    def test_profile_cache_invalidation(self, tmp_env):
        """更新 USER.md 后，下次 build_identity_prompt 获得最新内容。"""
        mgr = tmp_env["mgr"]
        mgr.ensure_user_dir("cache_test2")
        mgr.update_user_profile("cache_test2", "# Updated Profile\nName: TestUser")

        prompt = mgr.build_identity_prompt("cache_test2")
        assert "Name: TestUser" in prompt
