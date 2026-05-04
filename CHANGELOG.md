# LucidMind 变更日志

> **规则：每次代码改动必须在此文件记录。不记录 = 违反规则。**

---

## v3.1.1 (2026-05-04) — 架构修复 + Discord + 文档

### P0: 安全与清理
- **移除硬编码 Antigravity API Key**: `api/startup.py` 改为读取 `ANTIGRAVITY_API_KEY` 环境变量
- **发布忽略规则加固**: `.gitignore` 增加 `.env.*`、数据库、日志、备份、IDE、node_modules 等忽略项
- **环境变量模板安全化**: `.env.example` 改为空值模板，补充全部配置项
- **版本号统一**: `pyproject.toml` / `api/main.py` / `cli.py` 统一为 3.1.1
- **清理废弃文件**: 移除 `frontend/未命名.html`、`docs/测试日志.md`、`tests/_deprecated`
- **README 重写**: 现代化用户向 README，含 Quick Start、Features、Architecture、Hermes 对比

### P1: 架构修复
- **六边形架构合规**: `brain.py` 移除直接 `UserProfileAdapter` 导入，改为构造器注入 + 惰性回退
- **brain_task_executor 解耦**: 移除 `BroadcastStreamAdapter` 直接导入，通过 `stream_factory` 注入
- **memory/store.py 拆分**: 880→451 行，排序管线拆至 `store_ranking.py`，反馈/合并拆至 `store_feedback.py`

### P2: 能力增强
- **Discord 通道**: 新增 `adapters/channel/discord_channel.py`，线程绑定会话隔离，消息分片，集成到启动链路
- **CLI 修正**: 版本号更新至 3.1.1，默认端口改为 8765
- **用户文档**: 新增 `docs/configuration.md`（全量配置指南）和 `docs/architecture.md`（架构说明）

### 安全提示
- 既往出现在代码中的 API Key 应视为已泄露，发布前必须在服务商后台轮换

---

## v3.1.0 (2026-03-01) — Phase A/B/C/D 工程深度提升

### Phase A: 安全修复
- **ToolSafetyGuard 闭环**: `CompositeToolAdapter.execute()` 执行前经过安全审批链
- **路径穿越防护**: `_validate_plugin_name()` 正则+resolve 双重校验
- **HTTP 错误码规范**: API 端点统一使用 400/404/500 标准错误码

### Phase B: 插件三层加载
- **`skills/loader.py`**: `LazyPluginAdapter` — 启动时只读 manifest (Layer 1)，首次调用时加载代码 (Layer 3)
- **`discover_skills(lazy=True)`**: 懒加载模式，启动时不加载任何插件 Python 代码
- **`CompositeToolAdapter._try_lazy_load()`**: 未知工具自动触发懒加载 fallback
- **SKILL.md**: 新增 clipboard、web_monitor 文档（共 6 个插件有 SKILL.md）

### Phase C: 安全体系化
- **`discovery_safety.py`**: 5 项安全检查（路径逃逸/符号链接/权限/所有权/文件大小）
- **`skill_scanner.py`**: 16 种危险模式扫描 + 扫描历史持久化
- **`mcp_transport.py`**: MCP Server 配置安全验证（命令白名单/shell元字符/受保护环境变量/URL协议）
- **`api/security.py`**: `POST /scan/{plugin}` + `GET /scan-history` API

### Phase D: Letta 增量模式
- **`memory/letta_blocks.py`**: `MemoryBlock` + `BlockManager` — 命名记忆块 + 字符限制 + 受保护块 + Block 分裂
- **`adapters/tools/memory_tool.py`**: `MemoryToolAdapter` — Agent 自主记忆管理工具 (memory_read/write/append)
- **Block 分裂**: 大块自动按段落拆为子块 (project → project-overview/details/notes)
- **`format_for_prompt()`**: XML 标签格式注入 system prompt

### 测试结果
- 全量: **535/535 passed** (较 v2.02 增加 48 个新测试)
- test_phase0_safety.py: 19/19
- test_three_layer_loader.py: 17/17
- test_phase2_security.py: 25/25
- test_letta_blocks.py: 31/31
- 退化: 0

---

## v2.02 (2026-03-01) — 记忆系统 P0+P1 最优方案实施

