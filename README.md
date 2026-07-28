# A 股智能体交易平台

本项目把 TradingAgents-Astock 的真实 A 股数据和多智能体研究、确定性订单转换、
A 股事前风控、人工审批、模拟撮合和 vn.py 实盘 Gateway 整合为一个本地命令行平台。

## 当前能力

- 从 TradingAgents-Astock 的 `a_stock` 数据供应商获取真实日 K；
- 原始行情和研究报告保存为不可变 JSON，并在 SQLite 登记 SHA-256；
- 通过独立 Python 环境运行 OpenAI 兼容模型；
- 研究结论转换为结构化 `ResearchDecision`，不能直接下单；
- PAPER 和 LIVE 共用提案、风控、审批与幂等契约；
- SQLite 模拟资金、持仓、订单和成交事务账本；
- 签名、时间窗和 nonce 保护的 vn.py 子进程协议；
- 中信证券、国泰海通和后续券商使用统一 Gateway 接口。

## 安装

主平台：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

TradingAgents-Astock：

```powershell
python -m venv .runtime\tradingagents
.\.runtime\tradingagents\Scripts\python.exe -m pip install `
  -r integrations\tradingagents\requirements.lock
```

vn.py 节点：

```powershell
python -m venv .runtime\vnpy
.\.runtime\vnpy\Scripts\python.exe -m pip install `
  -r integrations\vnpy\requirements.lock
```

检查环境：

```powershell
.\.venv\Scripts\bagholder.exe doctor --json
.\.venv\Scripts\bagholder.exe status --json
```

## 模型配置

复制 `.env.example` 中的变量到本机安全环境。至少配置：

```powershell
$env:TRADINGAGENTS_LLM_PROVIDER = "openai"
$env:TRADINGAGENTS_MODEL = "你的 OpenAI 兼容模型名"
$env:TRADINGAGENTS_API_KEY = "从系统凭据存储读取的密钥"

# 使用兼容服务时再设置
$env:TRADINGAGENTS_BACKEND_URL = "https://example.com/v1"
```

API Key 不得写入仓库、命令参数、SQLite、证据文件或日志。

## 轻量研究模式

`TRADINGAGENTS_RESEARCH_MODE=FULL` 保持完整多智能体研究图。设置为
`LIGHTWEIGHT` 时，研究只依次运行行情分析、基本面分析和一次风险结论调用，
输出 `market_report`、`fundamentals_report` 与 `risk_report` 三份报告。

轻量模式仍然只生成研究证据和 `ResearchDecision`；不会创建订单、模拟成交或实盘请求。

## 外部数据缓存

完整研究与轻量研究共用 `TRADINGAGENTS_CACHE_DIR/external-data/cache.sqlite3` 中的
SQLite 缓存。日线、技术指标和财务数据默认有效 24 小时；机构预期和行业比较有效
1 小时。数据源暂时不可用时，系统只会回退到已校验的历史缓存，并在风险标记中写明
`外部数据过期回退：<工具名>`。

默认设置为 `TRADINGAGENTS_EXTERNAL_DATA_CACHE_BACKEND=sqlite`。缓存存储已抽象为
统一接口，未来可以接 PostgreSQL 或 MySQL；当前版本不会读取任何 PostgreSQL/MySQL
连接配置，也不会缓存模型提示词、密钥、模型结果、交易订单或平台证据。

## 获取真实行情

```powershell
.\.venv\Scripts\bagholder.exe market fetch CN:600519.SH `
  --start 2026-07-01 `
  --end 2026-07-24 `
  --json
```

输出包含证据 ID、来源、文件路径和 SHA-256。公共数据用于研究与模拟，不等同于券商柜台实时行情。

## 运行 TradingAgents 研究

自动获取行情后研究：

```powershell
.\.venv\Scripts\bagholder.exe research run CN:600519.SH `
  --date 2026-07-24 `
  --start 2026-07-01 `
  --json
```

也可以使用已经登记的市场证据：

```powershell
.\.venv\Scripts\bagholder.exe research run CN:600519.SH `
  --date 2026-07-24 `
  --evidence-id <市场证据ID> `
  --json
```

没有模型配置时返回 `MODEL_NOT_CONFIGURED`，不会生成订单。

## 模拟交易完整流程

创建模拟账户：

```powershell
.\.venv\Scripts\bagholder.exe paper account create `
  --account paper-main `
  --cash 1000000 `
  --json
```

运行到人工审批：

