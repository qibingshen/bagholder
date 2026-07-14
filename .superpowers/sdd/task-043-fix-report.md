# T043 恢复状态阻断修复报告

## 根因与修复

- 根因：`MarketPageState` 与 `SecurityPageState` 将普通字符串
  `status="RECOVERED"` 直接视为可用状态，未要求任何本地事实证据。
- 新增 `MarketStatus.is_verified`，默认值为 `False`，作为本地事实的显式验证标记。
- 页面恢复仅经 `from_market_status` 受控工厂创建；工厂只接受完整的
  `MarketStatus`，并校验 `source_id`、市场时间、采集时间、数据版本、
  `is_verified`、时区、时间顺序和非未来时点。
- 缺少事实、未验证、无时区、未来或时间顺序异常的证据均降级为 `STALE`。
  普通 `status="RECOVERED"` 构造同样降级，不能伪造恢复。
- 恢复状态仍不展示实时数据，也不允许当前预测；页面未引入网络访问、预测值
  生成或交易能力。移除了未使用的 `_不可实时状态` 常量。

## TDD 记录

先修改 `tests/contract/test_desktop_state_contract.py`，再运行：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_desktop_state_contract.py -q
```

红灯结果：6 项失败。直接构造仍得到 `RECOVERED`，且两个页面均没有
`from_market_status` 受控工厂。随后进行最小实现，再运行同一页面契约。

## 验证

- 页面状态契约：`34 passed`。
- 改动范围 Ruff：`All checks passed!`。
- 改动范围中文检查：通过。
- 全量 pytest：`309 passed, 10 failed`；失败均位于既有的市场新鲜度拒绝、
  `CompanyAction` 参数/辅助函数和港股六码规则，不涉及本次页面恢复状态代码。
- 全仓 Ruff：失败 2 项，均位于既有
  `tools/check_chinese_project_text.py` 的导入排序与长行。
- 全仓中文检查：失败 1 项，位于既有
  `tests/failure/test_market_data_failures.py:88` 的注释缺少简体中文解释。