### 新增
- **噪声过滤模块** (`memory/noise_filter.py`): 3类过滤(agent拒绝/寒暄/错误噪声) + CJK感知长度检查 + 自适应检索跳过
- **核心记忆Block直注** (`memory/block_inject.py`): 高频记忆(helpful≥2/用户偏好)直注prompt顶部，5分钟缓存，零搜索延迟（对标Letta memory blocks）
- **工具级观察采集** (`memory/tool_observer.py`): 记录tool_name/input/output/success/duration，每会话限流50条，失败模式分析（对标claude-mem observation）
- **两阶段提取器** (`memory/two_stage_extractor.py`): Stage1 LLM提取事实/偏好/教训 → Stage2 对比已有记忆决策ADD/UPDATE/DELETE/SKIP（对标mem0 add()）
- **自动备份JSONL** (`memory/store.py`): `backup_jsonl()` 方法，7天轮转
- **sqlite-vec向量搜索**: `requirements.txt` 添加 sqlite-vec>=0.1.6，8阶段管线向量阶段激活
- **测试**: `tests/test_noise_filter.py` (25个) + `tests/test_p1_enhancements.py` (32个)

### 修复
- **harmful反馈通路**: `brain_learning.py` L92 — `update_effectiveness(lid, effective)` 替代原来只传True的bug，harmful_count不再永远为0

### 变更
- **search_hybrid()**: 新增 Stage 0 自适应跳过（问候/简单命令直接返回空）
- **store.add()**: 新增 `skip_noise_filter` 参数，merge_deltas内部跳过过滤
- **reflect_on_session()**: 新增 `store`/`use_two_stage` 参数，支持两阶段模式
- **MemoryStoreLearningAdapter**: 集成CoreMemoryBlock(get_lessons置顶) + ToolObserver
- **memory/__init__.py**: 导出 CoreMemoryBlock, ToolObserver, TwoStageExtractor

### 激活与集成
- **ACE 全面激活**: `cli.py` + `adapters/tools/introspect.py` 切换到 MemoryStoreLearningAdapter（api/startup.py 此前已切换）
- **工具观察装饰器**: `adapters/tools/observed_tool.py` (新建78行) — ObservedToolAdapter 包装所有工具调用
- **api/startup.py**: 工具链增加 ObservedToolAdapter 装饰层，自动采集每次 tool call
- **brain_daemon.py**: _run_engines_inner() 第5步增加自动备份 + 向量回填 cron
- **embedding 管线打通**: `store.py` 新增 `embed_fn` 回调注入 + `add()` 自动生成向量 + `backfill_embeddings()` 渐进回填
- **adapter 注入 Ollama embed**: `memory_store_adapter.py` 初始化时将 `VectorStore.embed` 注入 MemoryStore
- **88条记忆全部向量化**: `memory_vectors` 表从 0 行回填至 88 行，search_hybrid 向量路径真正生效

### 测试结果
- 全量: **487/487 passed** (较上版本 455 增加 32 个新测试)
- 新增: test_noise_filter.py 25/25 + test_p1_enhancements.py 32/32
- 退化: 0

---

## v1.7 (2026-02-26) — 模型切换 + 记忆优化 + 自动构建 + pip 打包

### 修复
- **模型切换完整修复**：
  - 新增 `/api/switch-provider` API（不验证连接，快速切换）
  - `FallbackLLMAdapter.set_primary()` 切换主模型优先级
  - 持久化到 `data/active_provider.json`，启动时 `_restore_active_provider()` 恢复
  - 前端顶部下拉框改用 provider 名称绑定，切换后聊天区显示确认消息
- **向量检索融合失效**：`retrieval.py` 用 `id(obj)` 做 key 导致 BM25/向量结果无法匹配，改为 `_stable_key()`
- **MCP HTTP 传输变量名 bug**：`mcp_client.py` L264 `cfg` → `srv`
- **A/B 质量追踪持久化**：`brain.py` 新增 `_load_ab_stats()` / `_save_ab_stats()`
- **测试文件端口修正**：`test_e2e_api.py` 默认端口 8765 → 8000

### 新增
- **前端自动构建**：后端启动时检测 `frontend-v2/src` 是否有更新，自动执行 `vite build`
- **代码块语言标签**：Markdown 渲染增加语言标识 + 样式
- **pip 打包**：`pyproject.toml` 完善依赖声明、可选依赖分组、CLI 入口点

### 变更
- **STRATEGY.md 同步**：Phase 4 多角色配置标记✅，v1.6 大脑修复标记✅
- **requirements.txt 补全**：添加 python-pptx、openpyxl、Pillow、matplotlib、playwright 等

