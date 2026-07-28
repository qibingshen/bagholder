# 轻量研究图设计

日期：2026-07-27
状态：待用户评审

## 目标

为 TradingAgents-Astock 增加轻量研究模式，缩短模型调用链路。该模式只产出：

1. 行情分析；
2. 基本面分析；
3. 风险结论和结构化交易动作。

它继续生成既有的 `ResearchDecision`，不改变证据保存、信号转换、PAPER/LIVE 风控、人工审批或执行流程。

## 方案

新增 `TRADINGAGENTS_RESEARCH_MODE` 环境变量：

- 未设置或为 `FULL`：保持现有完整 TradingAgents 图；
- 为 `LIGHTWEIGHT`：使用轻量图。

轻量图不调用完整 `TradingAgentsGraph.propagate()`。隔离 runner 改为：

1. 创建仅含 `market`、`fundamentals` 的 `TradingAgentsGraph`，复用其数据供应商、工具节点、模型配置和输出语言配置；
2. 运行两个分析节点，得到 `market_report` 和 `fundamentals_report`；
3. 使用一次短提示词调用快速模型，基于两份报告生成 JSON 风险结论：`action`、`confidence`、`risk_flags`、`risk_report`；
4. 将三份报告返回给现有 `ResearchService`，并沿用既有证据与决策契约。

完整图中的社媒、新闻、政策、游资、解禁、多空辩论、交易员辩论和三方风险辩论均不进入轻量路径。

## 契约与错误处理

`RUN_RESEARCH` 的请求和响应 schema 不变。轻量模式返回的 `reports` 仅包含：

- `market_report`
- `fundamentals_report`
- `risk_report`

风险结论必须使用白名单动作 `BUY`、`HOLD`、`SELL`。模型输出无法解析、字段缺失、动作不合法或置信度不合法时，runner 返回既有稳定失败响应，不会生成研究决策、更不会触发订单。

## 配置与安全

轻量模式仍只从环境变量读取 API Key、模型和兼容接口地址。密钥不进入请求 payload、证据文件、SQLite 或日志。`TRADINGAGENTS_TIMEOUT_SECONDS` 继续控制隔离子进程总时限。

## 测试

1. 默认 `FULL` 模式保持调用完整图；
2. `LIGHTWEIGHT` 模式只选择 `market` 与 `fundamentals`；
3. 风险结论的合法 JSON 被规范化为既有研究结果；
4. 不合法风险结论被拒绝；
5. 现有完整测试、Ruff 和 Mypy 继续通过。

## 非目标

- 不改变交易建议到订单的转换规则；
- 不自动执行 PAPER 或 LIVE 订单；
- 不把模型输出当作投资建议或事实来源；
- 不引入常驻服务或新的外部数据供应商。
