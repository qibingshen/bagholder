# T049 预测失败场景红灯测试报告

## 交付内容

- 新增 `tests/failure/test_prediction_failures.py`。
- 覆盖当前预测对 `DELAYED`、`STALE`、`CLOSED`、时点不可验证，以及来源、市场时间、采集时间、数据版本、特征版本缺失的明确拒绝。
- 覆盖历史快照在当前数据不可用时仍可只读展示。
- 覆盖缺少有效到期价格、停牌或不可成交、非有效交易日时保持 `PENDING_VALIDATION`、不产生方向标签且保留原因。
- 覆盖同一快照标识追加后，对概率、标签规则、模型版本或数据版本的覆盖拒绝。
- 覆盖晚到或版本不匹配的价格、公司行动、交易日历与规则回填拒绝，防止回写历史预测。

## 红灯验证

执行命令：

```powershell
py -3.12 -m pytest -o addopts='' tests/failure/test_prediction_failures.py -v
```

结果：测试收集失败，退出码为 `2`。失败原因：

```text
ModuleNotFoundError: No module named 'stock_agent.domain.prediction'
```

该领域模块属于后续 T050 的实现范围；本任务未新增或修改任何生产代码、存储、网络、模型或交易能力。

## 后续关注项

- T050/T052 需实现本测试声明的预测输入、不可变快照和独立到期回填边界后，再将本测试转为通过。
- 对无有效到期价格的场景，领域结果必须同时保留 `PENDING_VALIDATION` 与可审计的明确原因，不能以方向标签替代。