---

## v1.6 (2026-02-26) — 大脑深度修复

### 修复（🔴 严重）
- **合并两套冲突压缩逻辑**：`_smart_compact_history()` + `_compact_history_if_needed()` 统一为 token-aware 压缩
  - 新增 `_estimate_tokens()` 中英文 token 估算
  - 新增 `_estimate_history_tokens()` 历史总量估算
  - 新增 `_find_safe_cut_point()` 安全截断（保护 tool_calls/tool 配对）
  - `_compact_history_if_needed()` 简化为仅截断超长工具结果，不再做消息级压缩
- **System Prompt token 预算控制**：`_build_messages()` 可选部分按优先级排列，超 4K tokens 自动裁剪
- **修复 L309 暴力截断**：`_stream_final_reply()` 中 `>60条` 截断改为 `_find_safe_cut_point()` 安全截断

### 修复（🟡 中等）
- **减少额外 LLM 调用**：`_detect_learning_signal()` 严格预筛，<6字/纯肯定词直接跳过
- **移除自动 sudo**：`_adapt_params()` 不再自动添加 `sudo` 前缀，由 ToolSafetyGuard 控制
- **真流式输出**：`_stream_final_reply()` 优先用 LLM `stream=True` 真流式推送，过滤 `<think>` 标签，降级伪流式

### 改进（🟢）
- **经验检索改进**：`_get_relevant_lessons()` 从最近 20 条消息提取用户输入（跳过 tool 消息）
- **超时配置集中**：`BrainDaemon` 超时常量集中为类属性（OBSERVE/ENGINES/TEACHING/IDLE_MAX_WAIT）

---

## v1.5 (2026-02-26)

### 新增
- **P0a: MCP Server 扩展配置**：新增 github/sqlite/brave-search 三个 MCP Server 配置
- **P1a: 经验质量治理**：`memory_curator.py` 新增 `quality_cleanup()` + `_is_command_like()`
  - 自动识别并删除用户指令型经验（每天XX/给我XX/提醒XX等），50→41条
  - 新增 `_COMMAND_PATTERNS` 模式匹配，`should_add_lesson()` 增加入库拦截
- **P1b: 上下文窗口智能管理**：`brain_resilience.py` `_smart_compact_history()`
  - ≤10条不处理，11-30条简单截断，>30条 LLM 生成对话摘要压缩
  - 10秒超时，失败回退简单截断
- **P1c: 工具使用强化**：`brain.py` `_TOOL_USAGE_HINTS` few-shot 提示注入
  - 7条工具选择原则注入 system prompt，引导 LLM 正确选择工具
- **P2a: 多角色/分身系统**：`identity/personas.py` + `api/personas.py`
  - PersonaManager：创建/切换/删除人格，持久化配置
  - 预置人格：coder(编程专家)、finance(金融股票分析专家)、ecommerce(电商运营专家)
  - Brain 集成：当前人格 prompt 自动注入 system message
  - API：GET /api/persona/list, POST switch/create, DELETE /{name}
- **P2b: Skill Creator 智能化**：`skill_creator.py` `create_skill_with_llm()`
  - 用 LLM 生成完整工具实现代码（非 stub），安全扫描后热加载
  - 失败自动回退 stub 模式，`_auto_create_skill()` 已切换使用
- **P2c: OAuth MCP 支持**：`mcp_client.py` `_HttpTransport` 增强
  - 支持 `oauth_token` 和 `headers` 配置项
  - 自动添加 `Authorization: Bearer` 头
  - 401 状态码检测和日志

### 修改
- `brain.py`: 新增 `_persona_manager` 属性，`_build_messages()` 注入角色 prompt
- `brain_resilience.py`: `_auto_create_skill()` 升级为 LLM 版本
- `api/main.py`: 注册 personas_router，Brain 初始化时注入 PersonaManager
- STRATEGY.md: Phase 4 全部标记

---

## v1.4 (2026-02-26)

### 新增
- **E2: /workspace 外文件操作确认**：`tool_safety.py` `_check_outside_workspace()`
  - 文件操作涉及工作目录外路径时自动升级为 DANGEROUS，需用户确认
  - 允许 /tmp 和 /private/tmp（临时文件安全区）
  - 覆盖工具：write_file, delete_file, move_file, read_file, list_directory, run_script, run_shell, run_command
  - 检查参数：path, file_path, target, directory, cwd, command

