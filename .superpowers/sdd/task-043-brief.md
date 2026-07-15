# T043：市场与证券页面状态模型

## 目标

实现 T034 已锁定的市场总览和个股研究页面状态模型，覆盖空、加载、离线、权限受限、过期、可用与恢复，且不将降级数据伪装为实时。

## 修改范围

- 新建：`src/stock_agent/desktop/pages/market_page.py`
- 新建：`src/stock_agent/desktop/pages/security_page.py`
- 修改：`tests/contract/test_desktop_state_contract.py`，只为接入真实接口；不得删除已批准断言。

## TDD 与行为要求

1. 先运行现有页面状态红灯测试；确认缺少页面模块/接口后再实现。
2. 每个状态必须保留可识别状态标识与明确简体中文说明；EMPTY、LOADING、OFFLINE、PERMISSION_DENIED、STALE、READY、RECOVERED 均需支持。
3. OFFLINE/STALE/CLOSED/权限受限时必须 `shows_realtime=False`、`current_prediction_allowed=False`；RECOVERED 仅在可验证本地事实重新可用时恢复。
4. 页面只接受本地 MarketService/SecurityResearchViewModel 事实或脱敏状态，不能连接网络、生成预测数值或交易。

## 验证

运行 `py -3.12 -m pytest -o addopts='' tests/contract/test_desktop_state_contract.py -v`，再运行全量 pytest、Ruff、中文检查。报告 `D:/personal/bagholder/.superpowers/sdd/task-043-report.md`，提交后只回复提交、测试摘要、concerns。
