# MCP 工具与权限契约

MCP 仅本机 stdio 或受控本机传输运行。每个工具输入/输出遵循 `common.md`，数值必须保留工具结果、
参数摘要、调用时间、数据版本和必要的模型/预测版本引用。

允许：`market.get_status`、`market.get_quotes`、`market.get_history`、`sector.list`、
`sector.get_metrics`、`sector.get_rotation`、`custom_sector.get`、`custom_sector.get_members_at`、
`prediction.get`、`prediction.list_history`、`backtest.get`、`backtest.start_readonly`、
`report.get`、`report.list`、`task.get`、`task.list`、`task.start_analysis`、`model.get`、
`model.list`、`model.get_evaluation`。

禁止：发布模型、回滚模型、删除数据或预测、替换备份、凭据管理、直接存储访问、任何券商登录或交易。
非本机调用、未注册工具、越权参数和破坏性动作返回 `PERMISSION_DENIED` 或 `TOOL_NOT_AVAILABLE`，
并写入脱敏审计日志。大模型在工具失败或结果不完整时必须拒绝生成相关量化数字。
