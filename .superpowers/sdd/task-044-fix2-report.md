# T044 日历状态优先级修复报告（二次）

## 修复内容

- 调整 `MarketController` 的降级判定顺序：先判断 `trading_calendar_status`，只有 `OPEN` 才继续验证状态与新鲜度判断。
- 所有非 `OPEN` 状态现在均返回 `CLOSED`，即使 `is_verified=False`；`OPEN` 且未验证仍返回 `STALE`。
- `CLOSED` 页面不展示实时数据，且禁用当前预测；控制器继续仅使用本地市场服务和本地历史日线，不新增网络访问、预测交易或交易路径。

## TDD 记录

先在 `tests/integration/test_market_controller.py` 添加六个参数化回归场景：
`CLOSED`、`HOLIDAY`、`MIDDAY_BREAK`、`TYPHOON_SUSPENDED`、`PRE_MARKET`、`AFTER_HOURS`，均设置 `is_verified=False`。

红灯命令：

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_market_controller.py -q
```

红灯结果：`6 failed, 14 passed`。六个场景均错误得到 `STALE`，证明验证判断抢在日历关闭判断之前。

最小实现仅将 `_degradation_status` 中的非 `OPEN` 判断移动到 `is_verified` 判断之前。

## 验证

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_market_controller.py tests/contract/test_desktop_state_contract.py -q
py -3.12 -m ruff check src/stock_agent/desktop/controllers/market_controller.py tests/integration/test_market_controller.py
py -3.12 -m ruff format --check src/stock_agent/desktop/controllers/market_controller.py tests/integration/test_market_controller.py
py -3.12 tools/check_chinese_project_text.py src/stock_agent/desktop/controllers
```

- 控制器集成测试与页面状态契约测试：`54 passed`。
- Ruff 检查通过，两个改动文件均已格式化。
- 控制器目录中文检查通过；新增测试的测试名、文档字符串与说明均使用简体中文，状态常量保留英文协议值。
