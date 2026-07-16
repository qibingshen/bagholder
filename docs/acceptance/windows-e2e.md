# Windows 端到端验收记录

## 当前状态

状态：部分完成，仍阻止正式发布。

原因：当前仓库已提供并在本机执行 `packaging/windows/build.ps1`，已生成 Windows 打包产物并完成最小启动验证；但尚未在 Windows 10/11 干净环境中完成安装、升级、核心流程与数据恢复验收，因此不能把 T124 标记为完成。

## 已有证据

- `py -3.12 -m pytest`：`650 passed in 12.59s`，覆盖率 `88.53%`。
- `py -3.12 -m ruff format --check src tests`：通过。
- `py -3.12 -m ruff check src tests`：通过。
- `py -3.12 tools/check_chinese_project_text.py`：通过。
- `git diff --check`：通过。
- `packaging\windows\build.ps1`：通过，生成 `dist/windows/bagholder/bagholder.exe`。
- `tools/packaging_guard.py dist/windows/manifest.txt`：通过，未发现凭据、本地数据库、行情缓存或预测快照入包。
- `dist/windows/bagholder/bagholder.exe`：通过 PySide6 最小桌面窗口启动验证，窗口标题为“本地量化股票分析智能体”。
- Windows 打包产物 SHA-256：`AD4558F4D0F92A498B7509A473C84B1FD024E44BA07E7577F4885CE27EC234B0`。

## 完成 T124 仍需补齐

1. 在 Windows 10/11 干净环境重复执行 `packaging\windows\build.ps1`。
2. 在干净用户数据目录中安装并启动桌面端。
3. 验证历史日线采集、本地存储、特征计算、简单基准预测、时间序列回测、MCP 查询、AI 解释、PySide6 展示和每日报告闭环。
4. 验证升级后保留本地数据、设置和任务状态。
5. 验证备份恢复后不覆盖原始行情、预测快照和已验证报告。
6. 补充 Windows 10 与 Windows 11 的独立验收记录。

固定风险提示：研究参考，不构成投资建议。
