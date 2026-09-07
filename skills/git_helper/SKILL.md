# Git Helper

Git 版本控制操作。

## 工具
- `git_status`: 查看当前仓库状态
- `git_diff`: 查看文件差异
- `git_commit`: 提交更改（需安全审批）
- `git_log`: 查看提交历史

## 使用建议
- 先 `git_status` 了解当前状态
- commit 前先 `git_diff` 确认改动内容
- commit message 用中文或英文均可，建议简洁明确
- `git_log` 默认显示最近 10 条

## 注意
- `git_commit` 是 DANGEROUS 级别操作，会触发审批
- 不要用 `run_command git ...`，用专门的 git 工具
