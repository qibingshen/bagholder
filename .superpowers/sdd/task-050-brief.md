# T050：预测领域模型、标签与简单基准

## 目标

实现 T047–T049 已批准的预测领域公开契约：安全输入输出、标签/结果、不可变快照、独立到期结果及简单基准概率；不实现高级模型、训练或发布。

## 修改范围

- 新建：`src/stock_agent/domain/prediction.py`
- 可修改：最小共享契约/测试文件，仅用于接入已批准的公开接口；不得删除测试断言。

## 必须满足

1. 实现 T047 的强类型输入/输出：1/5/20、三概率、0–100 单项、总和100±0.1、固定提示、置信度/依据/风险/新鲜度/版本必填，逐数字 MCP/LOCAL 引用覆盖且匹配证券/时点/版本。
2. 实现 T048 的标签和结果：按市场有效交易日、规则快照 `>=`/`<=` 阈值；预测输入禁未来到期价、未来日历/特征/公司行动；到期独立结果允许到期后价格，缺价/停牌/非交易日为 `PENDING_VALIDATION`。
3. 实现 T049 的不可变快照和追加结果：快照不能改写；结果独立关联 prediction_snapshot_id，所有价格/行动/日历/规则时点和版本逐项校验。
4. 简单基准仅形成受上述契约约束的候选概率，不承诺收益、不触发交易。

## TDD 与验证

先运行三组红灯：
`py -3.12 -m pytest -o addopts='' tests/contract/test_prediction_contract.py tests/property/test_prediction_labels.py tests/failure/test_prediction_failures.py -v`

再最小实现至通过，运行全量 pytest、Ruff、中文检查。报告 `D:/personal/bagholder/.superpowers/sdd/task-050-report.md`。提交后只回复提交、测试摘要、concerns。
