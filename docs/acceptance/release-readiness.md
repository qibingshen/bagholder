# T129 发布准备结论

## 当前结论

状态：阻止发布。

原因：T124、T125、T126 三平台安装包构建、安装、启动、升级、核心流程和数据恢复验收尚未完成。当前仓库已经完成大量本地质量门禁、研究边界审计和模型回滚演练证据，但不能替代 Windows、macOS、Linux 的真实端到端安装包验收。

## 已完成证据

| 类别 | 证据 | 结论 |
| --- | --- | --- |
| 全量测试 | `docs/acceptance/test-evidence.md` | `650 passed`，覆盖率 `88.53%` |
| 中文规范 | `docs/acceptance/chinese-conventions-results.md` | 通过 |
| 桌面状态矩阵 | `docs/acceptance/desktop-state-matrix.md` | 已记录差异和修复证据 |
| 固定风险提示 | `docs/acceptance/disclaimer-audit.md` | 已覆盖预测、报告、回测模拟、模型治理和研究对话 |
| 研究边界 | `docs/acceptance/research-boundary-audit.md` | 未发现券商连接、真实交易、收益承诺、MCP 管理工具或凭据泄露入口 |
| 模型治理 | `docs/acceptance/us7-test-results.md` | 候选模型发布门禁、影子运行、人工批准、原子发布和回滚失败场景测试通过 |
| 备份恢复 | `docs/acceptance/us8-test-results.md` | 备份清单、隔离恢复、容量预算和失败恢复测试通过 |

## 发布阻断项

| 任务 | 证据文件 | 当前状态 |
| --- | --- | --- |
| T124 Windows 安装包端到端验收 | `docs/acceptance/windows-e2e.md` | 未完成，已提供 `packaging/windows/build.ps1`，但缺少 Windows 10/11 真实安装包产物和端到端验收 |
| T125 macOS Apple Silicon/Intel 端到端验收 | `docs/acceptance/macos-e2e.md` | 未完成，已提供 `packaging/macos/build.sh`，但当前 Windows 环境不能替代 macOS 实机或 CI |
| T126 Ubuntu 22.04/24.04 端到端验收 | `docs/acceptance/linux-e2e.md` | 未完成，已提供 `packaging/linux/build.sh`，但当前 Windows 环境不能替代 Linux 实机或 CI |
| T045 真实用户可用性验收 | `docs/acceptance/us1-usability-study.md` | 未完成，缺少真实参与者执行结果，不能伪造 90%/3 分钟通过率 |

## 发布前必须补齐

1. 在目标平台分别执行 Windows、macOS、Linux 的真实打包脚本。
2. 在目标平台分别安装、启动、升级并恢复本地数据、设置和任务状态。
3. 记录三平台构建产物哈希、运行日志、`tools/packaging_guard.py` 检查结果和失败恢复结果。
4. 完成 T045 的真实用户可用性研究，或由产品决策明确将其移出首个发布门禁。
5. 重新运行 `py -3.12 -m pytest`、Ruff、中文规范和 `git diff --check`。

固定风险提示：研究参考，不构成投资建议。
