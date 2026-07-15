# T048：预测标签与概率容差属性测试报告

## 本次修正

- 将测试明确拆为两个阶段：`PredictionInput` 不得读取到期复权价格或其可得时点；到期后由 `resolve_actual_outcome(...)` 建立独立实际结果，允许 `expiry_price_available_at > prediction_time`。
- 到期价格缺失时断言实际结果为 `PENDING_VALIDATION`、无标签且无到期价格，不再断言抛出标签错误或强行分类。
- 使用显式的非连续美股交易日日历：跳过周末、7 月 3 日节假日和 7 月 15 日临停日；分别断言 1、5、20 个有效交易日到期日为 7 月 6 日、7 月 10 日、8 月 3 日，不以 `timedelta` 推导。
- 补充未来生效公司行动不得进入预测输入，以及到期结果锁定预测快照的标签规则版本、拒绝被新版回写的测试。
- 概率性质收紧为每项 `0 <= p <= 100` 且总和位于 `100% ±0.1`；显式覆盖单项 `100.05` 即使总和在容差内也必须拒绝。
- 未修改生产代码，未生成预测，未访问网络，未执行交易。

## 红灯验证

```powershell
py -3.12 -m pytest -o addopts='' tests/property/test_prediction_labels.py -v
```

预期结果为收集阶段红灯：`stock_agent.domain.prediction` 尚未实现。该红灯同时表明后续实现必须提供预测输入、到期实际结果、状态和版本不可变边界；本任务不实现生产模块。

## 静态检查

```powershell
py -3.12 -m py_compile tests/property/test_prediction_labels.py
py -3.12 -m ruff check tests/property/test_prediction_labels.py
py -3.12 -m ruff format --check tests/property/test_prediction_labels.py
py -3.12 tools/check_chinese_project_text.py tests/property
```

## Concerns

- 目标测试在生产模块缺失时只能验证收集阶段红灯；T050 及到期结果持久化实现后，需重新运行本测试，确认所有新增性质转绿。
- 测试契约要求实际结果为独立记录并锁定原预测快照的标签规则版本；不得以新版规则或到期结果字段改写历史预测。
