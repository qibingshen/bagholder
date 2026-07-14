# T035：三市场新鲜度边界数据测试报告

## 修改范围

- 新增 `tests/property/test_freshness_rules.py` 的三市场完整秒级边界断言：0 秒、各市场实时上限、上限后一秒、60 秒、61 秒、900 秒、901 秒。
- 新增带微秒的年龄分级断言，覆盖 CN、HK、US 的实时、近实时、延迟和过期阈值，要求年龄向上取整。
- 新增交易日历关闭时有效时间一律为 `CLOSED` 的跨市场用例，并验证休市不能绕过未来时间、无时区时间和负年龄的拒绝规则。
- 新增当前预测可用性契约：仅 `REALTIME` 和 `NEAR_REALTIME` 可用，`DELAYED`、`STALE`、`CLOSED` 不可用。

未修改 `src/` 下的生产代码。

## 失败证据

在新增测试后、未实现当前预测可用性规则前运行：

```powershell
py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py -v
```

结果：共收集 62 项，57 项通过、5 项失败，退出码为 1。

失败用例均为 `test_仅有效实时或近实时行情可用于当前预测` 的五个新参数场景（`REALTIME`、`NEAR_REALTIME`、`DELAYED`、`STALE`、`CLOSED`）。失败原因一致：`stock_agent.domain.freshness` 尚未提供 `is_usable_for_current_prediction`，报出 `AttributeError`。这证明新增测试没有被现有实现满足，且失败点是当前预测可用性规则尚未落地。

同一命令中，新增的三市场秒级边界、微秒向上取整、休市优先级，以及既有的未来时间、无时区时间和负年龄拒绝用例均按预期通过。

## 后续实现边界

后续生产实现应在不放宽时间校验的前提下，提供当前预测可用性规则：仅经验证的 `REALTIME` 与 `NEAR_REALTIME` 可进入当前研究输入；`DELAYED`、`STALE` 与 `CLOSED` 必须被拒绝。
