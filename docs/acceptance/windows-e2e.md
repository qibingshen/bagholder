# Windows 端到端验收记录

## 当前状态

状态：未完成。

原因：当前仓库已提供 `packaging/windows/build.ps1`，但尚未在 Windows 10/11 干净环境中生成并验收安装包产物。本机已完成全量测试、格式检查、静态检查、中文规范检查和空白检查，但这不能替代“安装、启动、升级、核心流程与数据恢复”的安装包端到端验收。

## 已有证据

- `py -3.12 -m pytest`：`650 passed in 12.59s`，覆盖率 `88.53%`。
- `py -3.12 -m ruff format --check src tests`：通过。
- `py -3.12 -m ruff check src tests`：通过。
- `py -3.12 tools/check_chinese_project_text.py`：通过。
- `git diff --check`：通过。

## 完成 T124 仍需补齐

1. 在 Windows 10/11 干净环境执行 `packaging\windows\build.ps1`。
2. 保存构建产物哈希、文件清单和 `tools/packaging_guard.py` 检查结果。
3. 在干净用户数据目录中安装并启动桌面端。
4. 验证历史日线采集、本地存储、特征计算、简单基准预测、时间序列回测、MCP 查询、AI 解释、PySide6 展示和每日报告闭环。
5. 验证升级后保留本地数据、设置和任务状态。
6. 验证备份恢复后不覆盖原始行情、预测快照和已验证报告。

固定风险提示：研究参考，不构成投资建议。