```powershell
.\.venv\Scripts\bagholder.exe pipeline run CN:600519.SH `
  --account paper-main `
  --date 2026-07-24 `
  --start 2026-07-01 `
  --mode PAPER `
  --json
```

明确审批后模拟成交：

```powershell
.\.venv\Scripts\bagholder.exe pipeline approve <运行ID> `
  --mode PAPER `
  --json
```

查询：

```powershell
.\.venv\Scripts\bagholder.exe pipeline show <运行ID> --json
.\.venv\Scripts\bagholder.exe paper account show paper-main --json
.\.venv\Scripts\bagholder.exe order show <订单ID> --json
```

## 真实下单

平台已实现 LIVE 执行通道：

```text
本地人工审批
→ 实盘总开关和账户开关
→ Gateway 健康、行情和对账检查
→ HMAC 签名 vn.py 请求
→ 券商私有 Gateway
→ 真实委托、撤单、订单和成交回报
```

两个券商账户使用独立配置，可同时装配，也会独立失败：一个账户的插件缺失、
健康检查失败或账户开关关闭，不会回退到另一个券商账户。中信证券接入示例：

```powershell
$env:BAGHOLDER_LIVE_ENABLED = "true"
$env:BAGHOLDER_CITIC_MAIN_LIVE_ENABLED = "true"
$env:BAGHOLDER_CITIC_MAIN_GATEWAY_PLUGIN = "bagholder_vnpy_citic:create_gateway"
$env:BAGHOLDER_CITIC_MAIN_GATEWAY_SHA256 = "<受信插件 SHA-256>"
$env:BAGHOLDER_CITIC_MAIN_TRADING_NODE_SECRET_HEX = "<系统凭据存储注入>"

.\.venv\Scripts\bagholder.exe pipeline run CN:600519.SH `
  --account citic-main `
  --date 2026-07-24 `
  --start 2026-07-01 `
  --mode LIVE `
  --json

.\.venv\Scripts\bagholder.exe pipeline approve <运行ID> `
  --mode LIVE `
  --broker CITIC `
  --confirm-live `
  --json
```

国泰海通使用对应的账户级变量：

```powershell
$env:BAGHOLDER_LIVE_ENABLED = "true"
$env:BAGHOLDER_GUOTAI_HAITONG_MAIN_LIVE_ENABLED = "true"
$env:BAGHOLDER_GUOTAI_HAITONG_MAIN_GATEWAY_PLUGIN = "bagholder_vnpy_guotai_haitong:create_gateway"
$env:BAGHOLDER_GUOTAI_HAITONG_MAIN_GATEWAY_SHA256 = "<受信插件 SHA-256>"
$env:BAGHOLDER_GUOTAI_HAITONG_MAIN_TRADING_NODE_SECRET_HEX = "<系统凭据存储注入>"

.\.venv\Scripts\bagholder.exe pipeline run CN:600519.SH `
  --account guotai-haitong-main `
  --date 2026-07-24 `
  --start 2026-07-01 `
  --mode LIVE `
  --json

.\.venv\Scripts\bagholder.exe pipeline approve <运行ID> `
  --mode LIVE `
  --broker GUOTAI_HAITONG `
  --confirm-live `
  --json
```

CLI 会先验证 `--broker` 与运行所属账户一致，再要求输入券商、账户、证券、方向和数量。
非交互环境、确认不匹配、对账未完成、行情不新鲜或 Gateway 不可用时都拒绝发单。
LIVE 失败绝不自动转成 PAPER，也绝不改投另一个券商账户。

当前仓库没有中信证券或国泰海通的私有 SDK，因此两家账户继续显示
`API_UNAVAILABLE`。要真正发送生产订单，必须分别取得：

- 券商批准的程序化交易产品和 API 权限；
- 官方 SDK、服务器地址和接口文档；
- 测试账户及测试交易环境；
- 委托、撤单、资金、持仓、订单、成交和断线恢复能力；
- 经确认的私有 `bagholder_vnpy_*:create_gateway` 插件；
- 券商测试环境完整验收。

普通证券客户端账号密码不能替代程序化交易接口。首次联调必须在券商测试环境完成。

## 测试

确定性测试不会访问网络：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
```

显式真实行情冒烟：

```powershell
$env:RUN_LIVE_DATA_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest tests\live\test_astock_market_data.py -q
Remove-Item Env:RUN_LIVE_DATA_TESTS
```

冒烟测试只获取 `600519` 的指定历史日 K、保存证据并校验摘要，不运行模型，也不产生任何订单。
