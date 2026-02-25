# 第一条：架构 — 六边形（Ports & Adapters）

```
Brain 只认识 Port（接口），不认识 Adapter（实现）。
换 Adapter 不改 Brain 一行代码。
新功能 = 新 Adapter，不是改核心。

六个 Port：
  LLM Port      — 与大模型对话
  Tool Port     — 执行工具
  Memory Port   — 记忆存取
  Stream Port   — 思维流输出
  Channel Port  — 接收用户输入
  Learning Port — 经验学习
```
