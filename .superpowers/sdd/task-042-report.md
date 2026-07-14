# T042 证券研究视图模型报告

## 实现说明

新增 `src/stock_agent/desktop/viewmodels/security_view_model.py`，提供仅消费本地已验证事实的只读证券研究视图模型：

- `SecurityResearchViewModel.assemble` 直接保留 `HistoricalDailyBar`，因此每根日 K 线及成交量同时保留证券身份、交易日、OHLCV、币种、复权口径、来源、市场时间、采集时间、数据版本和新鲜度；不连接网络、不补造数值、不提供交易能力。
- `IndicatorFact`、`RelativeStrengthFact` 要求来源、市场时间、采集时间、输入数据版本和计算版本；`SectorMembershipFact` 要求来源、市场时间、采集时间和数据版本。缺任一必填溯源字段会由 Pydantic 拒绝。
- `DELAYED`、`STALE`、`CLOSED` 或缺少市场状态时，显示明确中文降级提示并设置 `current_prediction_allowed=False`；已验证的 `REALTIME` / `NEAR_REALTIME` 事实沿用既有新鲜度规则。
- 日 K 线、板块和指标均不存在时，返回明确空状态；不虚构价格、板块或指标。

## TDD 证据

先在 `tests/contract/test_market_data_contract.py` 增加视图模型公开契约。

1. 首次运行 `pytest tests/contract/test_market_data_contract.py` 红灯：
   `ModuleNotFoundError: No module named 'stock_agent.desktop.viewmodels'`，证明视图模型尚不存在。
2. 实现最小视图模型后，为已验证近实时行情增加当前预测资格契约；运行
   `pytest --no-cov tests/contract/test_market_data_contract.py -k "已验证近实时"` 红灯，断言实际得到 `False` 而期望 `True`。
3. 仅向既有新鲜度规则传递已验证时点事实后复验。

## 验证结果

- `pytest --no-cov tests/contract/test_market_data_contract.py`：`92 passed in 0.50s`。
- `ruff check src/stock_agent/desktop/viewmodels/security_view_model.py tests/contract/test_market_data_contract.py`：通过。
- `ruff format --check src/stock_agent/desktop/viewmodels/security_view_model.py tests/contract/test_market_data_contract.py`：通过。
- `python tools/check_chinese_project_text.py src/stock_agent/desktop/viewmodels`：通过。
- 全量 `pytest --no-cov` 在收集阶段被既有缺失页面模块阻断：
  `ModuleNotFoundError: No module named 'stock_agent.desktop.pages.market_page'`，来源为 `tests/contract/test_desktop_state_contract.py`，与本任务视图模型无关。
- 全仓 `ruff check .` 未通过，既有问题位于 `tests/contract/test_desktop_state_contract.py` 与 `tools/check_chinese_project_text.py`。
- 全仓中文检查未通过，既有问题位于 `tests/failure/test_market_data_failures.py:88`，提示“注释缺少简体中文解释”。本任务新增源文件的中文检查通过。

## 回滚策略

若需要回滚，只需删除本任务新增的 `desktop/viewmodels` 包，并还原 `test_market_data_contract.py` 中的证券研究视图契约；不会影响网络、预测、下单或交易路径。
