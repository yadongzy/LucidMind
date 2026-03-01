# Clipboard 剪贴板工具

## 工具
- `clipboard_read` — 读取系统剪贴板内容（纯文本）
- `clipboard_write` — 写入内容到系统剪贴板

## 使用场景
- 用户说"帮我复制一下"、"把结果放到剪贴板"时调用 `clipboard_write`
- 用户说"剪贴板里有什么"、"读一下剪贴板"时调用 `clipboard_read`

## 注意事项
- 仅支持 macOS（`pbcopy`/`pbpaste`）
- 只处理纯文本，不支持图片/富文本
- 写入前无需确认（非破坏性操作）
