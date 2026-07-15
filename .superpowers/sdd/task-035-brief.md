# T035：三市场新鲜度边界数据测试

## 目标

为 US1 锁定 A 股、港股、美股的行情新鲜度分级与休市边界，确保过期数据不会被显示为实时或用于当前预测。

## 修改范围

- 修改：`tests/property/test_freshness_rules.py`

## 必须先新增并运行失败的测试

新增此前未覆盖的性质/边界用例：

1. 对 CN、HK、US 三市场，分别覆盖 0 秒、实时上限、上限后一秒、60 秒、60 秒后一秒、15 分钟、15 分钟后一秒，严格断言 `REALTIME`、`NEAR_REALTIME`、`DELAYED`、`STALE` 的转换；CN 实时上限为 5 秒，HK/US 为 15 秒。
2. 使用带微秒的时间验证所有分级采用向上取整年龄，不允许通过截断把超过阈值的数据伪装为实时。
3. 交易日历关闭时，无论年龄为何都为 `CLOSED`，但未来市场时间、无时区时间、负年龄必须拒绝。
4. 新鲜度为 `DELAYED` 或 `STALE` 时，面向当前预测的可用性必须为否；只有可验证市场时间且 `REALTIME`/`NEAR_REALTIME` 才可进入当前研究输入。

## 约束

- 仅写测试和报告，不修改生产代码。
- 先运行测试并确认至少新增场景在当前实现前失败；不能通过测试内辅助实现绕过。
- 中文文档字符串与说明；不增加网络、券商或交易能力。

## 验证与报告

运行 `py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py -v` 并在 `D:/personal/bagholder/.superpowers/sdd/task-035-report.md` 记录失败证据、命令与输出摘要；提交后仅回复提交、测试摘要、concerns。