### 修改
- STRATEGY.md: E2 标记 ✅ — Phase 3 全部任务 100% 完成

---

## v1.3 (2026-02-26)

### 验证确认（C5-C8 已在代码中实现）
- **C5**: `brain.py:246` — 只在 `_tool_calls_happened` 时标记经验有效（简单问候不算）
- **C6**: daemon 通过 `brain.process()` 调用，已包含 effectiveness 标记逻辑
- **C7**: `metacognition.py:107` — 深度元认知超时已改为 15s
- **C8**: `brain_engines.py:292` — `evolve()` 已接入学习引擎定时调用

### 工程质量（D1-D5）
- **D1**: `test_e2e_api.py` 25/25 测试全部通过
- **D3**: 9 个死代码文件移到 `adapters/tools/_deprecated/`
  - cascade_comm.py, clipboard.py, doubao_comm.py, gui_automation.py,
    notification.py, plugin_loader.py, stt.py, tts.py, vision.py
- **D4**: 15 个根目录散落文件移到 `_deprecated/`
  - 6 个分析 .md、probe_port.py、self_eval.py、integrated_lessons.json、
    user_preferences.json、user_profile.md、SOUL.md.deprecated、GPT.md、邯郸天气*.txt
- **D5**: `brain_daemon.py` 389行→162行（提取 `brain_daemon_observe.py` DaemonObserveMixin）

### 修改
- `brain_daemon.py`: 继承 `DaemonObserveMixin`，观察/健康/教学方法全部提取
- `STRATEGY.md`: C5-C8, D1-D5, E1 全部标记 ✅

---

## v1.2 (2026-02-26)

### 新增
- **Skill Scanner 安全扫描**（A4）：`skills/skill_scanner.py`
  - 13种危险模式检测：挖矿、数据外泄、反向Shell、eval/exec、subprocess、env读取等
  - 三级分类：CRITICAL（阻止安装）、WARNING（警告）、INFO（记录）
  - 集成到 `install_from_hub()`：下载后扫描，CRITICAL 直接删除拒绝安装
- **Skill Creator 自动创建**（A5）：`skills/skill_creator.py`
  - PluginHub 无匹配时自动生成 manifest.json + main.py
  - 生成后自动经过 skill_scanner 安全扫描
  - 集成到 `brain_resilience.py` `_auto_create_skill()` 方法
  - 完整闭环：_on_tool_not_found → 搜索PluginHub → 无结果 → 自动创建 → 扫描 → 热加载
- **MCP 连接健康监控+自动重连**（B5）：`mcp_client.py`
  - `health_check()` 方法：检查所有 MCP Server 连接状态
  - `_reconnect_server()` 方法：自动重连断开的服务器（最多3次）
  - `execute()` 中集成：服务器断开或无响应时自动重连再重试
  - `GET /api/mcp/health` API 端点
- **MCP 工具名冲突治理**（B6）：`mcp_client.py`
  - `discover()` 中检测工具名冲突，跳过重复工具并记录日志

### 修改
- `skills/__init__.py`：平台检查支持 `"all"` 字符串匹配所有平台
- `skills/__init__.py`：`install_from_hub()` 集成安全扫描（本地启用和远程下载两个路径）
- `brain_resilience.py`：`_on_tool_not_found` 搜索无结果时回退到 `_auto_create_skill`
- `api/mcp.py`：新增 `/api/mcp/health` 端点
- STRATEGY.md：A4/A5/B4/B5/B6 全部标记 ✅

### 测试验证
- skill_scanner：扫描全部16个 skills，正确识别 code_runner 的 CRITICAL（false positive in blacklist comment）
- skill_creator：创建 auto_test_tool（2个工具），安全扫描通过，热加载成功
- _on_tool_not_found 完整链路：magic_spell_cast → PluginHub无结果 → 自动创建 auto_magic_spell → 成功
- MCP auto-reconnect：Kill filesystem 进程 → execute 自动重连 → 执行成功
- MCP health_check：2个服务器均返回 healthy

---

## v0.3.3 (2026-02-25)

### 新增
- **PluginHub registry.json**（A1）：收录 16 个 skills，支持远程+本地回退
- **`_on_tool_not_found` 自动搜索安装**（A3）：`brain_resilience.py` 新增方法
  - 工具未注册 → 搜索 PluginHub → 精确匹配 tool 名 → 自动安装 → 热加载 → 立即重试
  - 集成到 `_tool_call_with_retry` 中，无需额外代码路径
