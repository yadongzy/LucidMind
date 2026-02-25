# 第十三条：代码质量保证（防腐铁律）

```
代码质量是项目长期存活的基础。以下规则强制执行：

1. 消息完整性（LLM 调用安全）
   - 发送给 LLM 的消息列表必须通过清洗（sanitize）
   - tool 消息必须紧跟在含 tool_calls 的 assistant 消息之后
   - 历史压缩不得打破 assistant(tool_calls) ↔ tool 的配对关系
   - 每次 _build_messages() 后必须校验消息结构合法性
   - 违反 = LLM API 400 错误 = 用户请求直接失败

2. 连接状态感知（资源泄漏防护）
   - WebSocket/HTTP 连接关闭后，禁止继续发送数据
   - Stream 适配器必须维护连接状态标志（_closed）
   - 首次发送失败后标记关闭，后续 emit 静默跳过
   - 禁止对已关闭连接产生刷屏式错误日志（>3 条同类错误后降级为 DEBUG）
   - 违反 = 日志污染 + 无效 I/O 开销

3. 异步纪律（事件循环安全）
   - 禁止在已有事件循环的上下文中调用 asyncio.run()
   - 同步方法需要调用异步代码时，使用 run_in_executor + 同步版本
   - 或将调用方改为 async 方法
   - asyncio.get_event_loop() 仅在确认无运行循环时使用
   - 违反 = 死锁 / RuntimeError / 功能静默失效

4. 死代码清理
   - Mixin 类必须被实际继承，否则删除或合并
   - 定义了但从未调用的方法必须标注 TODO 或删除
   - import 了但未使用的模块必须清理
   - 每次重构后检查是否产生了孤立代码

5. 平台适配
   - 错误恢复策略必须匹配运行平台（macOS/Linux/Windows）
   - 禁止在非 Windows 平台执行 powershell 命令适配
   - 禁止在非 Windows 平台将路径 / 替换为 \
   - 使用 platform.system() 判断后再执行平台相关逻辑

6. 资源生命周期
   - HTTP 客户端（httpx.AsyncClient）应复用，不应每次请求新建
   - 文件句柄必须在 finally 或 with 中关闭
   - 日志文件必须使用 RotatingFileHandler，防止无限增长
   - 后台任务必须有优雅停止机制（cancel + await）
```

## 检查清单（每次代码审查必过）

| 检查项 | 通过标准 |
|--------|---------|
| 消息清洗 | _build_messages() 返回前调用了 sanitize |
| 连接状态 | Stream emit 检查 _closed 标志 |
| 异步安全 | 无 asyncio.run() 在 async 上下文中 |
| 死代码 | 无未使用的 Mixin / 方法 / import |
| 平台适配 | 错误恢复逻辑匹配当前 OS |
| 资源复用 | httpx.AsyncClient 为长生命周期单例 |
| 日志轮转 | FileHandler → RotatingFileHandler |
