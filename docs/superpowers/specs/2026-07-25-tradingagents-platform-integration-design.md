# TradingAgents-Astock 平台集成设计

日期：2026-07-25  
状态：已确认

## 1. 目标

在现有 A 股安全交易骨架上完成第一版平台集成，使用户能够通过命令行执行以下完整链路：

1. 从 TradingAgents-Astock 的 A 股数据源获取真实市场数据；
2. 将原始数据保存为不可变证据并登记可验证的数据版本；
3. 通过 OpenAI 兼容模型运行 TradingAgents 多智能体研究；
4. 将研究结果转换为现有 `ResearchDecision`；
5. 经过确定性订单转换、A 股规则、账户风控和人工审批；
6. 明确选择 `PAPER` 模拟成交或 `LIVE` 券商真实下单；
7. 保存运行、审批、委托、成交、资金、持仓和审计记录。

本阶段提供命令行和标准 JSON 输出，不建设 Web 或桌面界面。

## 2. 核心约束

- TradingAgents、vn.py 和主平台继续使用三个独立 Python 环境。
- TradingAgents 通过一次一请求的隔离子进程和 JSON Lines 协议接入主平台。
- 大模型不能直接调用订单执行器，也不能生成已执行订单。
- `PAPER` 和 `LIVE` 使用相同的研究、提案、风控和审批契约，只在最终执行器分流。
- `LIVE` 执行失败时不得自动降级为 `PAPER`。
- 中信证券和国泰海通使用相同的 `BrokerGateway` 接口，券商差异留在插件内部。
- 未安装券商授权 SDK/Gateway、未取得 API 权限或未通过连接检查时，真实下单必须返回 `LIVE_BLOCKED`。
- 普通客户端账号密码不作为量化接口凭据。
- 模型和券商密钥只能从环境变量或操作系统凭据存储读取，不进入参数、证据、数据库或日志。
- SQLite 保存元数据和交易状态；不可变 JSON 保存原始行情和研究证据。
- 相同数据版本不重复抓取，相同订单幂等键不重复调用执行器。

## 3. 技术路线

### 3.1 隔离进程

主平台通过 `TradingAgentsClient` 启动：

```text
.runtime/tradingagents/Scripts/python.exe integrations/tradingagents/runner.py
```

主进程向标准输入写入一条 JSON 请求，子进程向标准输出写入一条 JSON 响应后退出。标准错误只用于经过脱敏的诊断信息。主进程负责：

- 设置最长运行时间；
- 超时后终止整个子进程树；
- 限制可继承的环境变量；
- 校验退出码和唯一 JSON 响应；
- 使用 Pydantic 校验所有字段；
- 拒绝额外文本、空响应、错误哨兵和非有限数值。

选择隔离进程而不是主进程直接导入，目的是隔离依赖、模型请求和公共数据源异常。第一版不引入常驻 HTTP 服务。

### 3.2 数据源

TradingAgents-Astock 默认使用 `a_stock` 数据供应商：

- mootdx/通达信：K 线、财务快照、F10；
- 新浪财经：K 线和财务数据备用源；
- 腾讯财经：估值、市值、换手率；
- 东方财富：股票信息、龙虎榜、解禁数据；
- 同花顺：盈利预测、热股、北向资金；
- 财联社：财经新闻。

第一版真实行情验收以日 K 数据为准。公共数据源可用于研究和模拟，但不宣称等同于券商柜台实时行情。`LIVE` 下单前的可交易价格和账户状态必须由券商 Gateway 再次确认。

## 4. 组件设计

### 4.1 TradingAgentsClient

职责：

- 构造 `FETCH_MARKET` 和 `RUN_RESEARCH` 请求；
- 调用指定隔离环境；
- 实施超时、退出码和 JSON 协议校验；
- 将外部异常转换为稳定的平台错误码；
- 不读取或保存模型密钥。

依赖通过 `TRADINGAGENTS_PYTHON` 配置；缺省为项目下 `.runtime/tradingagents/Scripts/python.exe`。