- **MCP filesystem Server 接入**（B1+B2）：14 个文件操作工具，list/write/read 端到端验证通过
- **MCP memory Server 接入**（B1+B3）：9 个知识图谱工具，create_entities/search_nodes 端到端验证通过
- 总计：2 个 MCP Server，23 个外部工具注入 Brain

### 修改
- `skills/__init__.py`：`refresh_hub_registry()` 支持本地 registry.json 回退
- `skills/__init__.py`：`install_from_hub()` 本地已存在时直接启用+热加载，不重复下载
- `api/plugins.py`：移除 `install_from_hub` 中冗余的 `hot_reload()` 调用
- `data/mcp_servers.json`：配置 filesystem + memory 两个 MCP Server
- STRATEGY.md：A1/A2/A3/B1/B2/B3 标记 ✅

---

## v0.3.2 (2026-02-25)

### 变更
- STRATEGY.md 3B MCP 工作流深度扩展：基于 OpenClaw mcporter skill 代码深度研究
  - 新增 B5（连接健康监控）、B6（工具名冲突治理）两个任务项
  - 新增 mcporter 完整架构分析（list/call/auth/config/daemon/codegen）
  - 新增 4 个关键设计模式分析（CLI桥接器、统一调用面、工具注入、确定性分发）
  - 新增 LucidMind vs mcporter 10 维度对比表
  - 明确 LucidMind 的 3 个结构性优势（直接集成、Python原生、无shell中转）
  - 明确 5 个缺失项（连接保活、工具名冲突、OAuth认证、ad-hoc Server、端到端验证）

---

## v0.3.1 (2026-02-25)

### 变更
- STRATEGY.md Phase 3 全面重构：基于 OpenClaw 代码深度对标分析
  - 3A: Skill 生态（PluginHub仓库 + 前端安装 + 大脑自动搜索安装 + Skill Creator + 安装时安全扫描）
  - 3A 补齐：Skill Creator (A5) 从 Phase 4 提升到 Phase 3 P0，形成完整工具发现闭环
  - 3B: MCP 工作流（实际接入 MCP Server + 两个端到端工作流验证）
  - 3C: 记忆系统加固（effectiveness修正 + daemon有效性闭环）
  - 3D: 工程质量（回归测试 + 死代码清理）
  - 3E: 安全加固（安装时静态代码扫描，对标 OpenClaw skill-scanner.ts）
  - 明确 P0/P1/P2 执行顺序
  - Phase 4 加入 Skill Creator 和多角色配置

---

## v0.3.0-feishu-voice (2026-02-25)

### 新增
- 飞书语音消息支持：下载音频 → Whisper STT → Brain处理 → 文字回复
- 飞书 SDK 长连接模式（无需公网域名/ngrok）
- Whisper 模型缓存（避免每次语音消息重新加载）
- `.zshrc` 添加 `proxy_on` / `proxy_off` 快捷命令

### 修复
- 修复全通道 `Brain._stream` → `Brain.stream` 属性名错误（飞书/微信/企微/Telegram/Teacher API）
- 修复飞书回复消息静默失败（添加HTTP响应状态日志）
- 修复飞书 WebSocket 连接被 Little Snitch Network Extension 内核级拦截（关闭 Network Extension）
- 注释 `.zshrc` 中硬编码的 Clash 代理变量（Clash 未运行时导致所有外网超时）

### 变更
- 飞书适配器清除代理环境变量 + 禁用 IPv6（避免 SDK 连接失败）

---

## v0.2.0 (2026-02-25)

### Phase 1 + Phase 2 完成
- 代码大清理（33个废弃.py + 28个脚本 → archive/）
- 15个内置插件（35个工具）
- MCP 协议完整兼容（stdio + http）
- PluginHub 自动搜索安装
- 插件热加载
- 前端仪表盘 + 插件/MCP/通道 UI
- Telegram / 飞书 / 企业微信 / 微信 四通道
- 工具安全审批流
- E2E 自动化测试（25个用例）
- 经验管理器 memory_curator.py（选择性添加 + 组合删除）
- 经验分层（strategy/fact/temp）
- 向量语义检索（Ollama nomic-embed-text）

---

## 日志格式

```
## vX.Y.Z (YYYY-MM-DD)

### 新增
- 新功能描述

### 修复
- Bug修复描述

### 变更
- 行为变更描述

### 删除
- 移除的功能/文件
```
