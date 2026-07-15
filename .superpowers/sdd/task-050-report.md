# T050 预测领域实现报告

## 完成内容

- 新增 `src/stock_agent/domain/prediction.py`：预测输入/输出、量化事实引用、标签规则、到期结果、不可变快照及追加式仓库。
- 为公司行动补充可得时点字段，用于预测输入与到期回填的点时校验。
- 实现 1/5/20 个有效交易日、`>=`/`<=` 阈值分类、缺少到期价格的 `PENDING_VALIDATION`，以及概率候选的边界校验。
- 未训练或发布模型，未联网，未生成事实数字，未触发交易。

## TDD 证据

实现前已执行三组目标测试，三组均因 `stock_agent.domain.prediction` 不存在而在导入期红灯。

```text
ModuleNotFoundError: No module named 'stock_agent.domain.prediction'
```

实现后，目标三组测试结果为 93 通过、1 失败；全量结果为 456 通过、1 失败。Ruff 与 `git diff --check` 通过。

## 已知阻塞

唯一失败位于 `tests/property/test_prediction_labels.py` 的“拒绝非规定交易日周期”测试。Hypothesis 生成非法周期 `21` 时，测试辅助函数先以 `reference_index + 21` 索引仅覆盖到 `20` 日的测试日历，抛出 `IndexError`，未调用 `resolve_actual_outcome`，因此不属于领域实现可修复的失败。未修改该测试或其断言。