### 4.2 MarketDataService

职责：

- 将 `CN:600519.SH` 转换为 TradingAgents 所需的 `600519`；
- 校验交易所后缀与股票代码；
- 获取指定开始、结束日期的 OHLCV；
- 拒绝未来数据、空数据、日期乱序和重复日期；
- 生成标准化市场快照。

市场快照包含：

- `evidence_id`
- `security_key`
- `start_date`
- `end_date`
- `as_of`
- `retrieved_at`
- `source`
- `records`
- `schema_version`

每条记录包含 `date`、`open`、`high`、`low`、`close` 和 `volume`。

### 4.3 EvidenceStore

职责：

- 先生成规范化 UTF-8 JSON；
- 对文件内容计算 SHA-256；
- 以新文件方式写入，目标已存在时拒绝覆盖；
- 在同一应用事务中登记证据元数据；
- 读取时重新计算摘要，摘要不符时返回 `EVIDENCE_TAMPERED`。

目录格式：

```text
var/evidence/YYYY-MM-DD/CN_600519_SH/
├── market-<evidence-id>.json
└── research-<evidence-id>.json
```

`var/` 是运行数据目录，必须在 `.gitignore` 中排除。

### 4.4 ResearchService

职责：

- 只接受已登记且摘要有效的市场证据；
- 调用 TradingAgents 多智能体研究；
- 保存最终研究报告、决策、模型提供商、模型名、分析日期和关联市场证据；
- 生成符合现有 `ResearchDecision` 契约的结果；
- 将 `evidence_ids` 绑定到已保存的市场和研究证据。

第一版保存 TradingAgents 实际返回的最终状态和报告，但不会声称已经冻结公共网站的所有上游新闻页面。研究证据代表本次运行实际观察到的结果。

模型配置：

```text
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_MODEL=<OpenAI兼容模型名>
TRADINGAGENTS_API_KEY=<密钥>
TRADINGAGENTS_BACKEND_URL=<可选兼容接口地址>
```

缺少密钥时，行情功能继续可用，研究流程返回 `MODEL_NOT_CONFIGURED`。

### 4.5 PipelineService

职责：

- 创建并推进一次管道运行；
- 每次状态变化写入 `pipeline_runs` 和 `audit_events`；
- 调用现有信号转换、风控和审批服务；
- 只允许符合状态机的转移；
- 失败状态保存稳定错误码和脱敏错误说明；
- 为最终订单生成幂等键。

正常状态：

```text
CREATED
→ DATA_READY
→ RESEARCH_READY
→ PROPOSAL_READY
→ RISK_PASSED
→ WAITING_APPROVAL
→ PAPER_EXECUTED 或 LIVE_SUBMITTED
→ RECONCILED
```

失败或阻断状态：

```text
DATA_FAILED
MODEL_NOT_CONFIGURED
RESEARCH_FAILED
RISK_BLOCKED
APPROVAL_REJECTED
APPROVAL_EXPIRED
LIVE_BLOCKED
EXECUTION_FAILED
RECONCILIATION_REQUIRED
```

安全恢复规则：

- 数据或研究失败可以在原运行中创建新的尝试记录，但不能覆盖旧证据；
- 风控阻断后必须创建新提案，不得修改已阻断提案；
- 审批过期后必须重新审批；
- 执行结果为未知时进入 `RECONCILIATION_REQUIRED`，冻结该账户的新开仓委托；
- 恢复操作继续使用原订单幂等键，不得重复发单。

### 4.6 PaperExecutionService

职责：

- 创建和查询模拟账户；
- 使用已审批限价单进行确定性本地撮合；
- 在同一 SQLite 事务内更新模拟订单、成交、现金和持仓；
- 支持买入、卖出、资金不足、持仓不足和 A 股可卖数量校验；
- 重复执行同一幂等键时返回原成交结果。

第一版模拟账户由用户明确创建并指定初始现金，不自动复制真实账户。

### 4.7 LiveExecutionService

职责：

