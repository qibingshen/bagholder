# T048：预测标签与概率容差属性测试报告

## 本次修正

- 已依据 `spec.md` 与 `contracts/predictions.md` 统一标签边界：收益率 `>=` 正阈值为上涨，`<=` 负阈值为下跌，其余为震荡。
- 已更新 `tests/property/test_prediction_labels.py`：对 1、5、20 个交易日分别使用 ±1%、±3%、±6% 阈值，并在性质断言与精确边界断言中覆盖等于阈值的上涨/下跌结果。
- 未修改任何生产代码，未生成预测，未访问网络，未执行交易。

## 红灯验证

先按任务要求执行：

```powershell
py -3.12 -m pytest -o addopts='' tests/property/test_prediction_labels.py -v
```

结果为预期红灯：测试收集阶段因尚未实现 `stock_agent.domain.prediction` 而报 `ModuleNotFoundError`。本任务仅修正测试与报告，不实现该领域模块。

## 静态检查

```powershell
py -3.12 -m py_compile tests/property/test_prediction_labels.py
py -3.12 -m ruff check tests/property/test_prediction_labels.py
py -3.12 -m ruff format --check tests/property/test_prediction_labels.py
py -3.12 tools/check_chinese_project_text.py tests/property
```

## Concerns

- `stock_agent.domain.prediction` 当前不存在，因此属性测试仍会在收集阶段红灯；后续 T050 实现时需要提供测试所引用的标签分类与概率校验 API。
- 本次验证不会产生绿色测试结果，因为用户明确限制不实现生产代码。
