# T044 日历状态门禁修复报告

## 修复内容

- 根因：`MarketController` 仅将 `CLOSED` 与 `HOLIDAY` 识别为交易日历降级状态，导致
  `MIDDAY_BREAK`、`TYPHOON_SUSPENDED`、`PRE_MARKET` 和 `AFTER_HOURS` 在本地状态新鲜且
  已验证时可能穿透至 `READY`。
- 将日历门禁收紧为白名单：仅 `trading_calendar_status == "OPEN"` 可继续构造
  `READY` 市场页；所有其他受控非开市状态均明确降级为 `CLOSED`，不显示实时数据且不允许
  当前预测。
- 新增跨市场参数化集成用例，覆盖中国市场 `MIDDAY_BREAK`、香港市场
  `TYPHOON_SUSPENDED`、美国市场 `PRE_MARKET` 与 `AFTER_HOURS`。用例通过真实
  `MarketController` 路径验证页面状态、实时展示和当前预测三个门禁结果。
- 未修改本地事实来源、历史日线组合逻辑；未新增网络访问、预测数值或交易路径。

## TDD 记录

先在 `tests/integration/test_market_controller.py` 添加四种非 `OPEN` 日历状态的参数化测试，
再运行：

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_market_controller.py -q
```

红灯结果为 `4 failed, 10 passed`：四种状态均未得到预期的 `CLOSED`；其中
`MIDDAY_BREAK` 错误进入 `READY`，其余三种因后续本地目录事实不足而落入 `EMPTY`。这证明
日历门禁没有在组合本地目录之前统一阻断非开市状态。

随后仅将降级判定改为 `trading_calendar_status != "OPEN"`，同一目标测试转绿为
`14 passed`。

## 验证

- 控制器集成与页面契约：

  ```powershell
  py -3.12 -m pytest -o addopts='' tests/integration/test_market_controller.py tests/contract/test_desktop_state_contract.py -q
  ```

  结果：`48 passed`。

- 改动范围 Ruff：`ruff check` 通过；`ruff format --check` 显示两份文件均已格式化。
- 改动范围中文检查：控制器目录与 `tests/integration` 均通过。
- 全量 pytest：`323 passed, 10 failed`。失败均位于既有的
  `tests/failure/test_market_data_failures.py`（当前预测拒绝、`CompanyAction` 参数及复权辅助函数）
  和 `tests/property/test_market_rules.py`（港股六码规则），未涉及本次控制器日历门禁文件。
- 全仓 Ruff：失败 2 项，均位于既有的 `tools/check_chinese_project_text.py`（导入排序与长行）。
- 全仓中文检查：失败 1 项，位于既有的
  `tests/failure/test_market_data_failures.py:88`，该注释缺少简体中文说明。
