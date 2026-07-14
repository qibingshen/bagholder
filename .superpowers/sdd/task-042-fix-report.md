# T042 证券研究视图模型审查修复报告

## 修复范围

- 视图模型的日线字段改为直接接收采集链路真实产物 `IngestedHistoricalDailyBar`，不再使用 `MarketService` 中不兼容的平行日线模型。
- 采集日线新增并强制保存 `artifact_version_id`；视图继续保留原有 `source_data_version`、来源和市场/采集时点。
- `HistoricalFreshness` 仅接受 `HISTORICAL`，采集日线和视图模型均防御性拒绝其他新鲜度状态。
- 当前预测准入同时要求交易日历为 `OPEN`、市场与采集时点可验证，以及既有新鲜度规则允许；`CLOSED` 和 `HOLIDAY` 一律为 `False`。
- 指标、相对强弱和板块事实均新增 `security_id`，组装时发现任一事实跨证券即整批拒绝。
- 空状态判定纳入相对强弱事实，只有相对强弱时不再显示“暂无事实”。

## TDD 证据

先在 `tests/contract/test_market_data_contract.py` 新增真实采集日线、历史新鲜度、交易日历、跨证券事实和相对强弱空状态的回归测试，再运行：

```powershell
pytest --no-cov tests/contract/test_market_data_contract.py -k "直接保留真实采集 or 拒绝被标记 or 交易日历未开市 or 另一证券 or 只存在相对强弱"
```

红灯结果为 `10 failed`：真实采集日线不能被 Pydantic 视图模型接收、非 `HISTORICAL` 状态未被拒绝、闭市/休市仍允许当前预测、跨证券衍生事实被渲染，以及仅有相对强弱时被误判为空状态。

## 验证结果

- `pytest --no-cov tests/contract/test_market_data_contract.py tests/integration/test_single_market_daily_pipeline.py`：`118 passed`。
- `ruff check src/stock_agent/desktop/viewmodels/security_view_model.py src/stock_agent/workers/market_ingestion.py tests/contract/test_market_data_contract.py`：通过。
- `ruff format --check src/stock_agent/desktop/viewmodels/security_view_model.py src/stock_agent/workers/market_ingestion.py tests/contract/test_market_data_contract.py`：通过。
- `python tools/check_chinese_project_text.py src/stock_agent/desktop/viewmodels`、`src/stock_agent/workers` 和 `tests/contract`：通过。
- 全量 `pytest --no-cov` 在收集阶段被既有缺失模块阻断：`tests/contract/test_desktop_state_contract.py` 导入 `stock_agent.desktop.pages.market_page` 失败；本任务未修改该页面模块。

## 风险与回滚

本次不连接网络、不生成预测数值，也不提供交易能力。若需回滚，可撤销本次对 `market_ingestion.py`、`security_view_model.py` 和对应契约测试的修改；采集工件版本字段是视图溯源完整性的必要契约。
