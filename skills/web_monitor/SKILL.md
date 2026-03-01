# Web Monitor 网页监控工具

## 工具
- `monitor_add` — 添加网页监控任务（URL + 检查间隔）
- `monitor_check` — 立即检查指定监控任务
- `monitor_list` — 列出所有监控任务及状态

## 使用场景
- 用户说"帮我监控这个网页有没有变化"时调用 `monitor_add`
- 用户说"看看那个页面更新了没"时调用 `monitor_check`

## 注意事项
- 通过 HTTP GET 获取页面内容，对比 hash 值判断变化
- 默认检查间隔 3600 秒（1小时）
- 监控数据持久化到 `data/monitors.json`
