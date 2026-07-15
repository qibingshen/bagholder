# T049：预测失败场景测试

## 目标

为过期/缺失数据、无有效到期价格和版本回写建立预测失败场景红灯测试。

## 修改范围

- 新建：`tests/failure/test_prediction_failures.py`

## 必须先新增并运行失败的测试

1. 当前预测输入为 DELAYED/STALE/CLOSED/不可验证时点、缺来源/市场时间/采集时间/数据或特征版本时，明确拒绝并说明原因；历史快照仍可只读展示。
2. 到期后无有效到期价格、停牌、不可成交或到期日非有效交易日时，结果为 PENDING_VALIDATION/明确无效原因，不得产生上涨/震荡/下跌。
3. 预测快照一旦追加保存，任何更新、覆盖、修改 probabilities、规则版本、模型版本或数据版本的请求都必须拒绝；到期结果只能独立追加关联。
4. 到期结果或回填所用价格、公司行动、日历和规则版本晚于允许时点或与快照不匹配时拒绝，不能回写历史预测。

## 约束

- 仅写失败测试和报告，不实现预测、存储、模型或网络。
- 中文说明，不生成量化数字或交易能力。

## 验证

运行 `py -3.12 -m pytest -o addopts='' tests/failure/test_prediction_failures.py -v`，确认红灯，报告 `D:/personal/bagholder/.superpowers/sdd/task-049-report.md` 并提交。最终只回复提交、测试摘要、concerns。
