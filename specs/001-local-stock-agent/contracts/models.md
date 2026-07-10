# 模型契约

`model.get`、`model.list`、`model.get_evaluation` 只读返回模型文件哈希、训练参数、代码、数据范围、
特征/标签版本、回测、基准、影子、批准、发布与回滚证据。

候选状态顺序为 `TRAINED → BACKTEST_PASSED → BASELINE_PASSED → SHADOW_RUNNING →
SHADOW_PASSED → AWAITING_LOCAL_APPROVAL → RELEASED`。发布最低门槛：Brier score 相对简单基准
改善至少 5%，平衡准确率提高至少 2 个百分点，任一市场/周期退化不超过 2 个百分点，影子运行至少
30 个交易日无严重故障，并由本机桌面用户批准。发布/回滚是桌面管理操作，不是 MCP 契约。