- 校验订单模式为 `LIVE`；
- 校验系统实盘总开关和账户实盘开关；
- 校验券商 API 状态、交易会话、对账状态和行情新鲜度；
- 要求用户二次确认账户、证券代码和数量；
- 通过现有签名、防重放 vn.py 协议提交订单；
- 保存券商订单号、状态、成交和错误回报；
- 支持委托、撤单、资金查询、持仓查询、订单查询、成交查询和断线恢复。

真实订单状态：

```text
SUBMITTING
SUBMITTED
PARTIALLY_FILLED
FILLED
CANCEL_PENDING
CANCELLED
REJECTED
UNKNOWN
```

`UNKNOWN` 必须触发对账和账户开仓冻结，不能自动再次提交。

### 4.8 BrokerGateway

通用接口提供：

```python
connect()
health()
query_account()
query_positions()
query_orders()
query_trades()
submit_order()
cancel_order()
close()
```

中信证券与国泰海通各自使用配置文件注册插件名称、SDK 能力和账户 ID。私有 SDK 不纳入公共依赖，也不提交仓库。平台在启动时动态加载经过明确允许的插件。

在取得对应券商的正式 API 产品之前，两家配置保持：

```text
api_state=API_UNAVAILABLE
supports_live_orders=false
```

这表示平台代码具备真实执行通道，但当前环境尚未获得真正发单所需的外部能力。

## 5. 数据持久化

SQLite 使用以下表：

| 表 | 责任 |
|---|---|
| `evidence_snapshots` | 证据 ID、类型、证券、来源、期间、文件路径和 SHA-256 |
| `research_decisions` | 结构化研究决策、模型版本和关联证据 |
| `pipeline_runs` | 当前状态、关联记录、失败代码和时间 |
| `pipeline_attempts` | 每次外部数据或研究调用的开始、结束和结果 |
| `paper_accounts` | 模拟现金、权益和账户状态 |
| `paper_positions` | 模拟持仓、成本和可卖数量 |
| `orders` | PAPER/LIVE 订单、幂等键、内部与券商订单号 |
| `fills` | PAPER/LIVE 成交记录 |
| `approvals` | 审批人、结果和有效期 |
| `audit_events` | 只追加的状态和安全事件 |

数据库启用外键、WAL、忙等待和显式事务。金额与价格以十进制定点字符串保存，业务层使用 `Decimal`，禁止使用二进制浮点数作为交易金额。

## 6. 命令行

```powershell
# 状态和环境检查
bagholder status --json
bagholder doctor --json

# 创建、查询模拟账户
bagholder paper account create --account paper-main --cash 1000000
bagholder paper account show paper-main --json

# 获取真实行情
bagholder market fetch CN:600519.SH `
  --start 2026-07-01 `
  --end 2026-07-24 `
  --json

# 单独运行研究
bagholder research run CN:600519.SH `
  --date 2026-07-24 `
  --json

# 运行到人工审批
bagholder pipeline run CN:600519.SH `
  --account paper-main `
  --date 2026-07-24 `
  --json

# 模拟执行
bagholder pipeline approve <run-id> --mode PAPER --json

# 真实执行
bagholder pipeline approve <run-id> `
  --mode LIVE `
  --broker CITIC `
  --confirm-live `
  --json

# 查看运行和执行结果
bagholder pipeline show <run-id> --json
bagholder order show <order-id> --json
```

`--confirm-live` 只表示进入交互式二次确认，不允许在命令行直接携带账号密码或确认文本。非交互环境默认拒绝实盘审批。

## 7. 错误处理

稳定错误码至少包括：

