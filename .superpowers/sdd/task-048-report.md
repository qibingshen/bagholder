# T048：预测标签与概率容差属性测试报告

## 范围

- 新增 `tests/property/test_prediction_labels.py`，仅包含 Hypothesis 性质测试和本地日历测试数据。
- 未修改生产代码，未生成预测，未访问网络，未执行交易。

## 覆盖的性质

- 周期仅接受 1、5、20 个交易日；交易日计数由传入且版本匹配的市场日历事实决定，不能由自然日间隔替代。
- 总回报复权收益率按 1 日正负 1%、5 日正负 3%、20 日正负 6% 分类；严格越过阈值才为上涨或下跌，等于正负边界为震荡。
- 预测时点拒绝未来才可得的到期价格、日历版本或特征，并在有效到期价格缺失时拒绝而不猜测。
- 三分类概率逐项非负、总和只能在 99.9 至 100.1 内，并拒绝 NaN、正无穷和负无穷。

## 红灯验证

先执行语法检查：

```powershell
py -3.12 -m py_compile tests/property/test_prediction_labels.py
```

语法检查通过。随后按任务要求执行：

```powershell
py -3.12 -m pytest -o addopts='' tests/property/test_prediction_labels.py -v
```

结果为收集阶段红灯：`ModuleNotFoundError: No module named 'stock_agent.domain.prediction'`。当前尚无预测标签领域模块，故新增测试未被实现转绿；本任务没有添加任何生产实现。

## 静态检查

```powershell
py -3.12 -m ruff check tests/property/test_prediction_labels.py
py -3.12 -m ruff format --check tests/property/test_prediction_labels.py
py -3.12 tools/check_chinese_project_text.py tests/property
```

三项检查均通过。

## Concerns

- 测试刻意保持红灯，后续 T050 实现 `stock_agent.domain.prediction` 时必须提供 `PredictionLabel`、`PredictionLabelRuleError`、`classify_prediction_label(...)` 与 `validate_prediction_probabilities(...)`，并满足本文件的时点和日历版本契约。
- 规格中的“达到阈值为上涨/下跌”表述与本任务简报的“等于边界归震荡”冲突；本测试按 T048 简报的明确边界规则实现，后续实现前应统一规格文字。
