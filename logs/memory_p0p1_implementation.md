# 记忆系统 P0+P1 最优方案实施日志

> 日期: 2026-03-01
> 版本: v2.02
> 测试结果: **487/487 passed, 0 退化**

---

## 一、P0 完成项（零 LLM 成本，纯工程）

### P0#1: 噪声过滤模块 ✅
- **文件**: `memory/noise_filter.py` (148行, 新建)
- **集成**: `memory/store.py` add() 方法 + search_hybrid() Stage 0
- **功能**: 3类正则过滤(agent拒绝/寒暄/错误噪声) + CJK感知长度检查
- **测试**: `tests/test_noise_filter.py` 25/25 passed

### P0#2: sqlite-vec 安装 ✅
- **依赖**: sqlite-vec 0.1.6 已安装
- **配置**: `requirements.txt` 添加 `sqlite-vec>=0.1.6`
- **状态**: MemoryStore 自动检测可用性，结合 Ollama embedding 生效

### P0#3: 自适应检索跳过 ✅
- **文件**: `memory/noise_filter.py` should_skip_retrieval()
- **集成**: `memory/store.py` search_hybrid() Stage 0
- **效果**: 问候/简单命令直接返回空，避免无意义检索

### P0#4: 自动备份 JSONL ✅
- **文件**: `memory/store.py` backup_jsonl() 方法
- **集成**: `brain_daemon.py` _run_engines_inner() 第5步，随引擎周期执行
- **配置**: 7天轮转，默认存储在 data/memory/backups/

### P0#5: harmful 反馈通路修复 ✅
- **文件**: `brain_learning.py` L92
- **修复**: `update_effectiveness(lid, effective)` 替代只传 True 的 bug
- **效果**: harmful_count 不再永远为 0

---

## 二、P1 完成项（低 LLM 成本，高收益）

### P1#6: 高频记忆 Block 直注 ✅ (对标 Letta)
- **文件**: `memory/block_inject.py` (114行, 新建)
- **集成**: `adapters/learning/memory_store_adapter.py` get_lessons() 置顶
- **机制**: helpful_count≥2 或 category=user_pref 的记忆直接注入 prompt 顶部
- **缓存**: 5分钟刷新间隔，零搜索延迟

### P1#7: 工具级观察采集 ✅ (对标 claude-mem)
- **文件**: `memory/tool_observer.py` (167行, 新建)
- **装饰器**: `adapters/tools/observed_tool.py` (78行, 新建)
- **集成**: `api/startup.py` ObservedToolAdapter 包装 tool_adapter
- **功能**: 记录 tool_name/input/output/success/duration，每会话限流50条

### P1#8: 两阶段提取+动作决策 ✅ (对标 mem0)
- **文件**: `memory/two_stage_extractor.py` (330行, 新建)
- **集成**: `memory/sync.py` reflect_on_session() use_two_stage 参数
- **流程**: Stage1 提取事实/偏好/教训 → Stage2 对比已有记忆决策 ADD/UPDATE/DELETE/SKIP
- **回退**: 无 LLM 时回退规则提取 + 全 ADD

---

## 三、激活与集成

### ACE 记忆系统激活 ✅
- `api/startup.py` L151: 已使用 MemoryStoreLearningAdapter（之前已完成）
- `cli.py` L123/137: JSONLessonsAdapter → MemoryStoreLearningAdapter
- `adapters/tools/introspect.py` L329: 回退适配器切换 + count() 兼容

### 工具观察装饰器 ✅
- `api/startup.py` L157: `tool_adapter = ObservedToolAdapter(tool_adapter, observer=...)`
- 所有工具调用自动记录到 observations 集合

### 自动备份 Cron ✅
- `brain_daemon.py` L179-184: _run_engines_inner() 第5步
- 随引擎周期（每轮空闲 tick）自动执行

---

## 四、文件清单

### 新建文件 (6个)
| 文件 | 行数 | 用途 |
|------|------|------|
| memory/noise_filter.py | 148 | 噪声过滤 + 自适应跳过 |
| memory/block_inject.py | 114 | 核心记忆 Block 直注 |
| memory/tool_observer.py | 167 | 工具观察采集 |
| memory/two_stage_extractor.py | 330 | 两阶段提取器 |
| adapters/tools/observed_tool.py | 78 | 工具观察装饰器 |
| tests/test_p1_enhancements.py | 359 | P1 测试 (32个) |
| tests/test_noise_filter.py | 188 | P0 测试 (25个) |

### 修改文件 (10个)
| 文件 | 改动 |
|------|------|
| memory/store.py | add() 噪声过滤 + search_hybrid() 跳过 + backup_jsonl() + merge_deltas skip |
| memory/sync.py | reflect_on_session 两阶段参数 |
| memory/__init__.py | 导出 3 个新模块 |
| adapters/learning/memory_store_adapter.py | CoreMemoryBlock + ToolObserver 集成 |
| adapters/tools/introspect.py | 切换到 MemoryStoreLearningAdapter |
| brain_learning.py | harmful 反馈通路修复 (1行) |
| brain_daemon.py | 自动备份 cron (5行) |
| api/startup.py | ObservedToolAdapter 装饰 + import |
| cli.py | JSONLessonsAdapter → MemoryStoreLearningAdapter |
| requirements.txt | sqlite-vec>=0.1.6 |
| tests/test_phase7_memory.py | skip_noise_filter 适配 |
| tests/test_phase8_ace.py | skip_noise_filter 适配 |
| CHANGELOG.md | v2.02 变更记录 |

---

## 五、测试结果

```
487 passed, 0 failed in 114.44s
新增测试: 57个 (25 noise_filter + 32 p1_enhancements)
退化: 0
```

## 六、诚实自查

| 检查项 | 状态 |
|--------|------|
| 所有功能真的完成？ | ✅ 代码已写入、集成、测试通过 |
| 测试真的运行了？ | ✅ pytest 真实输出 487/487 |
| 有降级运行？ | ⚠️ TwoStageExtractor Stage2 需 LLM (设计意图); 向量搜索需 Ollama 运行 |
| 涉及核心文件？ | api/startup.py(+2行), brain_daemon.py(+5行), brain_learning.py(+1行), cli.py(+2行) |

## 七、Embedding 管线修复 (2026-03-01 08:32)

### 问题
- memory_vectors 表有 **0 行数据** — sqlite-vec 已安装但无 embedding 写入
- store.add() 的 embedding 参数无人传入

### 修复
- `memory/store.py`: 新增 `embed_fn` 回调参数 + add() 自动调用 + `backfill_embeddings()` 渐进回填
- `adapters/learning/memory_store_adapter.py`: 注入 `VectorStore.embed` 作为 `embed_fn`
- `brain_daemon.py`: cron 增加 `backfill_embeddings(batch_size=10)` 调用
- 回填结果: memory_vectors **0 → 88 行**, search_hybrid 向量路径生效

### 验证
```
embed_fn: True
总回填: 88
memory_vectors: 88
hybrid搜索(含向量): 3 条 (score=0.597/0.568/0.505)
487/487 passed, 0 退化
```

## 八、下一步 (P2, 触发条件: 记忆>500条)

- 记忆分类升级 (8类)
- Reranking
- 意图分析检索
- L0/L1/L2 三层
