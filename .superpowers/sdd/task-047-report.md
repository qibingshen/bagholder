# T047：预测安全契约测试报告

## 范围

仅新增 `tests/contract/test_prediction_contract.py`，未修改生产代码、模型、网络或交易相关内容。

## 契约覆盖

- 预测输入必须绑定证券身份、预测时点、市场时点、采集时点、数据/特征/模型版本与当前数据可用性；缺失或不可用时拒绝。
- 预测输出仅允许 1、5、20 个交易日，包含三类概率、置信度、主要依据、风险因素、新鲜度、模型版本、结构化量化事实引用和固定提示“研究参考，不构成投资建议”。
- 三类概率不得为负，且总和必须在 100% 正负 0.1 个百分点内；收益承诺和买卖指令必须拒绝。
- 缺少 MCP 或本地事实的结构化引用时不得输出量化数字。
- 预测快照只能追加，禁止同一快照标识覆盖；当前过期预测必须不可用，历史快照可回看且与当前预测使用不同展示状态。

## 红灯验证

执行命令：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_prediction_contract.py -v
```

结果：失败（符合本任务“先写测试并确认红灯”的要求）。测试收集阶段报出：

```text
ModuleNotFoundError: No module named 'stock_agent.domain.prediction'
```

失败原因是预测领域契约及快照存储尚未实现，预期由后续 T050、T052 及相关输出/展示任务提供；本任务未实施任何生产代码使测试转绿。

## Concerns

测试刻意保持红灯。在预测领域模块、快照追加存储和展示层实现之前，无法进行绿灯验证；后续实现应保持本测试公开 API 和固定风险提示不变。

## 审查修正（第二轮）

- 量化事实引用改为逐项通过 `covered_fields` 覆盖 `up_probability`、`flat_probability`、`down_probability` 与 `confidence`，并要求引用类型只能为 `MCP` 或 `LOCAL`。
- 每个引用均要求匹配预测证券、预测时点、数据版本及模型版本；新增无关覆盖字段、错误引用类型、错误证券、错误时点、错误数据/模型版本、漏覆盖字段的拒绝测试。
- 新增 `confidence`、`primary_evidence`、`risk_factors`、`freshness`、`model_version`、`disclaimer` 缺失拒绝测试；固定提示改为逐字等于“研究参考，不构成投资建议”，语义相近文案也拒绝。
- 概率总和边界改为明确断言 99.9、100.0、100.1 可接受，99.89、100.11 必须拒绝，并以 `pytest.approx` 避免测试断言受二进制浮点表示影响。

## 第二轮红灯验证

执行命令：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_prediction_contract.py -v
```

结果：仍在收集阶段失败，错误保持为：

```text
ModuleNotFoundError: No module named 'stock_agent.domain.prediction'
```

另执行 `py -3.12 -m py_compile tests/contract/test_prediction_contract.py`，语法检查通过。红灯原因仍是生产领域模块尚未实现，未为转绿添加任何实现。
