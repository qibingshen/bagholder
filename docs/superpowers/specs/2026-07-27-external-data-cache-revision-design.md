# TradingAgents 外部数据缓存修订设计

日期：2026-07-27
状态：待用户评审
## 目标

为 TradingAgents 的轻量研究和完整研究提供同一套外部数据缓存，降低公开行情和基本面数据源不稳定、重复请求和长耗时带来的影响。默认使用本地 SQLite；架构上预留 PostgreSQL 和 MySQL 的可替换存储实现。

## 范围

缓存以下公共外部工具的可 JSON 序列化原始响应：`get_stock_data`、`get_indicators`、`get_fundamentals`、`get_balance_sheet`、`get_cashflow`、`get_income_statement`、`get_profit_forecast` 与 `get_industry_comparison`。

不缓存模型提示词、模型调用结果、API Key、请求头、交易数据、订单或主平台的研究证据。现有 MARKET 证据机制不变。

## 统一接入方式

在研究图和外部工具之间放置一个统一缓存包装层。完整图与轻量图都从该层调用工具，因此：

- 同一模式的重复研究可复用缓存；
- 完整研究与轻量研究可共享同一股票、同一参数的数据；
- 任何研究模式都不直接依赖 SQLite、PostgreSQL 或 MySQL 的具体 API。

缓存键由工具名、股票代码、规范化参数 JSON 和数据供应商版本组成。缓存条目保存键、工具名、参数摘要、来源、抓取时间、过期时间、原始 JSON 与 SHA-256。

## 存储接口和数据库演进

定义稳定的 `ExternalDataCacheStore` 接口，包含读取、原子写入和删除损坏条目的能力。研究包装层只依赖这个接口。

第一期提供 `SqliteExternalDataCacheStore`：数据库与缓存数据放在 `TRADINGAGENTS_CACHE_DIR/external-data/`，使用 SQLite 事务保证元数据与数据索引的一致性，不接触交易账本。

后续按同一接口新增 `PostgresExternalDataCacheStore` 或 `MySqlExternalDataCacheStore`。它们必须保持相同的键计算、TTL、SHA-256 校验、过期回退和 `stale=true` 语义；切换只改变缓存存储配置，不改研究图、报告字段或工具包装层。

第一期不提供 PostgreSQL/MySQL 连接配置、驱动依赖或迁移脚本，避免为当前本地单机缓存引入不必要的运维复杂度。

## 生命周期和失败处理

TTL 为：日线/技术指标 24 小时，三张财务报表与公司基本面 24 小时，估值/机构预期/行业对比 1 小时。

访问顺序：先返回未过期缓存；未命中或过期时访问上游；上游成功后原子写入新数据；上游失败但存在历史条目时返回该条目并标记 `stale=true`；没有历史条目时保留原有错误。

读取时验证 SHA-256。校验或 JSON 解析失败的条目删除并视为未命中。完整研究和轻量研究的风险结论均必须将使用的陈旧数据写入风险标记。

## 验收

1. 新鲜缓存命中时不访问上游。
2. 过期缓存会刷新并替换。
3. 上游失败且有历史缓存时返回 `stale=true`；无缓存时保留失败。
4. SHA-256 不匹配时拒绝缓存。
5. 轻量与完整研究分别重复运行时不重复抓取；两种模式之间也可复用缓存。
6. SQLite 实现通过 `ExternalDataCacheStore` 契约测试；未来 PostgreSQL/MySQL 实现可复用同一契约测试，研究流程无需修改。
