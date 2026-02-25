# 第五条：锁定清单

```
[LOCKED] 文件列表（通过真实测试后加入）：

核心文件（始终锁定）：
  - brain.py
  - brain_daemon.py
  - brain_meta.py
  - task_dispatcher.py
  - api/main.py
  - ports/ 下所有接口文件

已通过测试的模块（动态维护）：
  （通过真实测试后在此添加，格式：文件路径 | 锁定日期 | 测试证据）

修改流程：
Step 1: 声明要改什么、为什么
Step 2: 等待用户确认
Step 3: 修改
Step 4: 重跑所有真实测试
Step 5: 全部通过后重新锁定

紧急修复（bug fix）可跳过 Step 2，但必须事后补测试并报告。
```
