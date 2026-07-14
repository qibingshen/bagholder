# T034 契约测试报告

## 新增用例

- 市场状态查询：覆盖 A 股、港股、美股；要求返回市场标识、市场时区、交易日历状态、市场时点、采集时点、来源和新鲜度。
- 市场状态校验：缺少市场时点或采集时点时拒绝构造状态。
- 历史日线：要求包含证券身份、交易日、开高低收、成交量、复权口径、币种、来源、市场时点、采集时点、数据版本和新鲜度；拒绝将历史数据标为实时。
- 历史日线查询：拒绝倒置日期范围及跨市场不匹配的证券代码。
- 桌面状态：市场页和个股页均覆盖空、加载、离线、权限受限、过期、可用和恢复状态，并要求中文用户说明；离线或过期时禁用实时数据及当前预测；恢复后标明可用。

## 失败验证

执行命令：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py tests/contract/test_desktop_state_contract.py -v
```

结果：测试收集阶段以预期的接口缺失失败，未执行任何生产代码实现。

- `tests/contract/test_market_data_contract.py:19`：`ModuleNotFoundError: No module named 'stock_agent.application.market_service'`
- `tests/contract/test_desktop_state_contract.py:5`：`ModuleNotFoundError: No module named 'stock_agent.desktop.pages.market_page'`

pytest 摘要：`collected 0 items / 2 errors`，进程退出码为 `2`。

## 范围确认

仅新增或修改契约测试与本报告；未修改 `src/`，未引入任何数据源 HTTP、券商、下单或交易能力。
