# T127 固定风险提示审计

## 审计范围

本记录核对预测、报告、回测模拟和相关自然语言研究对话产物是否显示固定风险提示：“研究参考，不构成投资建议”。本审计不证明任何真实行情、预测准确性或收益表现。

## 固定风险提示位置

| 产物 | 实现或契约位置 | 当前结论 |
| --- | --- | --- |
| 预测输出 | `src/stock_agent/domain/prediction.py` 的 `FIXED_RESEARCH_DISCLAIMER` 与预测输出校验 | 已强制等于固定文本 |
| 预测展示 | `src/stock_agent/application/prediction_presenter.py` 与 `src/stock_agent/desktop/pages/prediction_page.py` | 展示层二次校验固定文本，并拒绝收益承诺或买卖指令 |
| 每日报告 | `src/stock_agent/domain/daily_report.py` | 报告快照强制包含固定文本 |
| 研究对话 | `src/stock_agent/application/research_chat_service.py` 与 `src/stock_agent/desktop/pages/research_chat_page.py` | 对话回答视图默认携带固定文本，且量化数字必须绑定 MCP 工具事实引用 |
| 模型中心 | `src/stock_agent/desktop/pages/model_management_page.py` | 模型治理页面显示固定文本 |
| 回测模拟 | `docs/acceptance/us6-backtest-results.md`、`tests/contract/test_backtest_contract.py`、`tests/failure/test_backtest_trading_constraints.py` | 回测结果被限定为历史验证和研究复盘，不构成投资建议 |
| 验收文档 | `docs/acceptance/us2-prediction-safety.md`、`docs/acceptance/us5-daily-reports.md`、`docs/acceptance/us7-model-governance.md`、`docs/acceptance/test-evidence.md` | 相关验收文档均记录固定风险提示或禁止收益承诺 |

## 可复跑证据

建议复跑：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_prediction_contract.py tests/contract/test_prediction_page_contract.py tests/contract/test_prediction_presenter.py tests/contract/test_daily_report_contract.py tests/contract/test_research_chat_page_contract.py tests/contract/test_model_management_page.py tests/contract/test_us5_acceptance_doc.py tests/contract/test_us6_acceptance_doc.py tests/contract/test_model_governance_acceptance_doc.py -q
```

本次全量门禁记录见 `docs/acceptance/test-evidence.md`，其中 `py -3.12 -m pytest` 已通过 `650 passed`。

## 审计结论

当前预测、报告、回测模拟、模型治理和研究对话相关产物均有固定风险提示或对应契约测试。后续新增导出、打印、通知、截图或自然语言总结入口时，必须同步加入“研究参考，不构成投资建议”，并新增对应契约测试或审计记录。
