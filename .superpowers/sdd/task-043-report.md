# T043 市场与证券页面状态模型报告

## 实现

- 新增 `MarketPageState` 与 `SecurityPageState`，均支持 `EMPTY`、`LOADING`、`OFFLINE`、`PERMISSION_DENIED`、`STALE`、`READY`、`RECOVERED`，并额外支持本地交易日历的 `CLOSED` 状态。
- 每个状态保留原始状态标识和简体中文用户说明。
- `OFFLINE`、`STALE`、`CLOSED`、`PERMISSION_DENIED` 的 `shows_realtime` 与 `current_prediction_allowed` 均为 `False`；同时保留渲染层兼容属性 `show_realtime_data` 和 `allow_current_prediction`。
- 页面模型仅接收脱敏状态，不包含网络请求、预测数值生成或交易能力。

## TDD 记录

先执行：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_desktop_state_contract.py -v
```

红灯结果：测试收集失败，`ModuleNotFoundError: No module named 'stock_agent.desktop.pages.market_page'`。随后新增最小页面状态模型，同一命令转绿。

## 验证

- 页面状态合约：34 passed。
- 页面文件 Ruff：`All checks passed!`。
- 页面文件编译：`py -3.12 -m compileall -q src/stock_agent/desktop/pages` 成功。
- 中文检查：人工检查新增模块的文档字符串、注释与用户可见文案均为简体中文；英文仅用于状态标识和代码标识符。
- 全量 pytest：309 passed，10 failed。失败均位于既有市场新鲜度、公司行动与港股代码规则实现，未涉及本任务新增页面状态文件。

## 已知关注项

全量失败包括当前预测拒绝、`CompanyAction` 参数和公司行动辅助函数缺失，以及港股六位代码校验；这些为任务范围外的既有失败，未在 T043 中修改。
