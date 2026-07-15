# US7 模型治理测试结果记录

## 记录范围

本记录对应 T118，用于固化候选模型契约、发布门禁、失败场景、模型中心页面和验收说明检查结果。US7 仅用于研究阶段候选模型治理，不连接券商、不执行真实交易、不承诺收益。

固定风险提示：研究参考，不构成投资建议。

## 指定测试命令

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_model_contract.py tests/property/test_model_release_gates.py tests/failure/test_model_governance_failures.py tests/contract/test_model_management_page.py tests/contract/test_model_governance_acceptance_doc.py -q
```

## 执行结果

本次执行输出：`14 passed in 0.70s`，命令退出码为 0。

| 类别 | 文件 | 覆盖重点 | 当前结果 |
| --- | --- | --- | --- |
| 模型契约 | `tests/contract/test_model_contract.py` | 候选模型版本、工件哈希、训练范围、特征版本、评估报告、人工批准和回滚计划 | 通过 |
| 发布门禁 | `tests/property/test_model_release_gates.py` | Brier 改善、平衡准确率改善、简单基准比较、分组退化和至少 30 个交易日影子运行 | 通过 |
| 失败场景 | `tests/failure/test_model_governance_failures.py` | 严重故障、未来数据泄漏、未经授权发布、MCP 管理动作拒绝、原子切换失败和回滚失败 | 通过 |
| 模型中心页面 | `tests/contract/test_model_management_page.py` | 门禁证据、发布确认、回滚确认和固定风险提示 | 通过 |
| 验收说明检查 | `tests/contract/test_model_governance_acceptance_doc.py` | 候选模型、简单基准、30 个交易日、人工批准、原子发布、回滚和 MCP 边界 | 通过 |

## 验收结论

US7 当前满足：候选模型不能直接覆盖正式模型；发布前必须通过时间序列回测、简单基准比较、至少 30 个交易日影子运行和人工批准；严重故障与未来数据泄漏会阻断发布；发布指针切换和回滚必须可审计且失败安全；MCP 管理动作保持默认拒绝，不能绕过桌面端确认。

后续调整模型发布门槛、影子运行证据、人工批准、回滚审计或 MCP 管理权限时，必须重新运行本记录中的指定测试命令。