| 错误码 | 行为 |
|---|---|
| `DATA_SOURCE_UNAVAILABLE` | 停止在数据阶段，可安全重试 |
| `DATA_INVALID` | 拒绝保存和研究 |
| `EVIDENCE_TAMPERED` | 冻结该证据关联流程 |
| `MODEL_NOT_CONFIGURED` | 允许行情使用，禁止研究 |
| `RESEARCH_TIMEOUT` | 终止子进程，停止流程 |
| `RESEARCH_PROTOCOL_ERROR` | 保存脱敏诊断，停止流程 |
| `RISK_BLOCKED` | 不允许审批和执行 |
| `APPROVAL_REQUIRED` | 停止在人工审批节点 |
| `LIVE_DISABLED` | 实盘总开关未打开 |
| `BROKER_API_UNAVAILABLE` | 券商 SDK、授权或会话不可用 |
| `ORDER_STATE_UNKNOWN` | 冻结新开仓并触发对账 |
| `DUPLICATE_REQUEST` | 返回原执行结果，不再次发单 |

任何外部异常都必须映射为稳定错误码。日志不得包含 API Key、券商密码、会话令牌或完整原始请求。

## 8. 测试设计

### 8.1 单元测试

- 股票代码转换和非法证券拒绝；
- OHLCV 日期、顺序、重复、价格和成交量校验；
- JSON 规范化、SHA-256 生成和篡改检测；
- 子进程超时、退出码、空响应、额外文本和非法 JSON；
- 管道状态机合法与非法转移；
- 实盘双开关、二次确认和禁止降级；
- 真实订单状态映射和未知状态冻结；
- 模拟资金、持仓和幂等成交。

### 8.2 契约测试

- TradingAgents 请求与响应 JSON Schema；
- `ResearchDecision` 必须引用真实存在且摘要有效的证据；
- vn.py 签名、时间窗口、防重放和订单回报；
- `BrokerGateway` 的委托、撤单、查询和健康检查接口；
- 中信与国泰海通配置在未授权环境中保持 `API_UNAVAILABLE`。

### 8.3 集成测试

- 使用受控假 TradingAgents 进程完成行情到 `WAITING_APPROVAL`；
- 模拟审批后只产生一次订单和成交；
- SQLite 事务失败时资金、持仓、订单和成交全部回滚；
- 使用假 vn.py Gateway 验证真实模式提交、撤单、部分成交、拒单和未知状态；
- 重启后从 SQLite 恢复运行状态和幂等结果；
- 对账不一致时阻断新开仓。

### 8.4 可选外部验收

设置 `RUN_LIVE_DATA_TESTS=1` 后：

- 从公共 A 股数据源拉取 `600519` 指定日期范围日 K；
- 保存市场证据；
- 重新读取并校验 SHA-256；
- 不要求模型密钥，不触发任何订单。

模型真实验收仅在用户配置兼容 API 密钥时运行。券商真实验收必须使用券商提供的测试环境；在测试环境未完成前不得用生产账户作为首次联调目标。

## 9. 验收标准

- 主项目、TradingAgents 和 vn.py 三个环境均能独立运行健康检查。
- `market fetch` 能取得真实 A 股日 K 并生成不可变证据和数据版本。
- 没有模型密钥时研究返回 `MODEL_NOT_CONFIGURED`，且订单表为空。
- 使用受控模型响应时，管道能稳定到达 `WAITING_APPROVAL`。
- 未审批、审批过期、风控拒绝均不能进入任何执行器。
- `PAPER` 审批后资金、持仓、订单和成交一致，重复请求不重复成交。
- `LIVE` 审批后只有在总开关、账户开关、Gateway 和会话全部可用时才发送签名请求。
- `LIVE` 不可用时返回明确阻断状态，不生成模拟成交。
- 假 Gateway 能覆盖真实委托生命周期；真实券商 Gateway 在取得 API/SDK 后按同一契约接入。
- 中信证券与国泰海通未授权配置不得显示为实盘可用。
- 现有测试继续通过，新增代码通过 Ruff 和 mypy 严格检查。

## 10. 非目标

- 本阶段不建设 Web 或桌面界面。
- 不实现高频交易、毫秒级行情或交易所直连。
- 不绕过券商的 API 申请、合规、适当性和测试流程。
- 不把公共网站数据宣传为交易所授权的券商级实时行情。
- 不允许 TradingAgents 或任何大模型直接持有券商凭据。
- 不在未取得中信或国泰海通官方接口材料时猜测其私有 SDK 调用方式。
