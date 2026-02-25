# 第十条：代码守护（防退化铁律）

```
代码守护是防止项目质量倒退的最后一道防线。

1. 依赖方向（单向依赖，禁止反向）
   Brain → Port（接口）  ✅ 允许
   Adapter → Port        ✅ 允许
   Brain → Adapter       ❌ 禁止（违反六边形）
   Adapter → Brain       ❌ 禁止
   api/ → Brain          ✅ 允许（组装层）
   api/ → Adapter        ✅ 允许（组装层）
   tests/ → 任意         ✅ 允许

2. 禁止操作清单
   - 禁止在 brain.py 中 import 任何 adapters/ 下的模块
   - 禁止删除或注释掉已有的错误处理代码
   - 禁止将 try/except 改为 pass 而不记录日志
   - 禁止硬编码 API Key、密码、Token
   - 禁止在生产代码中使用 print()，必须用 logger
   - 禁止修改 ports/ 接口签名（除非走 06-extension 流程）
   - 禁止未经用户确认删除任何文件
   - 禁止未经用户确认修改前端文件（frontend/、frontend-v2/）
   - 禁止未经用户确认修改路由指向或静态文件挂载

3. 修改锁定文件的守护
   - 修改 [LOCKED] 文件前必须：
     a) 在对话中声明修改原因
     b) 获得用户确认
     c) 修改后重跑该模块全部测试
     d) 全部通过后重新标记 [LOCKED]
   - 紧急修复（bug fix）可跳过确认，但必须事后补测试

4. 退化检测
   - 每次代码修改后，必须运行 pytest
   - pytest 失败数增加 = 退化 = 禁止继续
   - 修复退化优先于一切新功能

5. 文件大小守护（补充 03-code-limits）
   - 前端 CSS: 600 行上限
   - 配置文件 (.env, pyproject.toml): 50 行上限
   - SOUL.md: 200 行上限
   - PROGRESS.md: 无上限（历史记录）
```
