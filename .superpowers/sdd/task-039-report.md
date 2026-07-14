# T039 证券目录、市场状态与交易日历查询实现报告

## 实现结果

- 新增 `src/stock_agent/application/market_service.py`，提供只读取传入事实或内置受控离线样例的市场状态、证券身份目录解析和历史日线查询；未建立网络连接，未实现预测或交易能力。
- `MarketStatus` 强制市场时区、受控日历状态、带时区的市场/采集时点、来源、新鲜度与数据版本；缺少市场或本地状态事实时明确拒绝。
- `HistoricalDailyBar` 强制保留价格、币种、复权、来源、版本和时点，并拒绝实时新鲜度标记。
- 补充带来源、采集时点和版本的 `InstrumentCatalogEntry` 本地目录查询，以及 `resolve_instrument_identity` 候选解析；非唯一显示代码必须指定市场或交易所。

## TDD 记录

先执行指定红灯命令：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py tests/failure/test_market_data_failures.py -v
```

初始结果为收集失败，原因是 `stock_agent.application.market_service` 不存在。完成最小实现后，T039 相关市场状态、历史日线和证券身份边界用例通过。

## 验证结果

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py -k '市场状态 or 历史日线 or 市场接受 or 市场拒绝' -v
```

结果：`49 passed, 28 deselected`。

```powershell
py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -k '未带市场标识的非唯一显示代码' -v
```

结果：`1 passed, 49 deselected`。

```powershell
py -3.12 -m ruff format --check src/stock_agent/application/market_service.py src/stock_agent/domain/market.py
py -3.12 -m ruff check src/stock_agent/application/market_service.py src/stock_agent/domain/market.py
py -3.12 tools/check_chinese_project_text.py src
```

结果：全部通过。

全仓 Ruff 命令 `py -3.12 -m ruff format --check src tests` 与
`py -3.12 -m ruff check src tests` 未通过：既有
`tests/contract/test_desktop_state_contract.py`、
`tests/contract/test_market_data_contract.py` 和
`tests/property/test_freshness_rules.py` 存在格式、导入排序或行长诊断；本任务新增和修改文件的
Ruff 检查通过。全仓中文检查通过。

全量命令 `py -3.12 -m pytest -o addopts='' -v` 在收集阶段被既有缺失模块
`stock_agent.desktop.pages.market_page` 阻断，未执行测试主体。

组合命令中还有 13 项既有失败，分别属于当前预测新鲜度显式拒绝、`InstrumentIdentity`
构造阶段的市场一致性，以及公司行为/复权历史规则；本任务未修改预测或交易相关能力。
