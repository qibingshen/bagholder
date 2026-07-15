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

## 调用形状与执行限制

每个工具输入必须是版本化对象，至少含 `contract_version`、`request_id`、工具专属的严格参数，
以及集合查询所需的 `page_size`、`page_cursor`。工具不得接受任意 SQL、文件路径、网络地址、
凭据、券商标识或未声明字段；未知字段、类型错误和跨市场代码歧义返回 `VALIDATION_ERROR`。
所有结果与错误均遵循 `common.md` 的信封、分页、超时、资源限额和版本演进规则。

只读工具的默认/最大超时为 5/15 秒；`backtest.start_readonly` 与 `task.start_analysis` 的启动
请求默认/最大超时为 15/30 秒，且必须使用 `idempotency_key`。每个本机调用方同一时刻最多拥有
一个分析任务，所有列表查询最多返回 200 项，历史查询最多返回 10,000 根 K 线，响应最大 64 MiB。
超时或限额错误不得返回可被大模型当作完整数字的部分负载。

每一次成功的量化工具调用必须返回 `tool_name`、`tool_version`、规范化参数摘要、`called_at`、
`result_id`、`data_as_of`、`data_version`、`freshness` 和 `provenance`。预测还必须返回
`prediction_version` 与 `model_version`。研究对话只能逐项引用这些字段；缺失任一引用时必须输出
拒绝说明，不能补造数字。

## Skill 版本化执行清单

| Skill | 允许工具 | 输入与输出 | 超时与重试 | 失败码与审计 |
|---|---|---|---|---|
| 每日分析 | `market.*`、`sector.*`、`report.*`、`task.start_analysis` | 市场、交易日；输出报告结果引用 | 启动 30 秒；仅 `SOURCE_TEMPORARY_UNAVAILABLE` 指数退避重试 2 次 | `TIMEOUT`、`STALE_DATA`；记录任务、工具结果与降级范围 |
| 个股诊断 | `market.get_quotes`、`market.get_history`、`prediction.get` | 证券与市场；输出带溯源的诊断或拒绝 | 查询 15 秒；不重试 `VALIDATION_ERROR` | `NO_DATA`、`STALE_DATA`；记录参数摘要与结果标识 |
| 板块轮动 | `sector.*`、`market.get_status` | 板块范围与时点；输出指标引用或不可比较说明 | 查询 15 秒；限频后最多重试 1 次 | `RESOURCE_LIMIT_EXCEEDED`、`NOT_COMPARABLE`；记录覆盖率 |
| 预测复盘 | `prediction.list_history`、`backtest.get`、`report.get` | 市场、周期、版本；输出到期结果与基准比较引用 | 查询 15 秒；不重试完整性错误 | `POINT_IN_TIME_VIOLATION`、`NO_MATURED_RESULT`；记录数据截止时点 |
| 模型评估 | `model.get_evaluation`、`backtest.get`、`task.start_analysis` | 候选版本；输出门禁证据，不得发布 | 启动 30 秒；可恢复源错误重试 1 次 | `PERMISSION_DENIED`、`TIMEOUT`；记录候选版本和证据结果 |

Skill 只能按表中允许工具调用；任何越表调用、发布、回滚、删除、凭据访问或券商能力必须拒绝，
并产生 `PERMISSION_DENIED` 审计记录。表内所有步骤均依赖已提交且新鲜度合格的本地数据版本。
