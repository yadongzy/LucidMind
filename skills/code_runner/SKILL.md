# Code Runner

安全沙盒中执行 Python 代码和 Shell 命令。

## 工具
- `run_python`: 执行 Python 代码片段（沙盒环境，禁止危险操作）
- `run_command`: 执行 Shell 命令（受 ToolSafetyGuard 审批）
- `run_script`: 执行多行脚本

## 使用建议
- 数据处理、计算优先用 `run_python`
- 文件操作优先用 `read_file`/`write_file` 而非 shell 命令
- 长时间运行的命令会被超时终止（默认 30s）
- 沙盒禁止: `os.remove`, `socket`, `ctypes`, `importlib`

## 注意
- 不要用 `cat`/`echo` 读写文件，用专门的文件工具
- Shell 命令会触发安全审批弹窗
