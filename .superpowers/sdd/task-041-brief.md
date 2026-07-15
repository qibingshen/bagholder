# T041：行情新鲜度与当前预测阻断规则

## 目标

实现 T035 已批准的红灯测试所要求的生产规则，确保当前预测只消费时点可验证且足够新鲜的行情。

## 修改范围

- 修改：`src/stock_agent/domain/freshness.py`
- 可修改：`tests/property/test_freshness_rules.py`，仅限为了让测试对真实公开接口成立而进行的最小契约对齐；不得删除已批准的边界断言。

## 行为要求

1. 提供公开的、可由调用方使用的“当前预测新鲜度事实”接口或等价强类型模型，包含状态、市场时间、采集时间和时点可验证性。
2. 仅当状态为 `REALTIME` 或 `NEAR_REALTIME`、两时间均带时区、市场时间不晚于采集时间、`time_is_verifiable=True` 时返回可用于当前预测。
3. `DELAYED`、`STALE`、`CLOSED`、未知状态、缺时区、未来市场时间、负年龄或显式不可验证时点均必须返回不可用或抛出明确领域异常；不得默认放行未知状态。
4. 复用现有 `calculate_age_seconds` / `classify_freshness` 的规则，不得改变 CN 5 秒、HK/US 15 秒、60 秒、900 秒、休市和微秒向上取整边界。

## TDD 与验证

T035 已记录红灯。先运行：

`py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py -v`

确认失败仍是缺少规则入口，再作最小实现并运行同一命令至全绿；随后运行全量 pytest、Ruff 格式/检查与中文规范检查。把红绿证据、接口说明和命令结果写入 `D:/personal/bagholder/.superpowers/sdd/task-041-report.md`。提交后仅回复提交、测试摘要、concerns。
